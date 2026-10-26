package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

type memoryStore struct {
	pluginConfig    PluginConfiguration
	calls           int
	run             Run
	events          []Event
	failCompletion  bool
	approvalMu      sync.Mutex
	approvals       map[string]Approval
	runStatus       map[string]string
	toolExecutionMu sync.Mutex
	toolExecutions  map[string]ToolExecution
	audits          []AuditEvent
	widgetMu        sync.Mutex
	widgetTokens    map[string]WidgetToken
	widgetDigests   map[string]string
}

func (s *memoryStore) AuditEvents(_ context.Context, filter AuditFilter) ([]AuditEvent, error) {
	if filter.Limit == 0 {
		filter.Limit = 100
	}
	out := []AuditEvent{}
	for i := len(s.audits) - 1; i >= 0 && len(out) < filter.Limit; i-- {
		event := s.audits[i]
		if filter.RunID != "" && event.RunID != filter.RunID {
			continue
		}
		if filter.Action != "" && event.Action != filter.Action {
			continue
		}
		if filter.TargetID != "" && event.TargetID != filter.TargetID {
			continue
		}
		event.Details = redactedAuditJSON(event.Details)
		out = append(out, event)
	}
	return out, nil
}

func (s *memoryStore) WidgetTarget(context.Context, string, string) error { return nil }
func (s *memoryStore) CreateWidgetToken(_ context.Context, token WidgetToken, digest string) (WidgetToken, error) {
	s.widgetMu.Lock()
	defer s.widgetMu.Unlock()
	if s.widgetTokens == nil {
		s.widgetTokens = map[string]WidgetToken{}
		s.widgetDigests = map[string]string{}
	}
	s.widgetTokens[token.ID] = token
	s.widgetDigests[digest] = token.ID
	return token, nil
}
func (s *memoryStore) AuthenticateWidget(_ context.Context, digest string) (Principal, error) {
	s.widgetMu.Lock()
	defer s.widgetMu.Unlock()
	id, ok := s.widgetDigests[digest]
	if !ok {
		return Principal{}, ErrUnauthorized
	}
	token := s.widgetTokens[id]
	if token.RevokedAt != nil || !token.ExpiresAt.After(time.Now()) {
		return Principal{}, ErrUnauthorized
	}
	return Principal{ID: "widget:" + token.ID, Role: "widget", Scopes: token.Scopes, Widget: &WidgetBinding{TokenID: token.ID, AssistantID: token.AssistantID, ConversationID: token.ConversationID, Origin: token.Origin}}, nil
}
func (s *memoryStore) RevokeWidgetToken(_ context.Context, id string) error {
	s.widgetMu.Lock()
	defer s.widgetMu.Unlock()
	token, ok := s.widgetTokens[id]
	if !ok {
		return ErrNotFound
	}
	now := time.Now()
	token.RevokedAt = &now
	s.widgetTokens[id] = token
	return nil
}
func (*memoryStore) DeleteConversation(context.Context, string) error { return nil }
func (*memoryStore) RunRetention(context.Context, RetentionPolicy) (RetentionResult, error) {
	return RetentionResult{}, nil
}
func (*memoryStore) Health(context.Context) error                    { return nil }
func (*memoryStore) Assistants(context.Context) ([]Assistant, error) { return []Assistant{}, nil }
func (*memoryStore) CreateAssistant(_ context.Context, a Assistant) (Assistant, error) {
	a.ID = "00000000-0000-4000-8000-000000000001"
	a.Version = 1
	return a, nil
}
func (*memoryStore) CreateConversation(context.Context, string) (string, error) {
	return "00000000-0000-4000-8000-000000000002", nil
}
func (*memoryStore) Messages(context.Context, string) ([]Message, error) { return []Message{}, nil }
func (s *memoryStore) Start(_ context.Context, id, key, content string) (Run, error) {
	s.calls++
	if s.run.ID != "" {
		if s.run.Content != content {
			return Run{}, ErrConflict
		}
		s.run.Events = s.events
		s.run.Status = "completed"
		return s.run, nil
	}
	config := defaultAssistant()
	config.ID = "00000000-0000-4000-8000-000000000001"
	config.Version = 1
	config.Name = "Test"
	config.Model = "test"
	config.SystemPrompt = "Helpful"
	s.run = Run{ID: "00000000-0000-4000-8000-000000000003", ConversationID: id, Content: content, Model: "test", SystemPrompt: "Helpful", Messages: []Message{{Role: "user", Content: content}}, Status: "running", CorrelationID: newID(), AssistantConfig: config, ModelSnapshot: &ModelDefinition{ID: "test", Provider: "openai-compatible", Capabilities: []string{"chat", "streaming"}}}
	return s.run, nil
}
func (s *memoryStore) Finish(_ context.Context, _ Run, events []Event, status string) error {
	if s.failCompletion && status == "completed" {
		return errors.New("disk unavailable")
	}
	s.events = events
	return nil
}

