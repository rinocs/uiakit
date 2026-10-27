package main

import (
	"context"
	"strings"
	"testing"
)

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
