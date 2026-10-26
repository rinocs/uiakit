package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"net/http"
	"slices"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

var ErrUnauthorized = errors.New("unauthorized")
var ErrForbidden = errors.New("forbidden")

const bootstrapPrincipal = "bootstrap-operator"

var roleScopes = map[string][]string{
	"reader":   {"agent-runs:read", "documents:read", "knowledge-bases:read", "tools:read", "models:read", "assistants:read", "conversations:read", "messages:read"},
	"operator": {"agent-runs:read", "agent-runs:write", "approvals:read", "approvals:write", "documents:read", "documents:write", "knowledge-bases:read", "knowledge-bases:write", "tools:read", "tools:execute", "models:read", "assistants:read", "assistants:write", "conversations:read", "conversations:write", "messages:read", "messages:write", "widget-tokens:write"},
	"admin":    {"agent-runs:read", "agent-runs:write", "approvals:read", "approvals:write", "audit:read", "documents:read", "documents:write", "knowledge-bases:read", "knowledge-bases:write", "plugins:read", "plugins:write", "tools:read", "tools:execute", "models:read", "assistants:read", "assistants:write", "conversations:read", "conversations:write", "messages:read", "messages:write", "widget-tokens:write", "credentials:read", "credentials:write"},
	"widget":   {"messages:read", "messages:write"},
}

type Principal struct {
	ID           string
	CredentialID string
	Role         string
	Scopes       []string
	Widget       *WidgetBinding
}

func (p Principal) allows(scope string) bool {
	return slices.Contains(roleScopes[p.Role], scope) && slices.Contains(p.Scopes, scope)
}
func (p Principal) isAdmin() bool { return p.Role == "admin" }

type principalKey struct{}

func currentPrincipal(ctx context.Context) Principal {
	p, _ := ctx.Value(principalKey{}).(Principal)
	return p
}

type Credential struct {
	ID          string     `json:"id"`
	PrincipalID string     `json:"principal_id"`
	Role        string     `json:"role"`
	Scopes      []string   `json:"scopes"`
	ExpiresAt   time.Time  `json:"expires_at"`
	RevokedAt   *time.Time `json:"revoked_at"`
	CreatedAt   time.Time  `json:"created_at"`
}
type CredentialStore interface {
	Authenticate(context.Context, string) (Principal, error)
	Credentials(context.Context) ([]Credential, error)
	CreateCredential(context.Context, Credential, string) (Credential, error)
	RotateCredential(context.Context, string, string, time.Time) (Credential, error)
	RevokeCredential(context.Context, string) error
}

func (s *server) authenticate(ctx context.Context, header string) (Principal, error) {
	token, ok := strings.CutPrefix(header, "Bearer ")
	if !ok || len(token) == 0 || len(token) > 512 {
		return Principal{}, ErrUnauthorized
	}
	hash := sha256.Sum256([]byte(token))
	if strings.HasPrefix(token, widgetTokenPrefix) {
		return s.store.AuthenticateWidget(ctx, hex.EncodeToString(hash[:]))
	}
	expected, e := hex.DecodeString(s.config.APIKeyHash)
	if e == nil && len(expected) == 32 && subtle.ConstantTimeCompare(hash[:], expected) == 1 {
		return Principal{ID: bootstrapPrincipal, Role: "admin", Scopes: slices.Clone(roleScopes["admin"])}, nil
	}
	return s.store.Authenticate(ctx, hex.EncodeToString(hash[:]))
}
func requireScope(scope string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !currentPrincipal(r.Context()).allows(scope) {
				problem(w, 403, "forbidden")
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
func validScopes(role string, scopes []string) bool {
	allowed, ok := roleScopes[role]
	if !ok || len(scopes) == 0 {
		return false
	}
	seen := map[string]bool{}
	for _, scope := range scopes {
		if !slices.Contains(allowed, scope) || seen[scope] {
			return false
		}
		seen[scope] = true
	}
	return true
}
func credentialExpiry(value *time.Time) (time.Time, bool) {
	now := time.Now().UTC()
	if value == nil {
		return now.Add(30 * 24 * time.Hour), true
	}
	return value.UTC(), value.After(now) && !value.After(now.Add(365*24*time.Hour))
}
func newCredentialSecret() (string, string, error) {
	var data [32]byte
	if _, err := rand.Read(data[:]); err != nil {
		return "", "", err
	}
	token := hex.EncodeToString(data[:])
	sum := sha256.Sum256([]byte(token))
	return token, hex.EncodeToString(sum[:]), nil
}
func (s *server) credentialRoutes(r chi.Router) {
	r.With(requireScope("credentials:read")).Get("/v1/credentials", func(w http.ResponseWriter, r *http.Request) {
		rows, e := s.store.Credentials(r.Context())
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, rows)
	})
	r.With(requireScope("credentials:write")).Post("/v1/credentials", s.createCredential)
	r.With(requireScope("credentials:write")).Post("/v1/credentials/{id}/rotate", s.rotateCredential)
	r.With(requireScope("credentials:write")).Post("/v1/credentials/{id}/revoke", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		if id == currentPrincipal(r.Context()).CredentialID {
			problem(w, 409, "cannot_revoke_current_credential")
			return
		}
		if err := s.store.RevokeCredential(r.Context(), id); err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, map[string]string{"status": "revoked"})
	})
}
func (s *server) createCredential(w http.ResponseWriter, r *http.Request) {
	var input struct {
		PrincipalID string     `json:"principal_id"`
		Role        string     `json:"role"`
		Scopes      []string   `json:"scopes"`
		ExpiresAt   *time.Time `json:"expires_at"`
	}
	if !decode(w, r, &input) {
		return
	}
	expiry, ok := credentialExpiry(input.ExpiresAt)
	if !ok || len(input.PrincipalID) > 200 || !validScopes(input.Role, input.Scopes) {
		problem(w, 422, "invalid_credential")
		return
	}
	token, digest, err := newCredentialSecret()
	if err != nil {
		problem(w, 503, "unavailable")
		return
	}
	c := Credential{ID: newID(), PrincipalID: input.PrincipalID, Role: input.Role, Scopes: slices.Clone(input.Scopes), ExpiresAt: expiry, CreatedAt: time.Now().UTC()}
	c, err = s.store.CreateCredential(r.Context(), c, digest)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 201, map[string]any{"credential": c, "api_key": token})
}
func (s *server) rotateCredential(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	if id == currentPrincipal(r.Context()).CredentialID {
		problem(w, 409, "cannot_rotate_current_credential")
		return
	}
	var input struct {
		ExpiresAt *time.Time `json:"expires_at"`
	}
	if !decode(w, r, &input) {
		return
	}
	expiry, ok := credentialExpiry(input.ExpiresAt)
	if !ok {
		problem(w, 422, "invalid_expiry")
		return
	}
	token, digest, err := newCredentialSecret()
	if err != nil {
		problem(w, 503, "unavailable")
		return
	}
	c, err := s.store.RotateCredential(r.Context(), id, digest, expiry)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 200, map[string]any{"credential": c, "api_key": token})
}