type roundTrip func(*http.Request) (*http.Response, error)

func (f roundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func setup(t *testing.T) (*memoryStore, *server) {
	t.Helper()
	store := &memoryStore{}
	digest := sha256.Sum256([]byte("test-key"))
	s := NewServer(store, Config{APIKeyHash: hex.EncodeToString(digest[:]), InternalKey: "internal-secret", RuntimeURL: "http://runtime", Model: "test"})
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		if r.Header.Get("Authorization") != "Bearer internal-secret" {
			t.Error("missing internal auth")
		}
		var input struct {
			CorrelationID string `json:"correlation_id"`
		}
		json.NewDecoder(r.Body).Decode(&input)
		var frames strings.Builder
		for i, kind := range []string{"agent.started", "response.delta", "response.completed"} {
			payload := json.RawMessage(`{}`)
			if i > 0 {
				payload = json.RawMessage(`{"text":"Ciao"}`)
			}
			e := Event{ID: newID(), Type: kind, Version: 1, Timestamp: time.Now().UTC(), RunID: store.run.ID, CorrelationID: input.CorrelationID, Payload: payload}
			data, _ := json.Marshal(e)
			frames.WriteString("data: " + string(data) + "\n\n")
		}
		body := frames.String()
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader(body))}, nil
	})
	return store, s
}
func post(t *testing.T, s http.Handler, path, body, key string) *http.Response {
	t.Helper()
	req := httptest.NewRequest("POST", path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer test-key")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", key)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w.Result()
}
func TestAuthenticationAndValidation(t *testing.T) {
	_, s := setup(t)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, httptest.NewRequest("GET", "/v1/assistants", nil))
	r := w.Result()
	if r.StatusCode != 401 {
		t.Fatal(r.StatusCode)
	}
	r = post(t, s, "/v1/assistants", `{"name":"A","model":"test","system_prompt":"Helpful","unknown":true}`, "")
	if r.StatusCode != 422 {
		t.Fatal(r.StatusCode)
	}
	r = post(t, s, "/v1/assistants", `{"name":"A","model":"unapproved","system_prompt":"Helpful"}`, "")
	if r.StatusCode != 422 {
		t.Fatal(r.StatusCode)
	}
}
func TestStreamingReplayConflict(t *testing.T) {
	store, s := setup(t)
	url := "/v1/conversations/00000000-0000-4000-8000-000000000002/messages"
	r := post(t, s, url, `{"content":"Ciao"}`, "key-1")
	if r.StatusCode != 200 {
		t.Fatal(r.StatusCode)
	}
	first := readAll(t, r.Body)
	if !strings.Contains(first, "response.completed") || !strings.Contains(first, "Ciao") {
		t.Fatal(first)
	}
	r = post(t, s, url, `{"content":"Ciao"}`, "key-1")
	if second := readAll(t, r.Body); second != first {
		t.Fatalf("replay differs: %s", second)
	}
	r = post(t, s, url, `{"content":"Different"}`, "key-1")
	if r.StatusCode != 409 {
		t.Fatal(r.StatusCode)
	}
	if len(store.events) != 3 {
		t.Fatalf("events not persisted: %d", len(store.events))
	}
}

