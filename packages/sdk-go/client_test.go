package uai

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func eventJSON(eventID, eventType string, payload any) string {
	raw, _ := json.Marshal(payload)
	return fmt.Sprintf(
		`{"event_id":%q,"event_type":%q,"event_version":1,"timestamp":"2026-10-22T00:00:00Z","run_id":"run-1","correlation_id":"corr-1","payload":%s}`,
		eventID, eventType, raw,
	)
}

func writeEvent(w io.Writer, eventID, eventType string, payload any) {
	fmt.Fprintf(w, "id: %s\nevent: %s\ndata: %s\n\n", eventID, eventType, eventJSON(eventID, eventType, payload))
	if flusher, ok := w.(http.Flusher); ok {
		flusher.Flush()
	}
}

func newTestClient(t *testing.T, handler http.Handler) (*Client, *httptest.Server) {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	client, err := New(server.URL, "uai_test")
	if err != nil {
		t.Fatal(err)
	}
	return client, server
}

func TestSendMessageStreamsTerminalEvent(t *testing.T) {
	client, _ := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/v1/conversations/conversation-1/messages" {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer uai_test" {
			t.Errorf("missing bearer token")
		}
		if r.Header.Get("Idempotency-Key") != "idem-1" {
			t.Errorf("missing idempotency key")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("X-Run-ID", "run-1")
		w.Header().Set("X-Assistant-Version", "2")
		writeEvent(w, "e1", "agent.started", map[string]any{})
		writeEvent(w, "e2", "response.delta", map[string]any{"text": "caffè 😀"})
		writeEvent(w, "e3", "response.completed", map[string]any{
			"text":  "caffè 😀",
			"usage": map[string]any{"input_tokens": 1, "output_tokens": 2},
		})
	}))

	stream, err := client.SendMessage(context.Background(), "conversation-1", MessageInput{Content: "ciao"}, "idem-1")
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if stream.RunID != "run-1" || stream.AssistantVersion != 2 {
		t.Fatalf("unexpected stream metadata: %#v", stream)
	}

	var types []string
	for {
		event, err := stream.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		types = append(types, event.EventType)
		if event.EventType == "response.delta" {
			var payload TextPayload
			if err := event.DecodePayload(&payload); err != nil {
				t.Fatal(err)
			}
			if payload.Text != "caffè 😀" {
				t.Fatalf("unexpected text: %q", payload.Text)
			}
		}
	}
	want := []string{"agent.started", "response.delta", "response.completed"}
	if strings.Join(types, ",") != strings.Join(want, ",") {
		t.Fatalf("got events %v, want %v", types, want)
	}
	if _, err := stream.Next(); !errors.Is(err, io.EOF) {
		t.Fatalf("expected EOF after terminal event, got %v", err)
	}
}

func TestSendMessageSurfacesAgentFailed(t *testing.T) {
	client, _ := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("X-Run-ID", "run-1")
		writeEvent(w, "e1", "agent.started", map[string]any{})
		writeEvent(w, "e2", "agent.failed", map[string]any{"code": "provider_error"})
	}))

	stream, err := client.SendMessage(context.Background(), "conversation-1", MessageInput{Content: "x"}, "idem-failed")
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if _, err := stream.Next(); err != nil {
		t.Fatal(err)
	}
	event, err := stream.Next()
	if event.EventType != "agent.failed" {
		t.Fatalf("unexpected event: %s", event.EventType)
	}
	var agentErr *AgentFailedError
	if !errors.As(err, &agentErr) || agentErr.Code != "provider_error" {
		t.Fatalf("expected AgentFailedError, got %v", err)
	}
}

func TestSendMessageTreatsEOFWithoutTerminalAsIncomplete(t *testing.T) {
	client, _ := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("X-Run-ID", "run-1")
		writeEvent(w, "e1", "agent.started", map[string]any{})
	}))

	stream, err := client.SendMessage(context.Background(), "conversation-1", MessageInput{Content: "x"}, "idem-eof")
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if _, err := stream.Next(); err != nil {
		t.Fatal(err)
	}
	var incomplete *StreamIncompleteError
	if _, err := stream.Next(); !errors.As(err, &incomplete) {
		t.Fatalf("expected StreamIncompleteError, got %v", err)
	}
}

func TestSendMessageRequiresIdempotencyKey(t *testing.T) {
	var calls atomic.Int32
	client, _ := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
	}))
	_, err := client.SendMessage(context.Background(), "conversation-1", MessageInput{Content: "x"}, "  ")
	var validation *ValidationError
	if !errors.As(err, &validation) {
		t.Fatalf("expected ValidationError, got %v", err)
	}
	if calls.Load() != 0 {
		t.Fatalf("gateway was called")
	}
}

