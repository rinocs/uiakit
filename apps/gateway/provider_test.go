package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

type providerAuthStore struct {
	authStore
	providerMu            sync.Mutex
	inUse                 map[string]int
	synced                []ModelDefinition
	validateCalls         int
	applyCalls            int
	profiles              map[string]ProviderProfile
	globalRevision        int64
	appliedRevision       int64
	secretVersionOverride int
}

func (s *providerAuthStore) AssistantsUsingModel(_ context.Context, model string) (int, error) {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	return s.inUse[model], nil
}

func (s *providerAuthStore) ProviderProfiles(context.Context) ([]ProviderProfile, error) {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	out := make([]ProviderProfile, 0, len(s.profiles))
	for _, profile := range s.profiles {
		out = append(out, profile)
	}
	return out, nil
}

func (s *providerAuthStore) ProviderProfile(_ context.Context, id string) (ProviderProfile, error) {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	if profile, ok := s.profiles[id]; ok {
		return profile, nil
	}
	return ProviderProfile{}, ErrNotFound
}

func (s *providerAuthStore) CreateProviderProfile(_ context.Context, profile ProviderProfile) (ProviderProfile, error) {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	if _, ok := s.profiles[profile.ID]; ok {
		return profile, ErrConflict
	}
	s.globalRevision++
	profile.Revision = 1
	profile.ConfigSeq = s.globalRevision
	s.profiles[profile.ID] = profile
	return profile, nil
}

func (s *providerAuthStore) UpdateProviderProfile(_ context.Context, id string, expected int, profile ProviderProfile) (ProviderProfile, error) {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	current, ok := s.profiles[id]
	if !ok {
		return profile, ErrNotFound
	}
	if current.Revision != expected {
		return profile, ErrConflict
	}
	s.globalRevision++
	profile.ID = id
	profile.Revision = current.Revision + 1
	profile.ConfigSeq = s.globalRevision
	s.profiles[id] = profile
	return profile, nil
}

func (s *providerAuthStore) DeleteProviderProfile(_ context.Context, id string) error {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	if _, ok := s.profiles[id]; !ok {
		return ErrNotFound
	}
	s.globalRevision++
	delete(s.profiles, id)
	return nil
}

func (s *providerAuthStore) SetProviderSecret(_ context.Context, id string, secret ProviderSecret) (ProviderProfile, error) {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	profile, ok := s.profiles[id]
	if !ok {
		return ProviderProfile{}, ErrNotFound
	}
	switch secret.Source {
	case "stored":
		profile.SecretCipher = secret.Cipher
		profile.SecretNonce = secret.Nonce
		profile.SecretKeyVersion = secret.KeyVersion
		if s.secretVersionOverride != 0 {
			profile.SecretKeyVersion = s.secretVersionOverride
		}
		profile.SecretRef = ""
	case "env":
		profile.SecretCipher = nil
		profile.SecretNonce = nil
		profile.SecretKeyVersion = 0
		profile.SecretRef = secret.Ref
	case "none":
		profile.SecretCipher = nil
		profile.SecretNonce = nil
		profile.SecretKeyVersion = 0
		profile.SecretRef = ""
	}
	s.globalRevision++
	profile.Revision++
	profile.ConfigSeq = s.globalRevision
	s.profiles[id] = profile
	return profile, nil
}

func (s *providerAuthStore) ProviderAppliedRevision(context.Context) (int64, error) {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	return s.appliedRevision, nil
}

func (s *providerAuthStore) MarkProviderApplied(_ context.Context, revision int64) error {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	if revision > s.appliedRevision {
		s.appliedRevision = revision
	}
	return nil
}

func (s *providerAuthStore) ProviderConfiguration(context.Context) (ProviderConfiguration, error) {
	return ProviderConfiguration{}, ErrNotFound
}

func (s *providerAuthStore) SyncModels(_ context.Context, models []ModelDefinition) error {
	s.providerMu.Lock()
	defer s.providerMu.Unlock()
	s.synced = append([]ModelDefinition(nil), models...)
	return nil
}

type fakeProviderRuntime struct {
	mu               sync.Mutex
	server           *httptest.Server
	state            runtimeProviderState
	applyCode        int
	validateCode     int
	discovery        []string
	appliedConfig    ProviderConfiguration
	appliedPlane     providerRuntimePlane
	applyHistory     []int64
	discoveryRequest ProviderDiscovery
	applyEntered     chan int64
	applyRelease     chan struct{}
	inFlight         int
	maxInFlight      int
	models           []ModelDefinition
}

