package main

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

// Internal observability is not an extension of public SSE v1. An internal
// metadata frame accidentally crossing this boundary must fail closed.
func TestGatewayRejectsInternalLifecycleFrames(t *testing.T) {
	store, s := setup(t)
	original := s.client.Transport
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		response, err := original.RoundTrip(r)
		if err != nil {
			return response, err
		}
		data, err := io.ReadAll(response.Body)
		response.Body.Close()
		if err != nil {
			return nil, err
		}
		text := strings.Replace(string(data), `"event_type":"response.delta"`, `"event_type":"model.before"`, 1)
		response.Body = io.NopCloser(strings.NewReader(text))
		return response, nil
	})
	response := post(t, s, "/v1/conversations/00000000-0000-4000-8000-000000000002/messages", `{"content":"Hello"}`, "lifecycle-boundary")
	body := readAll(t, response.Body)
	if strings.Contains(body, "model.before") || strings.Contains(body, "response.completed") || !strings.Contains(body, "runtime_stream_failed") {
		t.Fatal(body)
	}
	if len(store.events) != 2 || store.events[0].Type != "agent.started" || store.events[1].Type != "agent.failed" {
		t.Fatal("internal metadata persisted as a public event", store.events)
	}
}
