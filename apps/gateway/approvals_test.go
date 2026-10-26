package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"
)

func (s *memoryStore) initApprovals() {
	if s.approvals == nil {
		s.approvals = map[string]Approval{}
	}
	if s.runStatus == nil {
		s.runStatus = map[string]string{}
	}
}

func (s *memoryStore) Approvals(_ context.Context) ([]Approval, error) {
	s.approvalMu.Lock()
	defer s.approvalMu.Unlock()
	s.initApprovals()
	now := nowUTC()
	out := []Approval{}
	for id, approval := range s.approvals {
		if (approval.Status == "pending" || approval.Status == "approved") && !approval.ExpiresAt.After(now) {
			approval.Status = "expired"
			s.approvals[id] = approval
		}
		out = append(out, approval)
	}
	return out, nil
}

func (s *memoryStore) Approval(_ context.Context, id string) (Approval, error) {
	s.approvalMu.Lock()
	defer s.approvalMu.Unlock()
	s.initApprovals()
	approval, ok := s.approvals[id]
	if !ok {
		return Approval{}, ErrNotFound
	}
	if (approval.Status == "pending" || approval.Status == "approved") && !approval.ExpiresAt.After(nowUTC()) {
		approval.Status = "expired"
		s.approvals[id] = approval
	}
	return approval, nil
}

func (s *memoryStore) DecideApproval(ctx context.Context, id, decision string) (Approval, error) {
	s.approvalMu.Lock()
	defer s.approvalMu.Unlock()
	s.initApprovals()
	approval, ok := s.approvals[id]
	if !ok {
		return Approval{}, ErrNotFound
	}
	now := nowUTC()
	if approval.Status == "pending" && !approval.ExpiresAt.After(now) {
		approval.Status = "expired"
		s.approvals[id] = approval
		return Approval{}, ErrConflict
	}
	if approval.Status != "pending" {
		return Approval{}, ErrConflict
	}
	if s.runStatus[approval.RunID] != "waiting_approval" {
		approval.Status = "invalidated"
		s.approvals[id] = approval
		return Approval{}, ErrConflict
	}
	approver := currentPrincipal(ctx).ID
	approval.DecidedAt = &now
	approval.DecidedBy = &approver
	if decision == "approve" {
		approval.Status = "approved"
		s.runStatus[approval.RunID] = "running"
	} else {
		approval.Status = "rejected"
		s.runStatus[approval.RunID] = "failed"
	}
	s.approvals[id] = approval
	return approval, nil
}

func seedApproval(store *authStore, status string, expires time.Time, runStatus string) Approval {
	store.approvalMu.Lock()
	defer store.approvalMu.Unlock()
	store.initApprovals()
	runID := "00000000-0000-4000-8000-000000000009"
	approval := Approval{
		ID: "00000000-0000-4000-8000-000000000010", RunID: runID,
		ToolID: "example.write", ToolVersion: "1.2.3",
		ArgumentsDigest: strings.Repeat("a", 64), PolicyDigest: strings.Repeat("b", 64),
		PolicySnapshot: json.RawMessage(`{"assistant":{"version":2},"tool":{"id":"example.write"}}`),
		RequestedBy:    "user-1", Status: status, CreatedAt: nowUTC(),
		ExpiresAt: expires,
	}
	store.approvals[approval.ID] = approval
	store.runStatus[runID] = runStatus
	return approval
}