func readAll(t *testing.T, r io.Reader) string {
	t.Helper()
	b, err := io.ReadAll(r)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestTruncatedStreamFailsAndPersists(t *testing.T) {
	store, s := setup(t)
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader("data: invalid\n\n"))}, nil
	})
	r := post(t, s, "/v1/conversations/00000000-0000-4000-8000-000000000002/messages", `{"content":"Hello"}`, "key")
	body := readAll(t, r.Body)
	if !strings.Contains(body, "agent.failed") || strings.Contains(body, "response.completed") {
		t.Fatal(body)
	}
	if len(store.events) != 1 || store.events[0].Type != "agent.failed" {
		t.Fatal("failure not persisted")
	}
}
func TestMessageRequiresIdempotencyAndRejectsOversize(t *testing.T) {
	store, s := setup(t)
	path := "/v1/conversations/00000000-0000-4000-8000-000000000002/messages"
	r := post(t, s, path, `{"content":"Hello"}`, "")
	if r.StatusCode != 422 {
		t.Fatal(r.StatusCode)
	}
	r = post(t, s, path, `{"content":"`+strings.Repeat("x", 32001)+`"}`, "key")
	if r.StatusCode != 422 {
		t.Fatal(r.StatusCode)
	}
	if store.calls != 0 {
		t.Fatal("invalid input reached storage")
	}
}

func TestPersistenceFailureDoesNotExposeCompletion(t *testing.T) {
	store, s := setup(t)
	store.failCompletion = true
	r := post(t, s, "/v1/conversations/00000000-0000-4000-8000-000000000002/messages", `{"content":"Hello"}`, "key")
	body := readAll(t, r.Body)
	if strings.Contains(body, "response.completed") || !strings.Contains(body, "agent.failed") {
		t.Fatal(body)
	}
}
func TestMismatchedCompletionFails(t *testing.T) {
	_, s := setup(t)
	original := s.client.Transport
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		response, e := original.RoundTrip(r)
		if e != nil {
			return response, e
		}
		b, _ := io.ReadAll(response.Body)
		response.Body.Close()
		text := string(b)
		index := strings.LastIndex(text, `"text":"Ciao"`)
		text = text[:index] + strings.Replace(text[index:], `"text":"Ciao"`, `"text":"Corrupted"`, 1)
		response.Body = io.NopCloser(strings.NewReader(text))
		return response, nil
	})
	r := post(t, s, "/v1/conversations/00000000-0000-4000-8000-000000000002/messages", `{"content":"Hello"}`, "key")
	body := readAll(t, r.Body)
	if strings.Contains(body, "response.completed") || !strings.Contains(body, "agent.failed") {
		t.Fatal(body)
	}
}

func TestEventReplayCanonicalizesJSONBKeyOrder(t *testing.T) {
	a := Event{ID: newID(), Type: "response.completed", Version: 1, Timestamp: time.Now().UTC(), RunID: newID(), CorrelationID: newID(), Payload: json.RawMessage(`{"text":"Ciao","usage":{"prompt_tokens":5,"completion_tokens":4,"total_tokens":9}}`)}
	b := a
	b.Payload = json.RawMessage(`{"text":"Ciao","usage":{"total_tokens":9,"prompt_tokens":5,"completion_tokens":4}}`)
	first, second := httptest.NewRecorder(), httptest.NewRecorder()
	if e := writeEvent(first, a); e != nil {
		t.Fatal(e)
	}
	if e := writeEvent(second, b); e != nil {
		t.Fatal(e)
	}
	if first.Body.String() != second.Body.String() {
		t.Fatal("JSONB key reordering changed replay")
	}
}

func (*memoryStore) Authenticate(context.Context, string) (Principal, error) {
	return Principal{}, ErrUnauthorized
}
func (*memoryStore) Credentials(context.Context) ([]Credential, error) { return []Credential{}, nil }
func (*memoryStore) CreateCredential(context.Context, Credential, string) (Credential, error) {
	return Credential{}, nil
}
func (*memoryStore) RotateCredential(context.Context, string, string, time.Time) (Credential, error) {
	return Credential{}, nil
}
func (*memoryStore) RevokeCredential(context.Context, string) error { return nil }

