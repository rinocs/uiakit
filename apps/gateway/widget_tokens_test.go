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

const (
	testAssistantID    = "00000000-0000-4000-8000-000000000001"
	testConversationID = "00000000-0000-4000-8000-000000000002"
	testWidgetOrigin   = "https://widget.example"
)

func widgetSetup(t *testing.T, rateLimit int) (*authStore, *server) {
	t.Helper()
	digest := sha256.Sum256([]byte("scoped-key"))
	store := &authStore{
		actor:  Principal{ID: "user-1", Role: "admin", Scopes: []string{"widget-tokens:write", "messages:read", "messages:write"}},
		digest: hex.EncodeToString(digest[:]),
	}
	return store, NewServer(store, Config{
		Model: "test", RuntimeURL: "http://runtime", InternalKey: "internal-secret",
		WidgetOrigins: []string{testWidgetOrigin}, WidgetRateLimit: rateLimit,
	})
}

func widgetRequest(s http.Handler, method, path, origin, token, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	if origin != "" {
		req.Header.Set("Origin", origin)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w
}

func mintWidget(t *testing.T, s http.Handler) (string, string) {
	t.Helper()
	body := `{"assistant_id":"` + testAssistantID + `","conversation_id":"` + testConversationID + `","subject":"browser-1","origin":"` + testWidgetOrigin + `","expires_in_seconds":600}`
	w := scopedRequest(s, "POST", "/v1/widget/tokens", body)
	if w.Code != 201 {
		t.Fatalf("mint: %d %s", w.Code, w.Body)
	}
	var response struct {
		Token string `json:"token"`
		ID    string `json:"id"`
	}
	if err := json.NewDecoder(w.Body).Decode(&response); err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(response.Token, widgetTokenPrefix) {
		t.Fatalf("unexpected token %q", response.Token)
	}
	return response.Token, response.ID
}

func TestWidgetTokenIsScopedAndBound(t *testing.T) {
	_, s := widgetSetup(t, 100)
	token, _ := mintWidget(t, s)
	path := "/v1/conversations/" + testConversationID + "/messages"

	if w := widgetRequest(s, "GET", path, testWidgetOrigin, token, ""); w.Code != 200 {
		t.Fatalf("bound conversation: %d %s", w.Code, w.Body)
	}
	if w := widgetRequest(s, "GET", "/v1/conversations/00000000-0000-4000-8000-000000000099/messages", testWidgetOrigin, token, ""); w.Code != 403 {
		t.Fatalf("cross conversation: %d %s", w.Code, w.Body)
	}
	if w := widgetRequest(s, "GET", path, "https://evil.example", token, ""); w.Code != 403 {
		t.Fatalf("wrong origin: %d %s", w.Code, w.Body)
	}
	for _, target := range []struct{ method, path string }{
		{"GET", "/v1/credentials"},
		{"GET", "/v1/assistants"},
		{"GET", "/v1/agent-runs"},
		{"POST", "/v1/conversations"},
		{"POST", "/v1/widget/tokens"},
	} {
		if w := widgetRequest(s, target.method, target.path, testWidgetOrigin, token, `{}`); w.Code != 403 {
			t.Fatalf("%s %s: %d %s", target.method, target.path, w.Code, w.Body)
		}
	}
}

func TestWidgetTokenExpiryAndRevocation(t *testing.T) {
	store, s := widgetSetup(t, 100)
	token, id := mintWidget(t, s)
	path := "/v1/conversations/" + testConversationID + "/messages"

	if w := scopedRequest(s, "DELETE", "/v1/widget/tokens/"+id, ""); w.Code != 200 {
		t.Fatalf("revoke: %d %s", w.Code, w.Body)
	}
	if w := widgetRequest(s, "GET", path, testWidgetOrigin, token, ""); w.Code != 401 {
		t.Fatalf("revoked token: %d %s", w.Code, w.Body)
	}

	expiredToken := "uai_widget_expired"
	digest := sha256.Sum256([]byte(expiredToken))
	if _, err := store.CreateWidgetToken(context.Background(), WidgetToken{
		ID: "00000000-0000-4000-8000-000000000010", AssistantID: testAssistantID,
		ConversationID: testConversationID, Subject: "expired", Scopes: widgetScopes,
		Origin: testWidgetOrigin, ExpiresAt: time.Now().Add(-time.Minute),
		CreatedAt: time.Now().Add(-time.Hour), CreatedBy: "user-1",
	}, hex.EncodeToString(digest[:])); err != nil {
		t.Fatal(err)
	}
	if w := widgetRequest(s, "GET", path, testWidgetOrigin, expiredToken, ""); w.Code != 401 {
		t.Fatalf("expired token: %d %s", w.Code, w.Body)
	}
}

func TestWidgetCORSAndRateLimit(t *testing.T) {
	_, s := widgetSetup(t, 1)
	path := "/v1/conversations/" + testConversationID + "/messages"

	preflight := httptest.NewRequest("OPTIONS", path, nil)
	preflight.Header.Set("Origin", testWidgetOrigin)
	preflight.Header.Set("Access-Control-Request-Method", "POST")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, preflight)
	if w.Code != 204 || w.Header().Get("Access-Control-Allow-Origin") != testWidgetOrigin {
		t.Fatalf("preflight: %d %v", w.Code, w.Header())
	}

	blocked := httptest.NewRequest("OPTIONS", path, nil)
	blocked.Header.Set("Origin", "https://evil.example")
	w = httptest.NewRecorder()
	s.ServeHTTP(w, blocked)
	if w.Code != 403 {
		t.Fatalf("untrusted preflight: %d", w.Code)
	}

	token, _ := mintWidget(t, s)
	if w := widgetRequest(s, "GET", path, testWidgetOrigin, token, ""); w.Code != 200 {
		t.Fatalf("first request: %d %s", w.Code, w.Body)
	}
	if w := widgetRequest(s, "GET", path, testWidgetOrigin, token, ""); w.Code != 429 {
		t.Fatalf("rate limit: %d %s", w.Code, w.Body)
	}
}

func TestWidgetMintRejectsUnlistedOriginAndLongTTL(t *testing.T) {
	_, s := widgetSetup(t, 100)
	bodies := []string{
		`{"assistant_id":"` + testAssistantID + `","conversation_id":"` + testConversationID + `","origin":"https://evil.example"}`,
		`{"assistant_id":"` + testAssistantID + `","conversation_id":"` + testConversationID + `","origin":"` + testWidgetOrigin + `","expires_in_seconds":999999}`,
	}
	for _, body := range bodies {
		if w := scopedRequest(s, "POST", "/v1/widget/tokens", body); w.Code != 422 {
			t.Fatalf("mint validation: %d %s", w.Code, w.Body)
		}
	}
}
