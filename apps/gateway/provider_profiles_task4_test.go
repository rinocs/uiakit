package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestConcurrentProfileWritesSerializePlaneApply(t *testing.T) {
	store, server, fake := providerSetup(t)
	fake.applyEntered = make(chan int64, 2)
	fake.applyRelease = make(chan struct{}, 2)
	body := func(id string) string {
		return `{"id":"` + id + `","name":"` + id + `","provider":"ollama","base_url":"http://ollama:11434","max_output_tokens":256,"models":[{"id":"model"}]}`
	}
	type result struct {
		id     string
		status int
		body   string
	}
	results := make(chan result, 2)
	done := make(chan struct{}, 2)
	start := func(id string) {
		go func() {
			response := providerRequest(server, "POST", "/v1/providers", body(id), "")
			results <- result{id: id, status: response.Code, body: response.Body.String()}
			done <- struct{}{}
		}()
	}
	start("first")
	select {
	case <-fake.applyEntered:
		// Writer A is now inside applyProviderPlane and is blocked by the fake.
	case <-time.After(2 * time.Second):
		t.Fatal("writer A did not enter the runtime apply")
	}
	start("second")
	secondBeforeRelease := false
	select {
	case revision := <-fake.applyEntered:
		secondBeforeRelease = true
		t.Errorf("second plane revision %d entered before the first was released; apply is not serialized", revision)
	case <-time.After(300 * time.Millisecond):
		// With the mutex, writer B is waiting before the runtime apply; this timeout is expected.
	}
	fake.applyRelease <- struct{}{}
	if !secondBeforeRelease {
		select {
		case <-fake.applyEntered:
			// The second apply may enter only after writer A has been released.
		case <-time.After(2 * time.Second):
			t.Fatal("writer B did not enter the runtime apply after writer A was released")
		}
	}
	// If the mutex is absent, both handlers were already blocked and both tokens
	// are needed to let the test join its writers before reporting the violation.
	fake.applyRelease <- struct{}{}
	for i := 0; i < 2; i++ {
		select {
		case <-done:
		case <-time.After(2 * time.Second):
			t.Fatal("profile writer did not finish")
		}
	}
	fake.mu.Lock()
	fake.applyRelease = nil
	fake.applyEntered = nil
	history := append([]int64(nil), fake.applyHistory...)
	maxInFlight := fake.maxInFlight
	finalRevision := fake.state.Revision
	fake.mu.Unlock()
	if secondBeforeRelease {
		t.Fatal("second apply arrived before release")
	}
	if maxInFlight != 1 {
		t.Fatalf("maximum apply concurrency=%d, want 1", maxInFlight)
	}
	if len(history) != 2 {
		t.Fatalf("apply history = %v, want two revisions", history)
	}
	for i := 1; i < len(history); i++ {
		if history[i] < history[i-1] {
			t.Fatalf("apply history went backwards: %v", history)
		}
	}
	store.providerMu.Lock()
	applied := store.appliedRevision
	persisted := map[string]ProviderProfile{
		"first": store.profiles["first"], "second": store.profiles["second"],
	}
	store.providerMu.Unlock()
	for i := 0; i < 2; i++ {
		var result result
		select {
		case result = <-results:
		default:
			t.Fatal("missing profile writer response")
		}
		if result.status != 200 || !strings.Contains(result.body, `"applied":true`) {
			t.Fatalf("concurrent %s write status=%d body=%s", result.id, result.status, result.body)
		}
		var view ProviderProfileView
		if err := json.Unmarshal([]byte(result.body), &view); err != nil {
			t.Fatalf("decode %s response: %v", result.id, err)
		}
		if view.Revision != persisted[result.id].Revision {
			t.Fatalf("%s response revision=%d persisted revision=%d", result.id, view.Revision, persisted[result.id].Revision)
		}
	}
	if int64(finalRevision) != history[len(history)-1] || applied != int64(finalRevision) {
		t.Fatalf("final plane revision=%d history=%v applied_revision=%d", finalRevision, history, applied)
	}
}