func (*memoryStore) AgentRuns(context.Context) ([]AgentRun, error) { return []AgentRun{}, nil }
func (*memoryStore) AgentRun(context.Context, string) (AgentRun, error) {
	return AgentRun{}, ErrNotFound
}
func (*memoryStore) CancelAgentRun(context.Context, string) (AgentRun, error) {
	return AgentRun{}, ErrNotFound
}

func (*memoryStore) Documents(context.Context, string) ([]Document, error) {
	return []Document{}, nil
}
func (*memoryStore) Document(context.Context, string) (Document, error) {
	return Document{}, ErrNotFound
}
func (*memoryStore) DocumentByHash(context.Context, string, string) (Document, error) {
	return Document{}, ErrNotFound
}
func (*memoryStore) CreateDocument(context.Context, Document) (Document, bool, error) {
	return Document{}, false, ErrNotFound
}
func (*memoryStore) DeleteDocument(context.Context, string) (Document, error) {
	return Document{}, ErrNotFound
}
func (*memoryStore) DocumentJob(context.Context, string) (DocumentJob, error) {
	return DocumentJob{}, ErrNotFound
}
func (*memoryStore) CancelDocumentJob(context.Context, string) (DocumentJob, error) {
	return DocumentJob{}, ErrNotFound
}

func (*memoryStore) KnowledgeBases(context.Context) ([]KnowledgeBase, error) {
	return []KnowledgeBase{}, nil
}
func (*memoryStore) KnowledgeBase(context.Context, string) (KnowledgeBase, error) {
	return KnowledgeBase{}, ErrNotFound
}
func (*memoryStore) KnowledgeBaseVersions(context.Context, string) ([]KnowledgeBaseVersion, error) {
	return []KnowledgeBaseVersion{}, nil
}
func (*memoryStore) KnowledgeBaseExport(context.Context, string) (KnowledgeBaseExport, error) {
	return KnowledgeBaseExport{}, ErrNotFound
}
func (*memoryStore) CreateKnowledgeBase(context.Context, string, string, KnowledgeBaseConfig, *KnowledgeBaseEmbedding) (KnowledgeBase, error) {
	return KnowledgeBase{}, ErrNotFound
}
func (*memoryStore) UpdateKnowledgeBase(context.Context, string, int, KnowledgeBase) (KnowledgeBase, error) {
	return KnowledgeBase{}, ErrNotFound
}
func (*memoryStore) DeleteKnowledgeBase(context.Context, string, int) error { return ErrNotFound }
func (*memoryStore) CreateKnowledgeBaseVersion(context.Context, string, int, KnowledgeBaseConfig, *KnowledgeBaseEmbedding) (KnowledgeBase, KnowledgeBaseVersion, error) {
	return KnowledgeBase{}, KnowledgeBaseVersion{}, ErrNotFound
}

func (*memoryStore) Models(context.Context) ([]ModelDefinition, error) {
	return []ModelDefinition{{ID: "test", Provider: "openai-compatible", Capabilities: []string{"chat", "streaming"}}}, nil
}
func (*memoryStore) Assistant(context.Context, string) (Assistant, error) {
	return Assistant{}, ErrNotFound
}
func (*memoryStore) AssistantVersions(context.Context, string) ([]Assistant, error) {
	return []Assistant{}, nil
}
func (*memoryStore) UpdateAssistant(context.Context, string, int, json.RawMessage) (Assistant, error) {
	return Assistant{}, ErrNotFound
}

func (s *memoryStore) PluginConfiguration(context.Context) (PluginConfiguration, error) {
	if s.pluginConfig.Revision == 0 {
		return PluginConfiguration{Revision: 1, Settings: map[string]PluginSetting{}}, nil
	}
	data, _ := json.Marshal(s.pluginConfig)
	var result PluginConfiguration
	json.Unmarshal(data, &result)
	return result, nil
}
func (s *memoryStore) UpdatePluginConfiguration(ctx context.Context, expected int, settings map[string]PluginSetting) (PluginConfiguration, error) {
	current, _ := s.PluginConfiguration(ctx)
	if current.Revision != expected {
		return current, ErrPreconditionFailed
	}
	s.pluginConfig = PluginConfiguration{Revision: expected + 1, Settings: settings}
	return s.PluginConfiguration(ctx)
}
