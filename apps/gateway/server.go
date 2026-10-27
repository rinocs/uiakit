package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unicode/utf8"

	"github.com/go-chi/chi/v5"
)

type Config struct {
	APIKeyHash, InternalKey, RuntimeURL, Model string
	RateLimit                                  int
	RateLimitPerPrincipal                      int
	WidgetOrigins                              []string
	WidgetRateLimit                            int
	RetentionConversationDays                  int
	RetentionAuditDays                         int
	RetentionApprovalDays                      int
	RetentionCleanupDays                       int
}
type activeRun struct {
	cancel    context.CancelFunc
	cancelled atomic.Bool
}

type server struct {
	store          Store
	config         Config
	client         *http.Client
	pluginMu       sync.Mutex
	activeMu       sync.Mutex
	active         map[string]*activeRun
	globalLimiter  *rateLimiter
	principalLimit *rateLimiter
	widgetLimiter  *rateLimiter
	handler        http.Handler
	telemetry      *Telemetry
}

func NewServer(store Store, c Config) *server {
	if c.RateLimit <= 0 {
		c.RateLimit = 120
	}
	if c.RateLimitPerPrincipal <= 0 {
		c.RateLimitPerPrincipal = 120
	}
	if c.WidgetRateLimit <= 0 {
		c.WidgetRateLimit = 60
	}
	s := &server{
		store: store, config: c, client: &http.Client{Timeout: 130 * time.Second},
		active:         map[string]*activeRun{},
		globalLimiter:  newRateLimiter(c.RateLimit, 1),
		principalLimit: newRateLimiter(c.RateLimitPerPrincipal, maxRateLimitKeys),
		widgetLimiter:  newRateLimiter(c.WidgetRateLimit, maxRateLimitKeys),
		telemetry:      NewTelemetry("uai-gateway"),
	}
	r := chi.NewRouter()
	r.Use(s.widgetCORS)
	r.Use(s.telemetryMiddleware)
	r.Get("/v1/health", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if err := store.Health(ctx); err != nil {
			problem(w, 503, "unavailable")
			return
		}
		respond(w, 200, map[string]string{"status": "ok", "version": "0.1.0"})
	})
	r.Group(func(r chi.Router) {
		r.Use(s.authorize)
		r.Get("/v1/me", func(w http.ResponseWriter, r *http.Request) {
			principal := currentPrincipal(r.Context())
			respond(w, 200, map[string]any{
				"principal_id": principal.ID, "role": principal.Role, "scopes": principal.Scopes,
			})
		})
		r.With(requireScope("assistants:read")).Get("/v1/assistants", func(w http.ResponseWriter, r *http.Request) {
			a, e := store.Assistants(r.Context())
			if e != nil {
				storeError(w, e)
				return
			}
			respond(w, 200, a)
		})
		r.With(requireScope("assistants:write")).Post("/v1/assistants", s.createAssistant)
		r.With(requireScope("conversations:write")).Post("/v1/conversations", s.createConversation)
		r.With(requireScope("conversations:write")).Delete("/v1/conversations/{id}", s.deleteConversation)
		r.With(requireScope("messages:read"), requireWidgetBinding).Get("/v1/conversations/{id}/messages", s.messages)
		r.With(requireScope("messages:write"), requireWidgetBinding).Post("/v1/conversations/{id}/messages", s.run)
		s.assistantRoutes(r)
		r.With(requireScope("models:read")).Get("/v1/models", func(w http.ResponseWriter, r *http.Request) {
			models, e := s.store.Models(r.Context())
			if e != nil {
				storeError(w, e)
				return
			}
			respond(w, 200, models)
		})
		r.With(requireScope("tools:read")).Get("/v1/tools", s.tools)
		s.knowledgeBaseRoutes(r)
		s.documentRoutes(r)
		s.jobRoutes(r)
		s.exportRoutes(r)
		s.agentRunRoutes(r)
		s.approvalRoutes(r)
		s.auditRoutes(r)
		s.credentialRoutes(r)
		s.providerRoutes(r)
		s.widgetRoutes(r)
		s.pluginRoutes(r)
	})
	s.internalToolExecutionRoutes(r)
	s.internalRetentionRoutes(r)
	s.internalProviderRoutes(r)
	s.handler = r
	return s
}
func (s *server) ServeHTTP(w http.ResponseWriter, r *http.Request) { s.handler.ServeHTTP(w, r) }

func (s *server) trackRun(id string, cancel context.CancelFunc) *activeRun {
	s.activeMu.Lock()
	defer s.activeMu.Unlock()
	entry := &activeRun{cancel: cancel}
	s.active[id] = entry
	return entry
}

