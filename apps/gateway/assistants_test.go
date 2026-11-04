package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

type versionStore struct {
	memoryStore
	assistant       Assistant
	versions       []Assistant
	models         []ModelDefinition
	providerManaged bool
	providerConfig  ProviderConfiguration
}

func (s *versionStore) Models(ctx context.Context) ([]ModelDefinition, error) {
	if s.models != nil {
		return s.models, nil
	}
	return s.memoryStore.Models(ctx)
}

func (s *versionStore) ProviderConfiguration(ctx context.Context) (ProviderConfiguration, error) {
	if s.providerManaged {
		return s.providerConfig, nil
	}
	return s.memoryStore.ProviderConfiguration(ctx)
}

func (s *versionStore) Assistant(_ context.Context, id string) (Assistant, error) {
	if s.assistant.ID != id {
		return Assistant{}, ErrNotFound
	}
	return s.assistant, nil
}
func (s *versionStore) AssistantVersions(ctx context.Context, id string) ([]Assistant, error) {
	if _, e := s.Assistant(ctx, id); e != nil {
		return nil, e
	}
	return s.versions, nil
}
func (s *versionStore) UpdateAssistant(_ context.Context, id string, expected int, patch json.RawMessage) (Assistant, error) {
	if expected != s.assistant.Version {
		return Assistant{}, ErrPreconditionFailed
	}
	next, e := applyAssistantPatch(s.assistant, patch)
	if e != nil {
		return Assistant{}, e
	}
	next.Version++
	s.assistant = next
	s.versions = append(s.versions, next)
	return next, nil
}
func versionSetup(t *testing.T) (*versionStore, *server) {
	t.Helper()
	_, base := setup(t)
	a := defaultAssistant()
	a.ID = "00000000-0000-4000-8000-000000000001"
	a.Name = "Original"
	a.Model = "test"
	a.Version = 1
	store := &versionStore{assistant: a, versions: []Assistant{a}}
	return store, NewServer(store, base.config)
}
func TestAssistantPatchRequiresVersionAndKeepsHistory(t *testing.T) {
	store, s := versionSetup(t)
	path := "/v1/assistants/" + store.assistant.ID
	request := func(method, body, etag string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, path, strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer test-key")
		r.Header.Set("Content-Type", "application/json")
		if etag != "" {
			r.Header.Set("If-Match", etag)
		}
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		return w
	}
	if w := request("GET", "", ""); w.Code != 200 || w.Header().Get("ETag") != `"1"` {
		t.Fatal(w.Code, w.Body)
	}
	if w := request("PATCH", `{"name":"Changed"}`, ""); w.Code != 428 {
		t.Fatal(w.Code, w.Body)
	}
	if w := request("PATCH", `{"name":"Changed"}`, `"1"`); w.Code != 200 || w.Header().Get("ETag") != `"2"` {
		t.Fatal(w.Code, w.Body)
	}
	if w := request("PATCH", `{"name":"Overwrite"}`, `"1"`); w.Code != 412 {
		t.Fatal(w.Code, w.Body)
	}
	if store.versions[0].Name != "Original" || store.versions[1].Name != "Changed" {
		t.Fatal(store.versions)
	}
}
func TestAssistantPatchRejectsUnsupportedOrPrivilegedFields(t *testing.T) {
	_, s := versionSetup(t)
	for _, body := range []string{`{"id":"override"}`, `{"version":5}`, `{"owner_id":"other"}`, `{"tools":["Bad Tool"]}`, `{"memory":{"semantic":true}}`, `{"name":null}`, `{"limits":{"duration_seconds":121}}`} {
		r := httptest.NewRequest("PATCH", "/v1/assistants/00000000-0000-4000-8000-000000000001", strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer test-key")
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("If-Match", `"1"`)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != 422 {
			t.Fatalf("%s: %d %s", body, w.Code, w.Body)
		}
	}
}
func TestModelCatalogRequiresScope(t *testing.T) {
	_, s := versionSetup(t)
	r := httptest.NewRequest("GET", "/v1/models", nil)
	r.Header.Set("Authorization", "Bearer test-key")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatal(w.Code, w.Body)
	}
	var models []ModelDefinition
	if e := json.Unmarshal(w.Body.Bytes(), &models); e != nil {
		t.Fatal(e)
	}
	if len(models) != 1 || models[0].ID != "test" {
		t.Fatal(models)
	}
}

func TestSharedAssistantConfigurationFixture(t *testing.T) {
	data, e := os.ReadFile("../../packages/api-contract/fixtures/assistant-v1.json")
	if e != nil {
		t.Fatal(e)
	}
	var a Assistant
	if e = json.Unmarshal(data, &a); e != nil {
		t.Fatal(e)
	}
	if e = a.validate(); e != nil {
		t.Fatal(e)
	}
	original := a
	updated, e := applyAssistantPatch(a, json.RawMessage(`{"limits":{"max_output_chars":10}}`))
	if e != nil {
		t.Fatal(e)
	}
	if updated.Limits.MaxInputChars != 64000 || updated.Limits.MaxOutputChars != 10 || original.Limits.MaxOutputChars != 64000 {
		t.Fatal("patch changed original snapshot or erased omitted fields")
	}
}
func TestModelsCannotBeReadWithoutScope(t *testing.T) {
	_, s := authSetup(t, "reader", []string{"assistants:read"})
	w := scopedRequest(s, "GET", "/v1/models", "")
	if w.Code != 403 {
		t.Fatal(w.Code)
	}
}

