package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

const widgetTokenPrefix = "uai_widget_"
const defaultWidgetTTL = 15 * time.Minute

var widgetScopes = []string{"messages:read", "messages:write"}

// WidgetBinding is attached to a principal authenticated by a widget token.
// The binding is checked both in route middleware and in the store.
type WidgetBinding struct {
	TokenID        string
	AssistantID    string
	ConversationID string
	Origin         string
}

type WidgetToken struct {
	ID             string     `json:"id"`
	AssistantID    string     `json:"assistant_id"`
	ConversationID string     `json:"conversation_id"`
	Subject        string     `json:"subject"`
	Scopes         []string   `json:"scopes"`
	Origin         string     `json:"origin"`
	ExpiresAt      time.Time  `json:"expires_at"`
	RevokedAt      *time.Time `json:"revoked_at,omitempty"`
	CreatedAt      time.Time  `json:"created_at"`
	CreatedBy      string     `json:"created_by"`
}

type WidgetTokenStore interface {
	WidgetTarget(context.Context, string, string) error
	CreateWidgetToken(context.Context, WidgetToken, string) (WidgetToken, error)
	AuthenticateWidget(context.Context, string) (Principal, error)
	RevokeWidgetToken(context.Context, string) error
}

func (s *server) widgetRoutes(r chi.Router) {
	r.With(requireScope("widget-tokens:write")).Post("/v1/widget/tokens", s.createWidgetToken)
	r.With(requireScope("widget-tokens:write")).Delete("/v1/widget/tokens/{id}", s.revokeWidgetToken)
}

func (s *server) createWidgetToken(w http.ResponseWriter, r *http.Request) {
	var input struct {
		AssistantID      string `json:"assistant_id"`
		ConversationID   string `json:"conversation_id"`
		Subject          string `json:"subject"`
		Origin           string `json:"origin"`
		ExpiresInSeconds int    `json:"expires_in_seconds"`
	}
	if !decode(w, r, &input) {
		return
	}
	if !validID(input.AssistantID) || !validID(input.ConversationID) ||
		len(input.Subject) > 200 || !validWidgetOrigin(input.Origin) ||
		!s.originAllowed(input.Origin) {
		problem(w, 422, "invalid_widget_token")
		return
	}
	ttl := defaultWidgetTTL
	if input.ExpiresInSeconds != 0 {
		if input.ExpiresInSeconds < 60 || input.ExpiresInSeconds > 86400 {
			problem(w, 422, "invalid_widget_token")
			return
		}
		ttl = time.Duration(input.ExpiresInSeconds) * time.Second
	}
	if input.Subject == "" {
		input.Subject = "widget"
	}
	if err := s.store.WidgetTarget(r.Context(), input.AssistantID, input.ConversationID); err != nil {
		storeError(w, err)
		return
	}
	token, digest, err := newWidgetSecret()
	if err != nil {
		problem(w, 503, "unavailable")
		return
	}
	now := time.Now().UTC()
	record := WidgetToken{
		ID:             newID(),
		AssistantID:    input.AssistantID,
		ConversationID: input.ConversationID,
		Subject:        input.Subject,
		Scopes:         append([]string(nil), widgetScopes...),
		Origin:         input.Origin,
		ExpiresAt:      now.Add(ttl),
		CreatedAt:      now,
		CreatedBy:      currentPrincipal(r.Context()).ID,
	}
	record, err = s.store.CreateWidgetToken(r.Context(), record, digest)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 201, struct {
		Token string `json:"token"`
		WidgetToken
	}{Token: token, WidgetToken: record})
}

func (s *server) revokeWidgetToken(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	if err := s.store.RevokeWidgetToken(r.Context(), id); err != nil {
		storeError(w, err)
		return
	}
	respond(w, 200, map[string]string{"status": "revoked"})
}

// widgetCORS applies only to the browser-facing conversation message routes.
// Preflight requests have no bearer token, so they are authorized by the
// configured origin allowlist and never reach s.authorize.
func (s *server) widgetCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !isWidgetMessagesPath(r.URL.Path) {
			next.ServeHTTP(w, r)
			return
		}
		origin := r.Header.Get("Origin")
		if origin == "" {
			next.ServeHTTP(w, r)
			return
		}
		if !s.originAllowed(origin) {
			problem(w, 403, "origin_forbidden")
			return
		}
		w.Header().Set("Access-Control-Allow-Origin", origin)
		w.Header().Set("Vary", "Origin")
		if r.Method == http.MethodOptions {
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type, Idempotency-Key")
			w.Header().Set("Access-Control-Max-Age", "600")
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func requireWidgetBinding(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		principal := currentPrincipal(r.Context())
		if principal.Widget != nil {
			if chi.URLParam(r, "id") != principal.Widget.ConversationID ||
				r.Header.Get("Origin") != principal.Widget.Origin {
				problem(w, 403, "forbidden")
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func isWidgetMessagesPath(path string) bool {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	return len(parts) == 4 && parts[0] == "v1" && parts[1] == "conversations" &&
		parts[2] != "" && parts[3] == "messages"
}

func (s *server) originAllowed(origin string) bool {
	for _, allowed := range s.config.WidgetOrigins {
		if allowed == origin {
			return true
		}
	}
	return false
}

func validWidgetOrigin(origin string) bool {
	if origin == "" || len(origin) > 500 {
		return false
	}
	parsed, err := url.Parse(origin)
	if err != nil || parsed.User != nil || parsed.Host == "" ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Path != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
		return false
	}
	return true
}

func parseWidgetOrigins(value string) []string {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	origins := []string{}
	for _, origin := range strings.Split(value, ",") {
		if trimmed := strings.TrimSpace(origin); trimmed != "" {
			origins = append(origins, trimmed)
		}
	}
	return origins
}

func newWidgetSecret() (string, string, error) {
	var data [32]byte
	if _, err := rand.Read(data[:]); err != nil {
		return "", "", err
	}
	token := widgetTokenPrefix + hex.EncodeToString(data[:])
	sum := sha256.Sum256([]byte(token))
	return token, hex.EncodeToString(sum[:]), nil
}

func (s *server) allowWidget(tokenID string) bool {
	return s.widgetLimiter.allow(tokenID, time.Now())
}