func TestApprovalsListGetApproveAndRunResume(t *testing.T) {
	store, s := authSetup(t, "admin", []string{"approvals:read", "approvals:write"})
	approval := seedApproval(store, "pending", time.Now().UTC().Add(10*time.Minute), "waiting_approval")
	w := scopedRequest(s, "GET", "/v1/approvals", "")
	if w.Code != 200 || !strings.Contains(w.Body.String(), approval.ID) ||
		!strings.Contains(w.Body.String(), `"tool_version":"1.2.3"`) {
		t.Fatalf("list: %d %s", w.Code, w.Body)
	}
	if strings.Contains(w.Body.String(), `"q"`) || strings.Contains(w.Body.String(), "secret") {
		t.Fatal("approval list exposed mutable arguments or secrets")
	}
	if w = scopedRequest(s, "GET", "/v1/approvals/"+approval.ID, ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"policy_snapshot"`) {
		t.Fatalf("get: %d %s", w.Code, w.Body)
	}
	if w = scopedRequest(s, "POST", "/v1/approvals/"+approval.ID+"/approve", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"approved"`) {
		t.Fatalf("approve: %d %s", w.Code, w.Body)
	}
	if store.runStatus[approval.RunID] != "running" {
		t.Fatal("run did not resume after persisted approval")
	}
	if w = scopedRequest(s, "POST", "/v1/approvals/"+approval.ID+"/approve", ""); w.Code != 409 {
		t.Fatalf("reused approval: %d %s", w.Code, w.Body)
	}
}

func TestApprovalRejectExpiryAndRunState(t *testing.T) {
	store, s := authSetup(t, "admin", []string{"approvals:read", "approvals:write"})
	rejected := seedApproval(store, "pending", time.Now().UTC().Add(10*time.Minute), "waiting_approval")
	if w := scopedRequest(s, "POST", "/v1/approvals/"+rejected.ID+"/reject", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"rejected"`) {
		t.Fatalf("reject: %d %s", w.Code, w.Body)
	}
	if store.runStatus[rejected.RunID] != "failed" {
		t.Fatal("rejected approval did not fail the waiting run")
	}
	expired := seedApproval(store, "pending", time.Now().UTC().Add(-time.Second), "waiting_approval")
	if w := scopedRequest(s, "POST", "/v1/approvals/"+expired.ID+"/approve", ""); w.Code != 409 {
		t.Fatalf("expired: %d %s", w.Code, w.Body)
	}
	store.approvalMu.Lock()
	status := store.approvals[expired.ID].Status
	store.approvalMu.Unlock()
	if status != "expired" {
		t.Fatalf("expired approval was not persisted: %s", status)
	}
}

func TestApprovalScopesAndMissingIDs(t *testing.T) {
	store, s := authSetup(t, "operator", []string{"approvals:read"})
	approval := seedApproval(store, "pending", time.Now().UTC().Add(time.Minute), "waiting_approval")
	if w := scopedRequest(s, "GET", "/v1/approvals", ""); w.Code != 200 {
		t.Fatalf("read scope: %d %s", w.Code, w.Body)
	}
	if w := scopedRequest(s, "POST", "/v1/approvals/"+approval.ID+"/approve", ""); w.Code != 403 {
		t.Fatalf("write scope missing: %d %s", w.Code, w.Body)
	}
	_, reader := authSetup(t, "reader", []string{"approvals:read"})
	if w := scopedRequest(reader, "GET", "/v1/approvals", ""); w.Code != 403 {
		t.Fatalf("reader role: %d %s", w.Code, w.Body)
	}
	_, admin := authSetup(t, "admin", []string{"approvals:read"})
	if w := scopedRequest(admin, "GET", "/v1/approvals/not-an-id", ""); w.Code != 422 {
		t.Fatalf("invalid id: %d %s", w.Code, w.Body)
	}
	if w := scopedRequest(admin, "GET", "/v1/approvals/00000000-0000-4000-8000-000000000099", ""); w.Code != 404 {
		t.Fatalf("missing: %d %s", w.Code, w.Body)
	}
}

func TestConcurrentApprovalsOnlyOneDecisionWins(t *testing.T) {
	store, s := authSetup(t, "admin", []string{"approvals:read", "approvals:write"})
	approval := seedApproval(store, "pending", time.Now().UTC().Add(time.Minute), "waiting_approval")
	var wg sync.WaitGroup
	codes := make(chan int, 2)
	for range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			codes <- scopedRequest(s, "POST", "/v1/approvals/"+approval.ID+"/approve", "").Code
		}()
	}
	wg.Wait()
	close(codes)
	seen := map[int]int{}
	for code := range codes {
		seen[code]++
	}
	if seen[http.StatusOK] != 1 || seen[http.StatusConflict] != 1 {
		t.Fatalf("concurrent decisions: %v", seen)
	}
}