func TestAssistantPatchAcceptsDeclaredTools(t *testing.T) {
	store, s := versionSetup(t)
	store.models = []ModelDefinition{{ID: "test", Provider: "openai-compatible",
		Capabilities: []string{"chat", "streaming", "tool_calling"}}}
	req := httptest.NewRequest("PATCH", "/v1/assistants/00000000-0000-4000-8000-000000000001",
		strings.NewReader(`{"tools":["builtin.text_stats"]}`))
	req.Header.Set("Authorization", "Bearer test-key")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("If-Match", `"1"`)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	if w.Code != 200 || !strings.Contains(w.Body.String(), `"tools":["builtin.text_stats"]`) {
		t.Fatalf("%d %s", w.Code, w.Body)
	}
}

func TestAssistantPatchRejectsToolsWithoutModelCapability(t *testing.T) {
	store, s := versionSetup(t)
	r := httptest.NewRequest("PATCH", "/v1/assistants/"+store.assistant.ID,
		strings.NewReader(`{"tools":["builtin.text_stats"]}`))
	r.Header.Set("Authorization", "Bearer test-key")
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("If-Match", `"1"`)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 422 || !strings.Contains(w.Body.String(), `"error":"tool_calling_unsupported"`) {
		t.Fatalf("%d %s", w.Code, w.Body)
	}
	if store.assistant.Version != 1 || len(store.assistant.Tools) != 0 {
		t.Fatal("invalid assistant was persisted")
	}
}

func TestAssistantPatchAcceptsExecutionBudgetsAndRejectsOutOfRange(t *testing.T) {
	store, s := versionSetup(t)
	path := "/v1/assistants/" + store.assistant.ID
	patch := func(body, etag string) *httptest.ResponseRecorder {
		r := httptest.NewRequest("PATCH", path, strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer test-key")
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("If-Match", etag)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		return w
	}
	body := `{"limits":{"max_input_chars":1000,"max_output_chars":1000,"duration_seconds":1,"max_steps":2,"max_tool_calls":3,"max_tokens":100}}`
	if w := patch(body, `"1"`); w.Code != 200 {
		t.Fatal(w.Code, w.Body)
	}
	if store.assistant.Limits.MaxSteps != 2 || store.assistant.Limits.MaxToolCalls != 3 || store.assistant.Limits.MaxTokens != 100 {
		t.Fatal(store.assistant.Limits)
	}
	if w := patch(`{"limits":{"max_steps":17}}`, `"2"`); w.Code != 422 {
		t.Fatal(w.Code, w.Body)
	}
}

func TestAssistantPatchAcceptsJsonSchemaStructuredOutput(t *testing.T) {
	store, s := versionSetup(t)
	store.models = []ModelDefinition{{ID: "test", Provider: "openai-compatible",
		Capabilities: []string{"chat", "streaming", "structured_output"}}}
	path := "/v1/assistants/" + store.assistant.ID
	patch := func(body, etag string) *httptest.ResponseRecorder {
		r := httptest.NewRequest("PATCH", path, strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer test-key")
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("If-Match", etag)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		return w
	}
	if w := patch(`{"structured_output":{"type":"object","properties":{"answer":{"type":"string"}}}}`, `"1"`); w.Code != 200 {
		t.Fatal(w.Code, w.Body)
	}
	if len(store.assistant.StructuredOutput) == 0 {
		t.Fatal("structured output not persisted")
	}
	if w := patch(`{"structured_output":[]}`, `"2"`); w.Code != 422 {
		t.Fatal(w.Code, w.Body)
	}
}

func TestAssistantRejectsUnsupportedStructuredOutput(t *testing.T) {
	store, s := versionSetup(t)
	for _, method := range []string{"POST", "PATCH"} {
		path := "/v1/assistants"
		if method == "PATCH" {
			path += "/" + store.assistant.ID
		}
		r := httptest.NewRequest(method, path, strings.NewReader(`{"name":"JSON","model":"test","structured_output":{"type":"object"}}`))
		r.Header.Set("Authorization", "Bearer test-key")
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("If-Match", `"1"`)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != 422 || !strings.Contains(w.Body.String(), "structured_output_unsupported") {
			t.Fatalf("%s: %d %s", method, w.Code, w.Body)
		}
	}
	if store.assistant.Version != 1 {
		t.Fatal("invalid configuration was persisted")
	}
}

func TestAssistantValidationUsesDesiredProviderWhileApplicationPending(t *testing.T) {
	store, s := versionSetup(t)
	store.models = []ModelDefinition{{ID: "test", Provider: "openai-compatible",
		Capabilities: []string{"chat", "streaming", "tool_calling"}}}
	store.providerManaged = true
	store.providerConfig = ProviderConfiguration{Provider: "openai-compatible", Models: []ProviderModel{{ID: "test"}}}
	a := store.assistant
	a.Tools = []string{"builtin.text_stats"}
	if err := s.validateAssistantModel(context.Background(), a); err != ErrToolCallingUnsupported {
		t.Fatalf("validation against pending catalog: %v", err)
	}
}