func TestSendMessageAbortPropagatesAndCancelsRun(t *testing.T) {
	var cancelled atomic.Int32
	client, _ := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/conversations/conversation-1/messages":
			w.Header().Set("Content-Type", "text/event-stream")
			w.Header().Set("X-Run-ID", "run-1")
			writeEvent(w, "e1", "agent.started", map[string]any{})
			<-r.Context().Done()
		case "/v1/agent-runs/run-1/cancel":
			cancelled.Add(1)
			w.Header().Set("Content-Type", "application/json")
			fmt.Fprint(w, `{"id":"run-1","status":"cancelled"}`)
		default:
			http.NotFound(w, r)
		}
	}))

	ctx, cancel := context.WithCancel(context.Background())
	stream, err := client.SendMessage(ctx, "conversation-1", MessageInput{Content: "x"}, "idem-abort")
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if _, err := stream.Next(); err != nil {
		t.Fatal(err)
	}
	cancel()
	var abortErr *AbortError
	if _, err := stream.Next(); !errors.As(err, &abortErr) {
		t.Fatalf("expected AbortError, got %v", err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for cancelled.Load() == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if cancelled.Load() == 0 {
		t.Fatal("run cancellation was not requested")
	}
}

func TestAPIErrorNormalization(t *testing.T) {
	client, _ := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		fmt.Fprint(w, `{"error":"forbidden"}`)
	}))
	_, err := client.ListAssistants(context.Background())
	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("expected APIError, got %v", err)
	}
	if apiErr.Status != 403 || apiErr.Code != "forbidden" {
		t.Fatalf("unexpected APIError: %#v", apiErr)
	}
}

func TestOperationsMatchPublicContract(t *testing.T) {
	raw, err := os.ReadFile("../api-contract/public.openapi.json")
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Paths map[string]map[string]json.RawMessage `json:"paths"`
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	expected := map[string]Operation{}
	for path, item := range document.Paths {
		for method, rawOperation := range item {
			if method == "parameters" {
				continue
			}
			var operation struct {
				OperationID string `json:"operationId"`
				Parameters  []struct {
					In       string `json:"in"`
					Name     string `json:"name"`
					Required bool   `json:"required"`
				} `json:"parameters"`
			}
			if err := json.Unmarshal(rawOperation, &operation); err != nil {
				t.Fatal(err)
			}
			headers := operation.Parameters
			var pathParameters []struct {
				In       string `json:"in"`
				Name     string `json:"name"`
				Required bool   `json:"required"`
			}
			if err := json.Unmarshal(item["parameters"], &pathParameters); err == nil {
				headers = append(headers, pathParameters...)
			}
			expected[operation.OperationID] = Operation{
				Method: strings.ToUpper(method),
				Path:   path,
			}
			for _, parameter := range headers {
				if parameter.In != "header" {
					continue
				}
				if parameter.Name == "Idempotency-Key" && parameter.Required {
					op := expected[operation.OperationID]
					op.RequiresIdempotencyKey = true
					expected[operation.OperationID] = op
				}
				if parameter.Name == "If-Match" && parameter.Required {
					op := expected[operation.OperationID]
					op.RequiresIfMatch = true
					expected[operation.OperationID] = op
				}
			}
		}
	}
	if len(expected) != len(Operations) {
		t.Fatalf("operation count: contract %d, SDK %d", len(expected), len(Operations))
	}
	for operationID, want := range expected {
		got, ok := Operations[operationID]
		if !ok {
			t.Fatalf("missing operation %s", operationID)
		}
		if got.Method != want.Method || got.Path != want.Path ||
			got.RequiresIdempotencyKey != want.RequiresIdempotencyKey ||
			got.RequiresIfMatch != want.RequiresIfMatch {
			t.Fatalf("operation %s mismatch: got %#v want %#v", operationID, got, want)
		}
	}
}

func TestSendMessageTimeoutPropagates(t *testing.T) {
	client, _ := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("X-Run-ID", "run-1")
		writeEvent(w, "e1", "agent.started", map[string]any{})
		<-r.Context().Done()
	}))

	ctx, cancel := context.WithTimeout(context.Background(), 250*time.Millisecond)
	defer cancel()
	stream, err := client.SendMessage(ctx, "conversation-1", MessageInput{Content: "x"}, "idem-timeout")
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if _, err := stream.Next(); err != nil {
		t.Fatal(err)
	}
	var timeoutErr *TimeoutError
	if _, err := stream.Next(); !errors.As(err, &timeoutErr) {
		t.Fatalf("expected TimeoutError, got %v", err)
	}
}