func (s *server) untrackRun(id string) {
	s.activeMu.Lock()
	delete(s.active, id)
	s.activeMu.Unlock()
}

func (s *server) activeRun(id string) *activeRun {
	s.activeMu.Lock()
	defer s.activeMu.Unlock()
	return s.active[id]
}

func (s *server) cancelActiveRun(id string) {
	entry := s.activeRun(id)
	if entry != nil {
		entry.cancelled.Store(true)
		entry.cancel()
	}
}
func (s *server) authorize(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		principal, err := s.authenticate(authctx, r.Header.Get("Authorization"))
		cancel()
		if err != nil {
			if errors.Is(err, ErrUnauthorized) {
				w.Header().Set("WWW-Authenticate", "Bearer")
				problem(w, 401, "unauthorized")
			} else {
				problem(w, 503, "authentication_unavailable")
			}
			return
		}
		if principal.Widget != nil {
			// Widget tokens have a dedicated per-token budget; they never consume
			// the installation-wide budget used by server-side credentials.
			if !s.widgetLimiter.allow(principal.Widget.TokenID, time.Now()) {
				w.Header().Set("Retry-After", "60")
				problem(w, 429, "rate_limited")
				return
			}
		} else {
			// Per-principal and installation-wide budgets are separate and bounded.
			if !s.principalLimit.allow(principal.ID, time.Now()) ||
				!s.globalLimiter.allow("installation", time.Now()) {
				w.Header().Set("Retry-After", "60")
				problem(w, 429, "rate_limited")
				return
			}
		}
		w.Header().Set("Cache-Control", "no-store")
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), principalKey{}, principal)))
	})
}
func decode(w http.ResponseWriter, r *http.Request, dst any) bool {
	if strings.Split(r.Header.Get("Content-Type"), ";")[0] != "application/json" {
		problem(w, 415, "content_type")
		return false
	}
	r.Body = http.MaxBytesReader(w, r.Body, 128*1024)
	d := json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	if err := d.Decode(dst); err != nil {
		problem(w, 422, "invalid_body")
		return false
	}
	if err := d.Decode(new(any)); err != io.EOF {
		problem(w, 422, "invalid_body")
		return false
	}
	return true
}
func (s *server) createAssistant(w http.ResponseWriter, r *http.Request) {
	var raw json.RawMessage
	if !decode(w, r, &raw) {
		return
	}
	a, e := applyAssistantPatch(defaultAssistant(), raw)
	if e != nil {
		storeError(w, e)
		return
	}
	if e = s.validateAssistantModel(r.Context(), a); e != nil {
		storeError(w, e)
		return
	}
	a, e = s.store.CreateAssistant(r.Context(), a)
	if e != nil {
		storeError(w, e)
		return
	}
	w.Header().Set("ETag", etag(a.Version))
	respond(w, 201, a)
}