func TestProviderProfileCreatePushesPlaneRevision(t *testing.T) {
	store, server, fake := providerSetup(t)
	body := `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha","capabilities":[],"context_window":null}]}`
	response := providerRequest(server, "POST", "/v1/providers", body, "")
	if response.Code != 200 {
		t.Fatalf("status = %d: %s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), `"applied":true`) {
		t.Fatalf("response was not applied: %s", response.Body.String())
	}
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if fake.appliedPlane.Revision != 1 {
		t.Fatalf("runtime revision = %d, want 1", fake.appliedPlane.Revision)
	}
	store.providerMu.Lock()
	defer store.providerMu.Unlock()
	if store.profiles["openai"].ConfigSeq != 1 {
		t.Fatalf("config sequence = %d, want 1", store.profiles["openai"].ConfigSeq)
	}
}

func TestProviderProfileCreateDoesNotExposeCredentialFields(t *testing.T) {
	_, server, _ := providerSetup(t)
	body := `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha","capabilities":[],"context_window":null}]}`
	response := providerRequest(server, "POST", "/v1/providers", body, "")
	if response.Code != 200 {
		t.Fatalf("status = %d: %s", response.Code, response.Body.String())
	}
	for _, forbidden := range []string{"api_key", "secret_cipher", "secret_nonce"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("response contains %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestProviderProfileCreateRejectsValidationCodes(t *testing.T) {
	_, server, _ := providerSetup(t)
	cases := []struct {
		name, body, code string
	}{
		{"id", `{"id":"Bad Id","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha"}]}`, "invalid_profile_id"},
		{"url", `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"http://user:pw@host/v1","max_output_tokens":512,"models":[{"id":"alpha"}]}`, "invalid_provider_url"},
		{"duplicate", `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha"},{"id":"alpha"}]}`, "duplicate_model_id"},
	}
	for _, tc := range cases {
		response := providerRequest(server, "POST", "/v1/providers", tc.body, "")
		if response.Code != 422 || !strings.Contains(response.Body.String(), tc.code) {
			t.Fatalf("%s: status = %d body = %s", tc.name, response.Code, response.Body.String())
		}
	}
}

func TestProviderProfileUpdateRequiresIfMatch(t *testing.T) {
	_, server, _ := providerSetup(t)
	body := `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha"}]}`
	if response := providerRequest(server, "POST", "/v1/providers", body, ""); response.Code != 200 {
		t.Fatalf("create status = %d: %s", response.Code, response.Body.String())
	}
	update := `{"name":"OpenAI EU","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha"}]}`
	if response := providerRequest(server, "PUT", "/v1/providers/openai", update, ""); response.Code != 428 {
		t.Fatalf("missing if-match status = %d", response.Code)
	}
	if response := providerRequest(server, "PUT", "/v1/providers/openai", update, `"0"`); response.Code != 412 {
		t.Fatalf("stale if-match status = %d body = %s", response.Code, response.Body.String())
	}
	if response := providerRequest(server, "PUT", "/v1/providers/openai", update, `"1"`); response.Code != 200 {
		t.Fatalf("update status = %d body = %s", response.Code, response.Body.String())
	}
}

func TestProviderProfileApplyFailureLeavesSavedRow(t *testing.T) {
	store, server, fake := providerSetup(t)
	fake.applyCode = 422
	body := `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha"}]}`
	response := providerRequest(server, "POST", "/v1/providers", body, "")
	if response.Code != 502 || !strings.Contains(response.Body.String(), "provider_pending") {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	store.providerMu.Lock()
	_, exists := store.profiles["openai"]
	store.providerMu.Unlock()
	if !exists {
		t.Fatal("profile was not saved after apply failure")
	}
}

func TestRuntimePlaneDecryptsStoredSecretOnlyInternally(t *testing.T) {
	store, server, _ := providerSetup(t)
	box, err := newSecretBox("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
	if err != nil {
		t.Fatal(err)
	}
	server.config.SecretKey = box
	cipher, nonce, err := box.seal("openai", "sk-live-123")
	if err != nil {
		t.Fatal(err)
	}
	store.profiles["openai"] = ProviderProfile{ID: "openai", Name: "OpenAI", Provider: "openai-compatible", BaseURL: "https://api.example.com/v1", MaxOutputTokens: 512, Models: []ProviderModel{{ID: "alpha"}}, SecretCipher: cipher, SecretNonce: nonce, SecretKeyVersion: providerSecretKeyVersion, ConfigSeq: 1, Revision: 1}
	store.profiles["local"] = ProviderProfile{ID: "local", Name: "Local", Provider: "openai-compatible", BaseURL: "http://local/v1", MaxOutputTokens: 256, Models: []ProviderModel{{ID: "beta"}}, SecretRef: "MODEL_API_KEY", ConfigSeq: 2, Revision: 1}
	plane, err := server.runtimePlane(context.Background())
	if err != nil || len(plane.Profiles) != 2 {
		t.Fatalf("plane: %+v %v", plane, err)
	}
	secrets := map[string]providerRuntimeProfile{}
	for _, profile := range plane.Profiles {
		secrets[profile.ID] = profile
	}
	if secrets["openai"].APIKey != "sk-live-123" || secrets["local"].APIKeyRef != "MODEL_API_KEY" {
		t.Fatalf("secrets in plane: %+v", plane.Profiles)
	}
	response := providerRequest(server, "GET", "/v1/providers", "", "")
	if strings.Contains(response.Body.String(), "sk-live-123") {
		t.Fatalf("public view leaked secret: %s", response.Body.String())
	}
}

func providerSecretProfile() ProviderProfile {
	return ProviderProfile{ID: "openai", Name: "OpenAI", Provider: "openai-compatible", BaseURL: "https://api.example.com/v1",
		MaxOutputTokens: 512, Models: []ProviderModel{{ID: "alpha"}}, ConfigSeq: 1, Revision: 1}
}

func TestProviderSecretStoredRoundTrip(t *testing.T) {
	store, server, _ := providerSetup(t)
	store.profiles["openai"] = providerSecretProfile()
	response := providerRequest(server, "PUT", "/v1/providers/openai/secret", `{"source":"stored","value":"sk-live-123"}`, "")
	if response.Code != 200 || !strings.Contains(response.Body.String(), `"secret_source":"stored"`) || !strings.Contains(response.Body.String(), `"secret_configured":true`) {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	if strings.Contains(response.Body.String(), "sk-live-123") {
		t.Fatalf("response leaked secret: %s", response.Body.String())
	}
	store.providerMu.Lock()
	profile := store.profiles["openai"]
	store.providerMu.Unlock()
	if len(profile.SecretCipher) == 0 || profile.SecretRef != "" {
		t.Fatalf("stored profile = %+v", profile)
	}
}

func TestProviderSecretRequiresKey(t *testing.T) {
	store, server, _ := providerSetup(t)
	store.profiles["openai"] = providerSecretProfile()
	server.config.SecretKey = nil
	stored := providerRequest(server, "PUT", "/v1/providers/openai/secret", `{"source":"stored","value":"sk-live-123"}`, "")
	if stored.Code != 503 || !strings.Contains(stored.Body.String(), "secret_key_unavailable") {
		t.Fatalf("stored status = %d body = %s", stored.Code, stored.Body.String())
	}
	env := providerRequest(server, "PUT", "/v1/providers/openai/secret", `{"source":"env","ref":"MODEL_API_KEY"}`, "")
	if env.Code != 200 || !strings.Contains(env.Body.String(), `"secret_source":"env"`) {
		t.Fatalf("env status = %d body = %s", env.Code, env.Body.String())
	}
}

func TestProviderSecretValidation(t *testing.T) {
	store, server, _ := providerSetup(t)
	store.profiles["openai"] = providerSecretProfile()
	for _, value := range []string{"", "line\nvalue", strings.Repeat("x", 4097)} {
		body, _ := json.Marshal(ProviderSecretInput{Source: "stored", Value: value})
		response := providerRequest(server, "PUT", "/v1/providers/openai/secret", string(body), "")
		if response.Code != 422 || !strings.Contains(response.Body.String(), "secret_value_invalid") {
			t.Fatalf("value length=%d status=%d body=%s", len(value), response.Code, response.Body.String())
		}
	}
	invalidRef := providerRequest(server, "PUT", "/v1/providers/openai/secret", `{"source":"env","ref":"INTERNAL_API_KEY"}`, "")
	if invalidRef.Code != 422 || !strings.Contains(invalidRef.Body.String(), "invalid_api_key_ref") {
		t.Fatalf("invalid ref status = %d body = %s", invalidRef.Code, invalidRef.Body.String())
	}
	store.profiles["local"] = ProviderProfile{ID: "local", Provider: "ollama", BaseURL: "http://ollama:11434", Models: []ProviderModel{{ID: "model"}}}
	ollama := providerRequest(server, "PUT", "/v1/providers/local/secret", `{"source":"stored","value":"sk-live-123"}`, "")
	if ollama.Code != 422 || !strings.Contains(ollama.Body.String(), "api_key_ref_not_supported") {
		t.Fatalf("ollama status = %d body = %s", ollama.Code, ollama.Body.String())
	}
	both := providerRequest(server, "PUT", "/v1/providers/openai/secret", `{"source":"stored","value":"sk-live-123","ref":"MODEL_API_KEY"}`, "")
	if both.Code != 422 || !strings.Contains(both.Body.String(), "invalid_configuration") {
		t.Fatalf("both status = %d body = %s", both.Code, both.Body.String())
	}
}

func TestProviderSecretUnreadableVersion(t *testing.T) {
	store, server, _ := providerSetup(t)
	store.profiles["openai"] = providerSecretProfile()
	store.secretVersionOverride = 2
	response := providerRequest(server, "PUT", "/v1/providers/openai/secret", `{"source":"stored","value":"sk-live-123"}`, "")
	if response.Code != 502 || !strings.Contains(response.Body.String(), "secret_unreadable") {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
}

func TestProviderDiscoveryUsesStoredSecret(t *testing.T) {
	store, server, fake := providerSetup(t)
	store.profiles["openai"] = providerSecretProfile()
	cipher, nonce, err := server.config.SecretKey.seal("openai", "sk-live-123")
	if err != nil {
		t.Fatal(err)
	}
	profile := store.profiles["openai"]
	profile.SecretCipher = cipher
	profile.SecretNonce = nonce
	profile.SecretKeyVersion = providerSecretKeyVersion
	store.profiles["openai"] = profile
	response := providerRequest(server, "POST", "/v1/providers/openai/models/discovery", `{}`, "")
	if response.Code != 200 {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	if fake.discoveryRequest.APIKey != "sk-live-123" || fake.discoveryRequest.APIKeyRef != "" {
		t.Fatalf("discovery request = %+v", fake.discoveryRequest)
	}
}

func TestProviderDiscoveryEnvRef(t *testing.T) {
	store, server, fake := providerSetup(t)
	profile := providerSecretProfile()
	profile.SecretRef = "PROVIDER_API_KEY_TEAM"
	store.profiles["openai"] = profile
	response := providerRequest(server, "POST", "/v1/providers/openai/models/discovery", `{}`, "")
	if response.Code != 200 {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	if fake.discoveryRequest.APIKey != "" || fake.discoveryRequest.APIKeyRef != "PROVIDER_API_KEY_TEAM" {
		t.Fatalf("discovery request = %+v", fake.discoveryRequest)
	}
}

func TestProviderProfileDeleteChecksNamespacedUse(t *testing.T) {
	store, server, _ := providerSetup(t)
	body := `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha","capabilities":[],"context_window":null}]}`
	if response := providerRequest(server, "POST", "/v1/providers", body, ""); response.Code != 200 {
		t.Fatalf("create status = %d: %s", response.Code, response.Body.String())
	}
	store.inUse["openai/alpha"] = 1
	if response := providerRequest(server, "DELETE", "/v1/providers/openai", "", ""); response.Code != 409 || !strings.Contains(response.Body.String(), "profile_in_use") {
		t.Fatalf("delete status = %d body = %s", response.Code, response.Body.String())
	}
}