func newFakeProviderRuntime(t *testing.T) *fakeProviderRuntime {
	t.Helper()
	fake := &fakeProviderRuntime{
		state: runtimeProviderState{
			Revision: 0, Provider: "openai-compatible", BaseURL: "http://provider/v1",
			APIKeyRef: "MODEL_API_KEY", APIKeyConfigured: true, MaxOutputTokens: 1024,
			Models: []ModelDefinition{{ID: "test", Provider: "openai-compatible",
				Capabilities: []string{"chat", "streaming"}}},
		},
		models: []ModelDefinition{{ID: "test", Provider: "openai-compatible",
			Capabilities: []string{"chat", "streaming"}}},
	}
	fake.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fake.mu.Lock()
		defer fake.mu.Unlock()
		if r.Header.Get("Authorization") != "Bearer internal-secret" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/internal/v1/provider/state":
			json.NewEncoder(w).Encode(fake.state)
		case r.Method == http.MethodPost && r.URL.Path == "/internal/v1/provider/validate":
			if fake.validateCode != 0 {
				w.WriteHeader(fake.validateCode)
				json.NewEncoder(w).Encode(map[string]string{"detail": "egress_denied"})
				return
			}
			json.NewEncoder(w).Encode(map[string]any{"api_key_configured": true})
		case r.Method == http.MethodPost && r.URL.Path == "/internal/v1/provider/apply":
			data, err := io.ReadAll(r.Body)
			if err != nil {
				w.WriteHeader(http.StatusUnprocessableEntity)
				return
			}
			if fake.applyCode != 0 {
				w.WriteHeader(fake.applyCode)
				json.NewEncoder(w).Encode(map[string]string{"detail": "provider_down"})
				return
			}
			var plane providerRuntimePlane
			if err := json.Unmarshal(data, &plane); err == nil && plane.Profiles != nil {
				models := make([]ModelDefinition, 0)
				for _, profile := range plane.Profiles {
					models = append(models, providerDefinitions(ProviderConfiguration{Provider: profile.Provider, MaxOutputTokens: profile.MaxOutputTokens, Models: profile.Models})...)
				}
				state := runtimeProviderState{Revision: int(plane.Revision), APIKeyConfigured: true, Models: models, Profiles: plane.Profiles}
				fake.inFlight++
				if fake.inFlight > fake.maxInFlight {
					fake.maxInFlight = fake.inFlight
				}
				if fake.applyEntered != nil {
					fake.applyEntered <- plane.Revision
				}
				release := fake.applyRelease
				if release != nil {
					fake.mu.Unlock()
					<-release
					fake.mu.Lock()
				}
				fake.inFlight--
				fake.appliedPlane = plane
				fake.applyHistory = append(fake.applyHistory, plane.Revision)
				fake.models = models
				fake.state = state
				json.NewEncoder(w).Encode(state)
				return
			}
			var config providerRuntimeConfig
			if err := json.Unmarshal(data, &config); err != nil {
				w.WriteHeader(http.StatusUnprocessableEntity)
				return
			}
			if fake.applyCode != 0 {
				w.WriteHeader(fake.applyCode)
				json.NewEncoder(w).Encode(map[string]string{"detail": "provider_down"})
				return
			}
			fake.appliedConfig = ProviderConfiguration{
				Revision: config.Revision, Provider: config.Provider, BaseURL: config.BaseURL,
				APIKeyRef: config.APIKeyRef, MaxOutputTokens: config.MaxOutputTokens, Models: config.Models,
			}
			fake.models = providerDefinitions(fake.appliedConfig)
			fake.state = runtimeProviderState{
				Revision: config.Revision, Provider: config.Provider, BaseURL: config.BaseURL,
				APIKeyRef: config.APIKeyRef, APIKeyConfigured: true,
				MaxOutputTokens: config.MaxOutputTokens, Models: fake.models,
			}
			json.NewEncoder(w).Encode(fake.state)
		case r.Method == http.MethodPost && r.URL.Path == "/internal/v1/provider/models":
			var discovery ProviderDiscovery
			if err := json.NewDecoder(r.Body).Decode(&discovery); err != nil {
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			fake.discoveryRequest = discovery
			json.NewEncoder(w).Encode(map[string]any{"models": fake.discovery})
		case r.Method == http.MethodGet && r.URL.Path == "/internal/v1/models":
			json.NewEncoder(w).Encode(fake.models)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	t.Cleanup(fake.server.Close)
	return fake
}

func providerSetup(t *testing.T) (*providerAuthStore, *server, *fakeProviderRuntime) {
	t.Helper()
	digest := sha256.Sum256([]byte("scoped-key"))
	store := &providerAuthStore{
		authStore: authStore{
			actor:  Principal{ID: "admin-1", Role: "admin", Scopes: roleScopes["admin"]},
			digest: hex.EncodeToString(digest[:]),
		},
		inUse:    map[string]int{},
		profiles: map[string]ProviderProfile{},
	}
	fake := newFakeProviderRuntime(t)
	server := NewServer(store, Config{Model: "test", RuntimeURL: fake.server.URL, InternalKey: "internal-secret", SecretKey: testBox(t)})
	return store, server, fake
}

func providerRequest(s http.Handler, method, path, body, ifMatch string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer scoped-key")
	req.Header.Set("Content-Type", "application/json")
	if ifMatch != "" {
		req.Header.Set("If-Match", ifMatch)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w
}

func providerInternalRequest(s http.Handler, method, path, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer internal-secret")
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w
}

func validProviderUpdate() string {
	return `{"provider":"openai-compatible","base_url":"http://provider/v1",` +
		`"api_key_ref":"MODEL_API_KEY","max_output_tokens":1024,` +
		`"models":[{"id":"test","capabilities":["tool_calling"],"context_window":8192}]}`
}

func TestProviderRequiresAdminScopes(t *testing.T) {
	digest := sha256.Sum256([]byte("scoped-key"))
	reader := &authStore{actor: Principal{ID: "reader-1", Role: "reader", Scopes: []string{"providers:read", "providers:write"}},
		digest: hex.EncodeToString(digest[:])}
	readerServer := NewServer(reader, Config{Model: "test", RuntimeURL: "http://runtime", InternalKey: "internal-secret"})
	if response := scopedRequest(readerServer, "GET", "/v1/provider", ""); response.Code != 403 {
		t.Fatalf("reader status = %d, want 403", response.Code)
	}
	adminRead := &authStore{actor: Principal{ID: "admin-1", Role: "admin", Scopes: []string{"providers:read"}},
		digest: hex.EncodeToString(digest[:])}
	adminServer := NewServer(adminRead, Config{Model: "test", RuntimeURL: "http://runtime", InternalKey: "internal-secret"})
	if response := scopedRequest(adminServer, "PUT", "/v1/provider", validProviderUpdate()); response.Code != 403 {
		t.Fatalf("admin without write status = %d, want 403", response.Code)
	}
}

func TestProviderUnmanagedViewComesFromRuntime(t *testing.T) {
	_, server, fake := providerSetup(t)
	fake.state.Provider = "ollama"
	fake.state.BaseURL = "http://ollama:11434"
	fake.state.APIKeyRef = ""
	fake.state.APIKeyConfigured = false
	response := providerRequest(server, "GET", "/v1/provider", "", "")
	if response.Code != 200 {
		t.Fatalf("status = %d: %s", response.Code, response.Body.String())
	}
	var view ProviderView
	if err := json.Unmarshal(response.Body.Bytes(), &view); err != nil {
		t.Fatal(err)
	}
	if view.Managed || view.Revision != 0 || view.Provider != "ollama" {
		t.Fatalf("unexpected view: %+v", view)
	}
	if response.Header().Get("ETag") != `"0"` {
		t.Fatalf("etag = %q", response.Header().Get("ETag"))
	}
}

func TestProviderUpdateValidatesAppliesAndSyncs(t *testing.T) {
	store, server, fake := providerSetup(t)
	response := providerRequest(server, "PUT", "/v1/provider", validProviderUpdate(), `"0"`)
	if response.Code != 200 {
		t.Fatalf("status = %d: %s", response.Code, response.Body.String())
	}
	var view ProviderView
	if err := json.Unmarshal(response.Body.Bytes(), &view); err != nil {
		t.Fatal(err)
	}
	if view.Revision != 1 || !view.Managed || !view.Applied || !view.APIKeyConfigured {
		t.Fatalf("unexpected view: %+v", view)
	}
	if len(view.Models) != 1 || view.Models[0].ID != "test" {
		t.Fatalf("unexpected models: %+v", view.Models)
	}
	store.providerMu.Lock()
	saved, synced := store.profiles["default"], store.synced
	store.providerMu.Unlock()
	if saved.Revision != 1 || saved.MaxOutputTokens != 1024 || saved.SecretRef != "MODEL_API_KEY" {
		t.Fatalf("saved = %+v", saved)
	}
	if len(synced) != 1 || synced[0].ID != "test" {
		t.Fatalf("synced = %+v", synced)
	}
	if fake.appliedPlane.Revision != 1 || len(fake.appliedPlane.Profiles) != 1 {
		t.Fatalf("runtime applied plane = %+v", fake.appliedPlane)
	}
}

func TestProviderUpdateRejectsRuntimeValidation(t *testing.T) {
	store, server, fake := providerSetup(t)
	fake.validateCode = 422
	response := providerRequest(server, "PUT", "/v1/provider", validProviderUpdate(), `"0"`)
	if response.Code != 422 || !strings.Contains(response.Body.String(), "egress_denied") {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	store.providerMu.Lock()
	defer store.providerMu.Unlock()
	if len(store.profiles) != 0 {
		t.Fatalf("configuration should not be saved")
	}
}

func TestProviderUpdateBlocksModelInUse(t *testing.T) {
	store, server, _ := providerSetup(t)
	store.profiles["default"] = ProviderProfile{ID: "default", Name: "Default", Revision: 2,
		ConfigSeq: 2, Provider: "openai-compatible", BaseURL: "http://provider/v1",
		SecretRef: "MODEL_API_KEY", MaxOutputTokens: 1024,
		Models: []ProviderModel{{ID: "old"}, {ID: "keep"}}}
	store.inUse["old"] = 1
	body := `{"provider":"openai-compatible","base_url":"http://provider/v1",` +
		`"api_key_ref":"MODEL_API_KEY","max_output_tokens":1024,` +
		`"models":[{"id":"keep","capabilities":[],"context_window":null}]}`
	response := providerRequest(server, "PUT", "/v1/provider", body, `"2"`)
	if response.Code != 409 || !strings.Contains(response.Body.String(), "model_in_use") {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
}

func TestProviderUpdateConflictAndPending(t *testing.T) {
	store, server, fake := providerSetup(t)
	store.profiles["default"] = ProviderProfile{ID: "default", Name: "Default", Revision: 3,
		ConfigSeq: 3, Provider: "openai-compatible", BaseURL: "http://provider/v1",
		SecretRef: "MODEL_API_KEY", MaxOutputTokens: 1024,
		Models: []ProviderModel{{ID: "test"}}}
	if response := providerRequest(server, "PUT", "/v1/provider", validProviderUpdate(), `"2"`); response.Code != 412 {
		t.Fatalf("conflict status = %d", response.Code)
	}
	fake.applyCode = 500
	response := providerRequest(server, "PUT", "/v1/provider", validProviderUpdate(), `"3"`)
	if response.Code != 502 || !strings.Contains(response.Body.String(), "provider_pending") {
		t.Fatalf("pending status = %d body = %s", response.Code, response.Body.String())
	}
	store.providerMu.Lock()
	defer store.providerMu.Unlock()
	if store.profiles["default"].Revision != 4 {
		t.Fatalf("saved revision = %d", store.profiles["default"].Revision)
	}
}

func TestProviderDiscovery(t *testing.T) {
	_, server, fake := providerSetup(t)
	fake.discovery = []string{"model-a", "model-b"}
	body := `{"provider":"openai-compatible","base_url":"http://provider/v1","api_key_ref":"MODEL_API_KEY"}`
	response := providerRequest(server, "POST", "/v1/provider/models", body, "")
	if response.Code != 200 || !strings.Contains(response.Body.String(), "model-b") {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	if fake.discoveryRequest.Provider != "openai-compatible" || fake.discoveryRequest.BaseURL != "http://provider/v1" || fake.discoveryRequest.APIKeyRef != "MODEL_API_KEY" {
		t.Fatalf("discovery request = %+v", fake.discoveryRequest)
	}
	invalid := providerRequest(server, "POST", "/v1/provider/models",
		`{"provider":"openai-compatible","base_url":"http://provider/v1","api_key_ref":"INTERNAL_API_KEY"}`, "")
	if invalid.Code != 422 {
		t.Fatalf("invalid ref status = %d", invalid.Code)
	}
}

func TestInternalProviderDesiredAndApplied(t *testing.T) {
	store, server, _ := providerSetup(t)
	if response := providerInternalRequest(server, "GET", "/internal/v1/provider/desired", ""); response.Code != 404 {
		t.Fatalf("unmanaged desired status = %d", response.Code)
	}
	store.profiles["default"] = ProviderProfile{ID: "default", Name: "Default", Revision: 1,
		ConfigSeq: 5, Provider: "openai-compatible", BaseURL: "http://provider/v1",
		SecretRef: "MODEL_API_KEY", MaxOutputTokens: 1024,
		Models: []ProviderModel{{ID: "test"}}}
	response := providerInternalRequest(server, "GET", "/internal/v1/provider/desired", "")
	if response.Code != 200 {
		t.Fatalf("desired status = %d", response.Code)
	}
	var plane providerRuntimePlane
	if err := json.Unmarshal(response.Body.Bytes(), &plane); err != nil || len(plane.Profiles) != 1 || plane.Profiles[0].ID != "default" {
		t.Fatalf("desired plane = %+v err=%v", plane, err)
	}
	final := providerInternalRequest(server, "POST", "/internal/v1/provider/applied", `{"revision":5}`)
	if final.Code != 204 {
		t.Fatalf("applied status = %d: %s", final.Code, final.Body.String())
	}
	store.providerMu.Lock()
	defer store.providerMu.Unlock()
	if store.appliedRevision != 5 || len(store.synced) != 1 || store.synced[0].ID != "test" {
		t.Fatalf("applied=%d synced=%+v", store.appliedRevision, store.synced)
	}
}

func TestLegacyProviderSchemaAndETagUsesDefaultProfileRevision(t *testing.T) {
	store, server, _ := providerSetup(t)
	store.profiles["default"] = ProviderProfile{ID: "default", Name: "Default", Revision: 7,
		ConfigSeq: 11, Provider: "openai-compatible", BaseURL: "http://provider/v1",
		SecretRef: "MODEL_API_KEY", MaxOutputTokens: 1024,
		Models: []ProviderModel{{ID: "test"}}}
	response := providerRequest(server, "GET", "/v1/provider", "", "")
	if response.Code != 200 {
		t.Fatalf("status = %d: %s", response.Code, response.Body.String())
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(response.Body.Bytes(), &raw); err != nil {
		t.Fatal(err)
	}
	want := []string{"revision", "managed", "applied", "provider", "base_url", "api_key_ref", "api_key_configured", "max_output_tokens", "models"}
	if len(raw) != len(want) {
		t.Fatalf("keys = %v", raw)
	}
	for _, key := range want {
		if _, ok := raw[key]; !ok {
			t.Fatalf("missing key %q", key)
		}
	}
	if response.Header().Get("ETag") != `"7"` {
		t.Fatalf("etag = %q", response.Header().Get("ETag"))
	}
}

func TestProvidersReturnsUnmanagedSyntheticDefault(t *testing.T) {
	_, server, fake := providerSetup(t)
	fake.state.Provider = "ollama"
	fake.state.BaseURL = "http://ollama:11434"
	fake.state.APIKeyRef = ""
	fake.state.APIKeyConfigured = false
	response := providerRequest(server, "GET", "/v1/providers", "", "")
	if response.Code != 200 {
		t.Fatalf("status = %d: %s", response.Code, response.Body.String())
	}
	var list ProviderProfileList
	if err := json.Unmarshal(response.Body.Bytes(), &list); err != nil {
		t.Fatal(err)
	}
	if len(list.Profiles) != 1 || list.Profiles[0].ID != "default" || list.Profiles[0].Managed {
		t.Fatalf("profiles = %+v", list.Profiles)
	}
	if list.Profiles[0].Provider != "ollama" || list.Profiles[0].SecretConfigured {
		t.Fatalf("synthetic default = %+v", list.Profiles[0])
	}
}