func (s *server) createConversation(w http.ResponseWriter, r *http.Request) {
	var b struct {
		AssistantID string `json:"assistant_id"`
	}
	if !decode(w, r, &b) {
		return
	}
	if !validID(b.AssistantID) {
		problem(w, 422, "invalid_id")
		return
	}
	id, e := s.store.CreateConversation(r.Context(), b.AssistantID)
	if e != nil {
		storeError(w, e)
		return
	}
	respond(w, 201, map[string]string{"id": id, "assistant_id": b.AssistantID})
}
func (s *server) messages(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	m, e := s.store.Messages(r.Context(), id)
	if e != nil {
		storeError(w, e)
		return
	}
	respond(w, 200, m)
}
func validID(id string) bool {
	if len(id) != 36 {
		return false
	}
	for i, c := range id {
		if i == 8 || i == 13 || i == 18 || i == 23 {
			if c != '-' {
				return false
			}
		} else if !strings.ContainsRune("0123456789abcdef", c) {
			return false
		}
	}
	return true
}
func (s *server) run(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	key := r.Header.Get("Idempotency-Key")
	if !validID(id) || len(key) < 1 || len(key) > 128 {
		problem(w, 422, "invalid_id_or_idempotency_key")
		return
	}
	var b struct {
		Content string `json:"content"`
	}
	if !decode(w, r, &b) {
		return
	}
	if strings.TrimSpace(b.Content) == "" || len(b.Content) > 32000 {
		problem(w, 422, "invalid_content")
		return
	}
	run, e := s.store.Start(r.Context(), id, key, b.Content)
	if e != nil {
		storeError(w, e)
		return
	}
	w.Header().Set("X-Run-ID", run.ID)
	if run.AssistantConfig.Version > 0 {
		w.Header().Set("X-Assistant-Version", strconv.Itoa(run.AssistantConfig.Version))
	}
	if run.Status != "running" {
		s.replay(w, run.Events)
		return
	}
	if run.CorrelationID == "" {
		run.CorrelationID = newID()
	}
	ctx, cancel := context.WithTimeout(r.Context(), 125*time.Second)
	defer cancel()
	active := s.trackRun(run.ID, cancel)
	defer s.untrackRun(run.ID)
	finalized := false
	var events []Event
	defer func() {
		if !finalized {
			cleanup, c := context.WithTimeout(context.Background(), 5*time.Second)
			defer c()
			if err := s.store.Finish(cleanup, run, events, "failed"); err != nil {
				log.Printf("run %s: failed to persist interrupted execution", run.ID)
			}
		}
	}()
	if err := s.ensurePlugins(ctx); err != nil {
		storeError(w, err)
		return
	}
	ctx, runSpan := s.telemetry.StartRun(ctx, run.ID, run.CorrelationID, run.Model)
	defer runSpan.End()
	slog.Info("run_started", "run_id", run.ID, "correlation_id", run.CorrelationID,
		"model", run.Model, "trace_id", s.telemetry.TraceID(ctx))
	allowedToolIDs := []string{}
	if currentPrincipal(r.Context()).allows("tools:execute") {
		allowedToolIDs = append(allowedToolIDs, run.AssistantConfig.Tools...)
	}
	body, _ := json.Marshal(map[string]any{"run_id": run.ID, "correlation_id": run.CorrelationID, "model": run.Model, "system_prompt": run.SystemPrompt, "messages": run.Messages, "assistant": run.AssistantConfig, "model_snapshot": run.ModelSnapshot, "retrieval_targets": run.RetrievalTargets, "authority": map[string]any{"principal_id": currentPrincipal(r.Context()).ID, "scopes": currentPrincipal(r.Context()).Scopes, "allowed_tool_ids": allowedToolIDs}})
	req, e := http.NewRequestWithContext(ctx, "POST", s.config.RuntimeURL+"/internal/v1/runs", bytes.NewReader(body))
	if e != nil {
		problem(w, 502, "runtime_unavailable")
		return
	}
	req.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	req.Header.Set("Content-Type", "application/json")
	s.telemetry.Inject(ctx, req.Header)
	resp, e := s.client.Do(req)
	if e != nil {
		problem(w, 502, "runtime_unavailable")
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 || !strings.HasPrefix(resp.Header.Get("Content-Type"), "text/event-stream") {
		problem(w, 502, "runtime_unavailable")
		return
	}
	if traceID := resp.Header.Get("X-Trace-ID"); traceID != "" {
		w.Header().Set("X-Trace-ID", traceID)
	}
	sseHeaders(w)
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 4096), 512*1024)
	total := 0
	terminal := false
	var text strings.Builder
	outputChars := 0
	seen := make(map[string]bool)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		var event Event
		if json.Unmarshal([]byte(strings.TrimSpace(line[5:])), &event) != nil || event.Version != 1 || event.RunID != run.ID || !validID(event.ID) || event.CorrelationID != run.CorrelationID || event.Timestamp.IsZero() || seen[event.ID] {
			break
		}
		var payload struct {
			Text  string         `json:"text"`
			Code  string         `json:"code"`
			Usage map[string]int `json:"usage"`
		}
		if json.Unmarshal(event.Payload, &payload) != nil {
			break
		}
		valid := true
		switch event.Type {
		case "agent.started":
			valid = len(events) == 0
		case "response.delta":
			valid = len(events) > 0 && payload.Text != ""
			outputChars += utf8.RuneCountInString(payload.Text)
			if outputChars > 64000 {
				valid = false
			}
			if valid {
				text.WriteString(payload.Text)
			}
		case "response.completed":
			valid = len(events) > 0 && payload.Text != "" && payload.Text == text.String()
		case "agent.failed":
			valid = len(events) > 0 && payload.Code != ""
		case "agent.cancelled":
			valid = len(events) > 0 && payload.Code != ""
		default:
			valid = false
		}
		if !valid {
			break
		}
		if active != nil && active.cancelled.Load() && event.Type != "agent.cancelled" &&
			(event.Type == "response.completed" || event.Type == "agent.failed") {
			break
		}
		seen[event.ID] = true
		total += len(line)
		if total > 2*1024*1024 || len(events) >= 4096 {
			break
		}
		events = append(events, event)
		terminal = event.Type == "response.completed" || event.Type == "agent.failed" ||
			event.Type == "agent.cancelled"
		if terminal {
			status := "completed"
			if event.Type == "agent.failed" {
				status = "failed"
			} else if event.Type == "agent.cancelled" {
				status = "cancelled"
			}
			cleanup, c := context.WithTimeout(context.Background(), 5*time.Second)
			err := s.store.Finish(cleanup, run, events, status)
			c()
			if err != nil {
				break
			}
			finalized = true
		}
		if err := writeEvent(w, event); err != nil {
			return
		}
		if terminal {
			return
		}
	}
	if active != nil && active.cancelled.Load() && !finalized {
		cancelled := Event{ID: newID(), Type: "agent.cancelled", Version: 1, Timestamp: time.Now().UTC(),
			RunID: run.ID, CorrelationID: run.CorrelationID, Payload: json.RawMessage(`{"code":"cancelled"}`)}
		if terminal && len(events) > 0 {
			events = events[:len(events)-1]
		}
		events = append(events, cancelled)
		cleanup, c := context.WithTimeout(context.Background(), 5*time.Second)
		err := s.store.Finish(cleanup, run, events, "cancelled")
		c()
		if err == nil {
			finalized = true
			writeEvent(w, cancelled)
		}
		return
	}
	failed := Event{ID: newID(), Type: "agent.failed", Version: 1, Timestamp: time.Now().UTC(), RunID: run.ID, CorrelationID: run.CorrelationID, Payload: json.RawMessage(`{"code":"runtime_stream_failed"}`)}
	// Discard an uncommitted terminal event if persistence failed.
	if terminal && len(events) > 0 {
		events = events[:len(events)-1]
	}
	events = append(events, failed)
	cleanup, c := context.WithTimeout(context.Background(), 5*time.Second)
	err := s.store.Finish(cleanup, run, events, "failed")
	c()
	if err == nil {
		finalized = true
		writeEvent(w, failed)
	}
}
func (s *server) replay(w http.ResponseWriter, events []Event) {
	sseHeaders(w)
	for _, e := range events {
		if writeEvent(w, e) != nil {
			return
		}
	}
}
func sseHeaders(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Accel-Buffering", "no")
}

