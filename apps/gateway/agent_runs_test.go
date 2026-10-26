package main

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

type agentRunStore struct {
	*documentStore
	runs map[string]AgentRun
}

func newAgentRunStore() *agentRunStore {
	return &agentRunStore{documentStore: newDocumentStore(), runs: map[string]AgentRun{}}
}

func (s *agentRunStore) AgentRuns(ctx context.Context) ([]AgentRun, error) {
	out := []AgentRun{}
	for _, run := range s.runs {
		if p := currentPrincipal(ctx); p.isAdmin() || p.ID == "user-a" {
			out = append(out, run)
		}
	}
	return out, nil
}

func (s *agentRunStore) AgentRun(_ context.Context, id string) (AgentRun, error) {
	run, ok := s.runs[id]
	if !ok {
		return AgentRun{}, ErrNotFound
	}
	return run, nil
}

func (s *agentRunStore) CancelAgentRun(_ context.Context, id string) (AgentRun, error) {
	run, ok := s.runs[id]
	if !ok {
		return AgentRun{}, ErrNotFound
	}
	if run.Status != "queued" && run.Status != "running" && run.Status != "waiting_approval" {
		return AgentRun{}, ErrConflict
	}
	now := time.Now().UTC()
	run.Status = "cancelled"
	run.UpdatedAt = now
	run.CancelRequestedAt = &now
	s.runs[id] = run
	return run, nil
}

func TestAgentRunListGetCancelAndConflict(t *testing.T) {
	store := newAgentRunStore()
	s := NewServer(store, Config{Model: "test", RuntimeURL: "http://runtime", InternalKey: "internal-secret"})
	s.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		if r.URL.Path == "/internal/v1/runs/00000000-0000-4000-8000-000000000009/cancel" && r.Method == "POST" {
			return &http.Response{StatusCode: 204, Body: io.NopCloser(strings.NewReader(""))}, nil
		}
		return &http.Response{StatusCode: 500, Body: io.NopCloser(strings.NewReader(""))}, nil
	})
	run := AgentRun{ID: "00000000-0000-4000-8000-000000000009",
		ConversationID: "00000000-0000-4000-8000-000000000002", Status: "running",
		AssistantID: "00000000-0000-4000-8000-000000000001", AssistantVersion: 1,
		Model: "test", CreatedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC()}
	store.runs[run.ID] = run
	if w := kbRequest(s, "GET", "/v1/agent-runs", "", "key-a", ""); w.Code != 200 || !strings.Contains(w.Body.String(), run.ID) {
		t.Fatalf("list: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "GET", "/v1/agent-runs/"+run.ID, "", "key-a", ""); w.Code != 200 {
		t.Fatalf("get: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "POST", "/v1/agent-runs/"+run.ID+"/cancel", "", "key-a", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"cancelled"`) {
		t.Fatalf("cancel: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "POST", "/v1/agent-runs/"+run.ID+"/cancel", "", "key-a", ""); w.Code != 409 {
		t.Fatalf("repeat: %d %s", w.Code, w.Body)
	}
}
