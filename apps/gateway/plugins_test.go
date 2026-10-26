package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPluginAdminPersistenceAndReconciliation(t *testing.T) {
	store, s := setup(t)
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		if r.Header.Get("Authorization") != "Bearer internal-secret" {
			t.Fatal("missing auth")
		}
		body, status := ``, 204
		switch r.URL.Path {
		case "/internal/v1/plugins":
			body, status = `[{"manifest":{"id":"org.uai.hello","version":"0.1.0","name":"Hello","runtime":"python"},"state":"inactive"},{"manifest":{"id":"org.uai.isolated","version":"0.1.0","name":"Isolated","runtime":"isolated_http"},"state":"inactive"}]`, 200
		case "/internal/v1/plugins/validate":
		case "/internal/v1/plugins/reconcile":
			body, status = `{"applied":true,"revision":2}`, 200
		default:
			t.Fatal(r.URL.Path)
		}
		return &http.Response{StatusCode: status, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(body))}, nil
	})
	request := func(method, path, body, version string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, path, strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer test-key")
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("If-Match", version)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		return w
	}
	w := request("PUT", "/v1/plugins/org.uai.hello", `{"enabled":true,"config":{}}`, `"1"`)
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body)
	}
	config, err := store.PluginConfiguration(context.Background())
	if err != nil || config.Revision != 2 || !config.Settings["org.uai.hello"].Enabled {
		t.Fatal(config, err)
	}
	if w = request("PUT", "/v1/plugins/org.uai.hello", `{"enabled":false,"config":{}}`, `"1"`); w.Code != 412 {
		t.Fatal(w.Code, w.Body)
	}
	if w = request("PUT", "/v1/plugins/org.uai.hello", `{"enabled":false,"config":{}}`, ""); w.Code != 428 {
		t.Fatal(w.Code, w.Body)
	}
	w = request("GET", "/v1/plugins", "", "")
	if w.Code != 200 || w.Header().Get("ETag") != `"2"` {
		t.Fatal(w.Code, w.Body)
	}
	var result map[string]any
	if json.Unmarshal(w.Body.Bytes(), &result) != nil || result["applied"] != true {
		t.Fatal(w.Body)
	}
}

func TestPluginAdministrationRequiresAdminAndExplicitScopes(t *testing.T) {
	for _, actor := range []struct {
		role   string
		scopes []string
	}{
		{"reader", []string{"plugins:read", "plugins:write"}},
		{"operator", []string{"plugins:read", "plugins:write"}},
		{"admin", []string{"credentials:write"}},
	} {
		_, s := authSetup(t, actor.role, actor.scopes)
		s.client.Transport = roundTrip(func(*http.Request) (*http.Response, error) { t.Fatal("forbidden runtime access"); return nil, nil })
		for _, method := range []string{"GET", "PUT", "DELETE"} {
			path := "/v1/plugins"
			if method != "GET" {
				path += "/org.uai.hello"
			}
			if w := scopedRequest(s, method, path, `{"enabled":true,"config":{}}`); w.Code != 403 {
				t.Fatal(actor, method, w.Code)
			}
		}
	}
}

func TestPluginDesiredStateSurvivesApplyFailureAndRetries(t *testing.T) {
	store, s := setup(t)
	fail := true
	applies := 0
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		status, body := 204, ""
		if r.URL.Path == "/internal/v1/plugins/reconcile" {
			applies++
			status = 200
			body = `{"applied":true,"revision":2}`
			if fail {
				status = 500
				body = `{"detail":"private secret"}`
			}
		}
		return &http.Response{StatusCode: status, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(body))}, nil
	})
	r := httptest.NewRequest("PUT", "/v1/plugins/org.uai.hello", strings.NewReader(`{"enabled":true,"config":{}}`))
	r.Header.Set("Authorization", "Bearer test-key")
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("If-Match", `"1"`)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 202 || strings.Contains(w.Body.String(), "secret") {
		t.Fatal(w.Code, w.Body)
	}
	config, _ := store.PluginConfiguration(context.Background())
	if config.Revision != 2 {
		t.Fatal("desired state was lost")
	}
	fail = false
	if err := s.ensurePlugins(context.Background()); err != nil || applies != 2 {
		t.Fatal(err, applies)
	}
	// Deleting the final entry must still reconcile, including after runtime restart.
	store.pluginConfig = PluginConfiguration{Revision: 3, Settings: map[string]PluginSetting{}}
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		applies++
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"applied":true,"revision":3}`))}, nil
	})
	if err := s.ensurePlugins(context.Background()); err != nil || applies != 3 {
		t.Fatal(err, applies)
	}
}

func TestPluginConfigRejectsUnsafeInputBeforeRuntime(t *testing.T) {
	for _, body := range []string{`{"enabled":true,"config":{},"import_path":"secret"}`, `{"enabled":true,"config":null}`, `{"config":{}}`, `{"enabled":true,"config":[]}`} {
		_, s := setup(t)
		s.client.Transport = roundTrip(func(*http.Request) (*http.Response, error) { t.Fatal("invalid input reached runtime"); return nil, nil })
		r := httptest.NewRequest("PUT", "/v1/plugins/org.uai.hello", strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer test-key")
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("If-Match", `"1"`)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != 422 {
			t.Fatal(w.Code, w.Body)
		}
	}
}

func TestPluginCatalogRejectsPrivateMetadataAndRedirects(t *testing.T) {
	for _, body := range []string{
		`[{"manifest":{"id":"org.uai.hello","runtime":"python","api_key":"secret"},"state":"active"}]`,
		`[{"manifest":{"id":"../../secret","runtime":"python"},"state":"active"}]`,
		`[{"manifest":{"id":"org.uai.hello","runtime":"python"},"state":"invented"}]`,
		`null`, strings.Repeat("x", 2097153),
	} {
		_, s := setup(t)
		s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
			data := body
			if r.Method == "POST" {
				data = `{"applied":true,"revision":1}`
			}
			return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(data))}, nil
		})
		r := httptest.NewRequest("GET", "/v1/plugins", nil)
		r.Header.Set("Authorization", "Bearer test-key")
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != 503 || strings.Contains(w.Body.String(), "secret") {
			t.Fatal(w.Code, w.Body)
		}
	}
	_, s := setup(t)
	calls := 0
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 302, Header: http.Header{"Location": []string{"http://elsewhere/steal"}}, Body: http.NoBody}, nil
	})
	if _, err := s.runtimePlugins(context.Background()); err == nil || calls != 1 {
		t.Fatal(err, calls)
	}
}

type pluginSaveFailureStore struct{ memoryStore }

func (s *pluginSaveFailureStore) UpdatePluginConfiguration(context.Context, int, map[string]PluginSetting) (PluginConfiguration, error) {
	return PluginConfiguration{}, ErrConflict
}
func TestPluginSaveFailureNeverAppliesUnsavedConfiguration(t *testing.T) {
	_, s := setup(t)
	s.store = &pluginSaveFailureStore{}
	calls := 0
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		calls++
		if r.URL.Path != "/internal/v1/plugins/validate" {
			t.Fatal("applied unsaved config", r.URL.Path)
		}
		return &http.Response{StatusCode: 204, Body: http.NoBody}, nil
	})
	r := httptest.NewRequest("PUT", "/v1/plugins/org.uai.hello", strings.NewReader(`{"enabled":true,"config":{}}`))
	r.Header.Set("Authorization", "Bearer test-key")
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("If-Match", `"1"`)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 409 || calls != 1 {
		t.Fatal(w.Code, w.Body, calls)
	}
}