const streamWriteTimeout = 15 * time.Second

// writeEvent is the production path; slow clients are bounded by the write
// deadline so they cannot pin a gateway handler or its upstream connection.
func writeEvent(w http.ResponseWriter, e Event) error {
	return writeEventWithTimeout(w, e, streamWriteTimeout)
}

func writeEventWithTimeout(w http.ResponseWriter, e Event, timeout time.Duration) error {
	// JSONB may reorder object keys. Canonicalize payloads on both first delivery
	// and replay so an idempotent response remains byte-for-byte stable.
	var payload any
	decoder := json.NewDecoder(bytes.NewReader(e.Payload))
	decoder.UseNumber()
	if err := decoder.Decode(&payload); err != nil {
		return err
	}
	canonical, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	e.Payload = canonical
	b, err := json.Marshal(e)
	if err != nil {
		return err
	}
	if err = http.NewResponseController(w).SetWriteDeadline(time.Now().Add(timeout)); err != nil && !errors.Is(err, http.ErrNotSupported) {
		return err
	}
	_, err = fmt.Fprintf(w, "id: %s\nevent: %s\ndata: %s\n\n", e.ID, e.Type, b)
	if err == nil {
		err = http.NewResponseController(w).Flush()
	}
	return err
}
func respond(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
func problem(w http.ResponseWriter, status int, code string) {
	respond(w, status, map[string]string{"error": code})
}
func storeError(w http.ResponseWriter, e error) {
	if errors.Is(e, ErrDirectiveRuntimeUnavailable) {
		problem(w, 503, "runtime_unavailable")
	} else if errors.Is(e, ErrInvalidConfig) {
		problem(w, 422, "invalid_configuration")
	} else if errors.Is(e, ErrPreconditionFailed) {
		problem(w, 412, "version_conflict")
	} else if errors.Is(e, ErrUnauthorized) {
		problem(w, 401, "unauthorized")
	} else if errors.Is(e, ErrForbidden) {
		problem(w, 403, "forbidden")
	} else if errors.Is(e, ErrNotFound) {
		problem(w, 404, "not_found")
	} else if errors.Is(e, ErrExportTooLarge) {
		problem(w, 413, "export_too_large")
	} else if errors.Is(e, ErrConflict) {
		problem(w, 409, "conflict")
	} else {
		problem(w, 503, "storage_unavailable")
	}
}
