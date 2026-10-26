package main

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

const toolCatalogFixture = `[{"id":"builtin.text_stats","name":"Text statistics","description":"Read-only counts","version":"1.0.0","input_schema":{"type":"object"},"output_schema":{"type":"object"},"permissions":["tools:execute"],"risk_level":"read_only","timeout":1,"retry_policy":"never","executor":"builtin"}]`

func TestToolCatalogRequiresExplicitReadScope(t *testing.T) {
	_, denied := authSetup(t, "reader", []string{"assistants:read"})
	denied.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) { t.Fatal("unauthorized catalog fetch"); return nil, nil })
	if w := scopedRequest(denied, "GET", "/v1/tools", ""); w.Code != 403 {
		t.Fatal(w.Code, w.Body)
	}
	_, s := authSetup(t, "reader", []string{"tools:read"})
	calls := 0
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		calls++
		if r.Method != "GET" || r.URL.String() != "http://runtime/internal/v1/tools" || r.Header.Get("Authorization") != "Bearer internal-secret" {
			t.Fatal("unsafe internal request", r)
		}
		if deadline, ok := r.Context().Deadline(); !ok || time.Until(deadline) > 5*time.Second {
			t.Fatal("unbounded catalog request")
		}
		return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(toolCatalogFixture))}, nil
	})
	w := scopedRequest(s, "GET", "/v1/tools", "")
	if w.Code != 200 || calls != 1 {
		t.Fatal(w.Code, w.Body, calls)
	}
	var tools []map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &tools); err != nil || len(tools) != 1 || tools[0]["id"] != "builtin.text_stats" {
		t.Fatal(err, tools)
	}
	r := scopedRequest(s, "POST", "/v1/tools", `{"python":"arbitrary"}`)
	if r.Code == 200 || r.Code == 201 {
		t.Fatal("public code installation enabled")
	}
}

func TestToolCatalogRejectsPrivateOrInvalidRuntimeResponses(t *testing.T) {
	for _, data := range []string{
		strings.Replace(toolCatalogFixture, `"executor":"builtin"`, `"executor":"builtin","api_key":"secret"`, 1),
		strings.Replace(toolCatalogFixture, `"executor":"builtin"`, `"executor":"python_module"`, 1),
		strings.Replace(toolCatalogFixture, `"timeout":1`, `"timeout":0`, 1),
		strings.Replace(toolCatalogFixture, `"input_schema":{"type":"object"}`, `"input_schema":null`, 1),
		"null", toolCatalogFixture + " {}", "[" + strings.Trim(toolCatalogFixture, "[]") + "," + strings.Trim(toolCatalogFixture, "[]") + "]", strings.Repeat("x", 1048577),
	} {
		_, s := authSetup(t, "reader", []string{"tools:read"})
		s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(data))}, nil
		})
		w := scopedRequest(s, "GET", "/v1/tools", "")
		if w.Code != 503 || strings.Contains(w.Body.String(), "secret") {
			t.Fatal(w.Code, w.Body)
		}
	}
	_, s := authSetup(t, "reader", []string{"tools:read"})
	calls := 0
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 302, Header: http.Header{"Location": []string{"http://other/steal"}}, Body: http.NoBody}, nil
	})
	if w := scopedRequest(s, "GET", "/v1/tools", ""); w.Code != 503 || calls != 1 {
		t.Fatal(w.Code, w.Body, calls)
	}
}

func TestToolCatalogAcceptsMetadataWithoutCountingHTMLTransportEscapes(t *testing.T) {
	_, s := authSetup(t, "reader", []string{"tools:read"})
	description := strings.Repeat("<&", 1000)
	data := strings.Replace(toolCatalogFixture, "Read-only counts", description, 1)
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(data))}, nil
	})
	w := scopedRequest(s, "GET", "/v1/tools", "")
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body)
	}
	var tools []ToolDefinition
	if err := json.Unmarshal(w.Body.Bytes(), &tools); err != nil || tools[0].Description != description {
		t.Fatal(err, "metadata changed")
	}
}

const httpToolCatalogFixture = `[{"id":"example.lookup","name":"Lookup","description":"Reads a lookup","version":"1.0.0","input_schema":{"type":"object"},"output_schema":{"type":"object"},"permissions":["tools:execute","connector:example"],"risk_level":"read_only","timeout":1,"retry_policy":"never","executor":"http"}]`

func TestToolCatalogAcceptsBoundReadOnlyHTTPAndMCPTools(t *testing.T) {
	for _, fixture := range []string{
		httpToolCatalogFixture,
		strings.Replace(httpToolCatalogFixture, `"executor":"http"`, `"executor":"mcp"`, 1),
	} {
		_, s := authSetup(t, "reader", []string{"tools:read"})
		s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(fixture))}, nil
		})
		if w := scopedRequest(s, "GET", "/v1/tools", ""); w.Code != 200 {
			t.Fatal(w.Code, w.Body)
		}
	}
}

func TestToolCatalogRejectsUnboundOrMutatingRemoteTools(t *testing.T) {
	for _, fixture := range []string{
		strings.Replace(httpToolCatalogFixture, `,"connector:example"`, ``, 1),
		strings.Replace(httpToolCatalogFixture, `"connector:example"`, `"connector:one","connector:two"`, 1),
		strings.Replace(httpToolCatalogFixture, `"risk_level":"read_only"`, `"risk_level":"write"`, 1),
		strings.Replace(httpToolCatalogFixture, `"risk_level":"read_only"`, `"risk_level":"destructive"`, 1),
		strings.Replace(httpToolCatalogFixture, `"executor":"http"`, `"executor":"builtin"`, 1),
	} {
		_, s := authSetup(t, "reader", []string{"tools:read"})
		s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(fixture))}, nil
		})
		if w := scopedRequest(s, "GET", "/v1/tools", ""); w.Code != 503 {
			t.Fatal(w.Code, w.Body)
		}
	}
}
