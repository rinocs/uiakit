package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func directiveRequest(s *server, method, path, body string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	r.Header.Set("Authorization", "Bearer test-key")
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("If-Match", `"1"`)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	return w
}

func TestDirectiveSelectionValidatedBeforeAssistantVersionIsSaved(t *testing.T) {
	for _, status := range []int{204, 422, 401, 500, 302, 0} {
		t.Run(http.StatusText(status), func(t *testing.T) {
			store, s := versionSetup(t)
			validations := 0
			s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
				validations++
				if r.URL.String() != "http://runtime/internal/v1/directives/validate" || r.Method != "POST" || r.Header.Get("Authorization") != "Bearer internal-secret" || r.Header.Get("Content-Type") != "application/json" {
					t.Fatal("invalid internal request", r.URL, r.Header)
				}
				if deadline, ok := r.Context().Deadline(); !ok || time.Until(deadline) > 5*time.Second {
					t.Fatal("missing bounded validation deadline")
				}
				var body struct {
					Directives []string `json:"directives"`
				}
				if e := json.NewDecoder(r.Body).Decode(&body); e != nil || len(body.Directives) != 1 || body.Directives[0] != "registered" {
					t.Fatal("invalid selection", body, e)
				}
				if status == 0 {
					return nil, context.DeadlineExceeded
				}
				return &http.Response{StatusCode: status, Header: http.Header{"Location": []string{"http://other/steal"}}, Body: io.NopCloser(strings.NewReader("private diagnostic"))}, nil
			})
			w := directiveRequest(s, "PATCH", "/v1/assistants/"+store.assistant.ID, `{"directives":["registered"]}`)
			expected := 503
			if status == 204 {
				expected = 200
			}
			if status == 422 {
				expected = 422
			}
			if w.Code != expected || validations != 1 {
				t.Fatal(w.Code, w.Body, validations)
			}
			if strings.Contains(w.Body.String(), "private diagnostic") {
				t.Fatal("upstream detail leaked")
			}
			if status == 204 {
				if store.assistant.Version != 2 || store.assistant.Directives[0] != "registered" || len(store.versions[0].Directives) != 0 {
					t.Fatal("invalid version snapshots")
				}
				r := httptest.NewRequest("PATCH", "/v1/assistants/"+store.assistant.ID, strings.NewReader(`{"directives":[]}`))
				r.Header.Set("Authorization", "Bearer test-key")
				r.Header.Set("Content-Type", "application/json")
				r.Header.Set("If-Match", `"2"`)
				cleared := httptest.NewRecorder()
				s.ServeHTTP(cleared, r)
				if cleared.Code != 200 || store.assistant.Version != 3 || len(store.assistant.Directives) != 0 || validations != 1 || store.versions[1].Directives[0] != "registered" {
					t.Fatal("clearing selection changed prior version or called runtime", cleared.Code, validations)
				}
			} else if store.assistant.Version != 1 || len(store.versions) != 1 {
				t.Fatal("invalid selection saved")
			}
		})
	}
}

func TestCreateAssistantSupportsRegisteredDirectives(t *testing.T) {
	_, s := versionSetup(t)
	calls := 0
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 204, Header: http.Header{}, Body: http.NoBody}, nil
	})
	w := directiveRequest(s, "POST", "/v1/assistants", `{"name":"With directive","model":"test","system_prompt":"Helpful","directives":["registered"]}`)
	if w.Code != 201 || calls != 1 {
		t.Fatal(w.Code, w.Body, calls)
	}
	var a Assistant
	if e := json.Unmarshal(w.Body.Bytes(), &a); e != nil || len(a.Directives) != 1 || a.Directives[0] != "registered" {
		t.Fatal(a, e)
	}
}

func TestDirectiveNamesAreBoundedAndUniqueBeforeRuntimeCall(t *testing.T) {
	for _, selected := range [][]string{{"same", "same"}, {"bad name"}, {"../module"}, {strings.Repeat("a", 101)}, {"Uppercase"}, make([]string, 65)} {
		store, s := versionSetup(t)
		s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
			t.Fatal("invalid selection reached runtime")
			return nil, nil
		})
		body, _ := json.Marshal(map[string]any{"directives": selected})
		w := directiveRequest(s, "PATCH", "/v1/assistants/"+store.assistant.ID, string(body))
		if w.Code != 422 || store.assistant.Version != 1 {
			t.Fatal(w.Code, w.Body)
		}
	}
}
