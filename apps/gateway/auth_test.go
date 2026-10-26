package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type authStore struct {
	memoryStore
	actor        Principal
	digest       string
	credential   Credential
	storedDigest string
}

func (s *authStore) Authenticate(_ context.Context, digest string) (Principal, error) {
	if digest != s.digest {
		return Principal{}, ErrUnauthorized
	}
	return s.actor, nil
}
func (s *authStore) Credentials(context.Context) ([]Credential, error) {
	return []Credential{s.credential}, nil
}
func (s *authStore) CreateCredential(_ context.Context, c Credential, digest string) (Credential, error) {
	s.storedDigest = digest
	s.credential = c
	return c, nil
}
func (s *authStore) RotateCredential(_ context.Context, id, digest string, expiry time.Time) (Credential, error) {
	s.storedDigest = digest
	return s.credential, nil
}
func (s *authStore) RevokeCredential(context.Context, string) error { return nil }
func authSetup(t *testing.T, role string, scopes []string) (*authStore, *server) {
	t.Helper()
	digest := sha256.Sum256([]byte("scoped-key"))
	store := &authStore{actor: Principal{ID: "user-1", Role: role, Scopes: scopes}, digest: hex.EncodeToString(digest[:])}
	return store, NewServer(store, Config{Model: "test", RuntimeURL: "http://runtime", InternalKey: "internal-secret"})
}
func scopedRequest(s http.Handler, method, path, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer scoped-key")
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w
}
func TestRoleAndScopeIntersection(t *testing.T) {
	cases := []struct {
		role               string
		scopes             []string
		method, path, body string
		status             int
	}{
		{"reader", []string{"assistants:read"}, "GET", "/v1/assistants", "", 200},
		{"reader", []string{"assistants:write"}, "POST", "/v1/assistants", `{"name":"A","model":"test","system_prompt":""}`, 403},
		{"operator", []string{"assistants:read"}, "POST", "/v1/assistants", `{"name":"A","model":"test","system_prompt":""}`, 403},
		{"operator", []string{"credentials:read"}, "GET", "/v1/credentials", "", 403},
		{"unknown", []string{"assistants:read"}, "GET", "/v1/assistants", "", 403},
	}
	for _, c := range cases {
		t.Run(c.role+c.method+c.path, func(t *testing.T) {
			_, s := authSetup(t, c.role, c.scopes)
			w := scopedRequest(s, c.method, c.path, c.body)
			if w.Code != c.status {
				t.Fatalf("status %d: %s", w.Code, w.Body)
			}
		})
	}
}
func TestCredentialCreationHashesSecretAndReturnsItOnce(t *testing.T) {
	store, s := authSetup(t, "admin", []string{"credentials:write", "credentials:read"})
	w := scopedRequest(s, "POST", "/v1/credentials", `{"role":"reader","scopes":["assistants:read"]}`)
	if w.Code != 201 {
		t.Fatalf("%d: %s", w.Code, w.Body)
	}
	var result struct {
		APIKey string `json:"api_key"`
	}
	if err := json.NewDecoder(w.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	if len(result.APIKey) != 64 {
		t.Fatal("missing random secret")
	}
	sum := sha256.Sum256([]byte(result.APIKey))
	if hex.EncodeToString(sum[:]) != store.storedDigest {
		t.Fatal("stored value is not digest")
	}
	w = scopedRequest(s, "GET", "/v1/credentials", "")
	if strings.Contains(w.Body.String(), result.APIKey) || strings.Contains(w.Body.String(), store.storedDigest) {
		t.Fatal("list exposed credential material")
	}
}
func TestCredentialValidationRejectsRoleEscalationAndInvalidExpiry(t *testing.T) {
	_, s := authSetup(t, "admin", []string{"credentials:write"})
	for _, body := range []string{`{"role":"reader","scopes":["credentials:write"]}`, `{"role":"admin","scopes":["unknown"]}`, `{"role":"reader","expires_at":"2020-01-01T00:00:00Z"}`} {
		if w := scopedRequest(s, "POST", "/v1/credentials", body); w.Code != 422 {
			t.Fatalf("%d: %s", w.Code, w.Body)
		}
	}
}

func TestPublicMessageCannotInjectAuthority(t *testing.T) {
	store, s := authSetup(t, "operator", []string{"messages:write"})
	req := httptest.NewRequest("POST", "/v1/conversations/00000000-0000-4000-8000-000000000002/messages", strings.NewReader(`{"content":"Hello","authority":{"principal_id":"admin"}}`))
	req.Header.Set("Authorization", "Bearer scoped-key")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", "key")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	if w.Code != 422 || store.calls != 0 {
		t.Fatalf("authority injection reached storage: %d", w.Code)
	}
}
func TestAuthFailuresDoNotBecomeBootstrap(t *testing.T) {
	_, s := authSetup(t, "operator", []string{"assistants:read"})
	for _, header := range []string{"", "Basic scoped-key", "Bearer wrong", "Bearer " + strings.Repeat("x", 513)} {
		req := httptest.NewRequest("GET", "/v1/assistants", nil)
		req.Header.Set("Authorization", header)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)
		if w.Code != 401 {
			t.Fatal(w.Code)
		}
	}
}

func TestGatewayPropagatesOnlyAuthenticatedAuthority(t *testing.T) {
	_, s := authSetup(t, "operator", []string{"messages:write"})
	seen := false
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		var input struct {
			Authority struct {
				PrincipalID string   `json:"principal_id"`
				Scopes      []string `json:"scopes"`
				Tools       []string `json:"allowed_tool_ids"`
			} `json:"authority"`
		}
		if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
			t.Fatal(err)
		}
		if input.Authority.PrincipalID != "user-1" || len(input.Authority.Scopes) != 1 || input.Authority.Scopes[0] != "messages:write" || len(input.Authority.Tools) != 0 {
			t.Fatalf("incorrect authority: %+v", input.Authority)
		}
		seen = true
		return &http.Response{StatusCode: 503, Body: http.NoBody}, nil
	})
	req := httptest.NewRequest("POST", "/v1/conversations/00000000-0000-4000-8000-000000000002/messages", strings.NewReader(`{"content":"Hello"}`))
	req.Header.Set("Authorization", "Bearer scoped-key")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", "key")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	if w.Code != 502 || !seen {
		t.Fatalf("%d, authority not forwarded", w.Code)
	}
}

func TestCredentialCannotRevokeOrRotateItsOwnKey(t *testing.T) {
	store, s := authSetup(t, "admin", []string{"credentials:write"})
	id := "00000000-0000-4000-8000-000000000001"
	store.actor.CredentialID = id
	for _, action := range []string{"rotate", "revoke"} {
		w := scopedRequest(s, "POST", "/v1/credentials/"+id+"/"+action, `{}`)
		if w.Code != 409 {
			t.Fatalf("%s returned %d", action, w.Code)
		}
	}
}

func TestMeReturnsEffectiveRoleAndScopes(t *testing.T) {
	_, s := authSetup(t, "reader", []string{"assistants:read", "models:read"})
	w := scopedRequest(s, "GET", "/v1/me", "")
	if w.Code != 200 {
		t.Fatalf("%d: %s", w.Code, w.Body)
	}
	var body struct {
		PrincipalID string   `json:"principal_id"`
		Role        string   `json:"role"`
		Scopes      []string `json:"scopes"`
	}
	if err := json.NewDecoder(w.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.PrincipalID != "user-1" || body.Role != "reader" || len(body.Scopes) != 2 {
		t.Fatalf("unexpected principal: %#v", body)
	}
}
