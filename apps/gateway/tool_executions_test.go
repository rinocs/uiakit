package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func (s *memoryStore) initExecutions() {
	if s.toolExecutions == nil {
		s.toolExecutions = map[string]ToolExecution{}
	}
}

func (s *memoryStore) ReserveToolExecution(ctx context.Context, request ToolExecutionRequest) (ToolExecution, error) {
	if e := validateExecutionRequest(request); e != nil {
		return ToolExecution{}, e
	}
	s.toolExecutionMu.Lock()
	defer s.toolExecutionMu.Unlock()
	s.initExecutions()
	for _, execution := range s.toolExecutions {
		if execution.RunID != request.RunID || execution.IdempotencyKey != request.IdempotencyKey {
			continue
		}
		if execution.ToolID != request.ToolID || execution.ToolVersion != request.ToolVersion ||
			execution.ArgumentsDigest != request.ArgumentsDigest || execution.RiskLevel != request.RiskLevel {
			return ToolExecution{}, ErrConflict
		}
		if execution.Status == "completed" || execution.Status == "unknown" {
			return execution, nil
		}
		if execution.Status == "failed" && execution.RiskLevel == "read_only" &&
			execution.Attempt < execution.MaxAttempts {
			execution.Attempt++
			execution.Status, execution.ErrorCode = "reserved", nil
			execution.FinishedAt, execution.UpdatedAt = nil, nowUTC()
			s.toolExecutions[execution.ID] = execution
			return execution, nil
		}
		if execution.Status == "reserved" || execution.Status == "running" || execution.Status == "failed" {
			return ToolExecution{}, ErrConflict
		}
	}
	if s.runStatus[request.RunID] == "" {
		return ToolExecution{}, ErrNotFound
	}
	if request.ApprovalID != nil {
		s.approvalMu.Lock()
		defer s.approvalMu.Unlock()
		s.initApprovals()
		approval, ok := s.approvals[*request.ApprovalID]
		if !ok {
			return ToolExecution{}, ErrNotFound
		}
		if approval.Status != "approved" || !approval.ExpiresAt.After(nowUTC()) ||
			approval.RunID != request.RunID || approval.ToolID != request.ToolID ||
			approval.ToolVersion != request.ToolVersion || approval.ArgumentsDigest != request.ArgumentsDigest {
			return ToolExecution{}, ErrConflict
		}
		approval.Status = "consumed"
		now := nowUTC()
		approval.ConsumedAt = &now
		s.approvals[approval.ID] = approval
	}
	now := nowUTC()
	execution := ToolExecution{
		ID: newID(), RunID: request.RunID, ToolID: request.ToolID,
		ToolVersion: request.ToolVersion, ArgumentsDigest: request.ArgumentsDigest,
		ApprovalID: request.ApprovalID, RiskLevel: request.RiskLevel,
		IdempotencyKey: request.IdempotencyKey, Status: "reserved", Attempt: 1,
		MaxAttempts: request.MaxAttempts, CreatedAt: now, UpdatedAt: now,
	}
	s.toolExecutions[execution.ID] = execution
	return execution, nil
}

func (s *memoryStore) StartToolExecution(_ context.Context, id string) (ToolExecution, error) {
	s.toolExecutionMu.Lock()
	defer s.toolExecutionMu.Unlock()
	s.initExecutions()
	execution, ok := s.toolExecutions[id]
	if !ok {
		return ToolExecution{}, ErrNotFound
	}
	if execution.Status == "running" {
		return execution, nil
	}
	if execution.Status != "reserved" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.StartedAt, execution.UpdatedAt = "running", &now, now
	s.toolExecutions[id] = execution
	return execution, nil
}

func (s *memoryStore) CompleteToolExecution(_ context.Context, id string, result json.RawMessage) (ToolExecution, error) {
	if e := validateExecutionResult(result); e != nil {
		return ToolExecution{}, e
	}
	s.toolExecutionMu.Lock()
	defer s.toolExecutionMu.Unlock()
	s.initExecutions()
	execution, ok := s.toolExecutions[id]
	if !ok {
		return ToolExecution{}, ErrNotFound
	}
	if execution.Status == "completed" && string(execution.Result) == string(result) {
		return execution, nil
	}
	if execution.Status != "running" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.Result, execution.ErrorCode = "completed", result, nil
	execution.FinishedAt, execution.UpdatedAt = &now, now
	s.toolExecutions[id] = execution
	return execution, nil
}

func (s *memoryStore) FailToolExecution(_ context.Context, id, code string) (ToolExecution, error) {
	return s.finishFakeExecution(id, "failed", code)
}

func (s *memoryStore) UnknownToolExecution(_ context.Context, id, code string) (ToolExecution, error) {
	return s.finishFakeExecution(id, "unknown", code)
}

func (s *memoryStore) finishFakeExecution(id, status, code string) (ToolExecution, error) {
	if e := validateExecutionCode(code); e != nil {
		return ToolExecution{}, e
	}
	s.toolExecutionMu.Lock()
	defer s.toolExecutionMu.Unlock()
	s.initExecutions()
	execution, ok := s.toolExecutions[id]
	if !ok {
		return ToolExecution{}, ErrNotFound
	}
	if execution.Status == status && execution.ErrorCode != nil && *execution.ErrorCode == code {
		return execution, nil
	}
	if execution.Status != "running" && execution.Status != "reserved" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.ErrorCode = status, &code
	execution.FinishedAt, execution.UpdatedAt = &now, now
	s.toolExecutions[id] = execution
	return execution, nil
}

func (s *memoryStore) ReconcileToolExecution(_ context.Context, id, status string,
	result json.RawMessage, code string) (ToolExecution, error) {
	if status == "completed" {
		if e := validateExecutionResult(result); e != nil {
			return ToolExecution{}, e
		}
	} else if status != "failed" {
		return ToolExecution{}, ErrInvalidConfig
	} else if e := validateExecutionCode(code); e != nil {
		return ToolExecution{}, e
	}
	s.toolExecutionMu.Lock()
	defer s.toolExecutionMu.Unlock()
	s.initExecutions()
	execution, ok := s.toolExecutions[id]
	if !ok {
		return ToolExecution{}, ErrNotFound
	}
	if execution.Status != "unknown" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.FinishedAt, execution.UpdatedAt = status, &now, now
	if status == "completed" {
		execution.Result, execution.ErrorCode = result, nil
	} else {
		execution.Result, execution.ErrorCode = nil, &code
	}
	s.toolExecutions[id] = execution
	return execution, nil
}

func (s *memoryStore) ToolExecution(_ context.Context, id string) (ToolExecution, error) {
	s.toolExecutionMu.Lock()
	defer s.toolExecutionMu.Unlock()
	s.initExecutions()
	execution, ok := s.toolExecutions[id]
	if !ok {
		return ToolExecution{}, ErrNotFound
	}
	return execution, nil
}

func internalRequest(s http.Handler, method, path, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer internal-secret")
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w
}

func executionRequest(key string, risk string, approval *string) string {
	body := map[string]any{
		"run_id": "00000000-0000-4000-8000-000000000009", "tool_id": "test.read",
		"tool_version": "1.0.0", "arguments_digest": strings.Repeat("a", 64),
		"risk_level": risk, "idempotency_key": key, "max_attempts": 2,
	}
	if risk != "read_only" {
		body["max_attempts"] = 1
	}
	if approval != nil {
		body["approval_id"] = *approval
	}
	data, _ := json.Marshal(body)
	return string(data)
}

func TestToolExecutionReserveStartCompleteAndReplay(t *testing.T) {
	store, s := authSetup(t, "admin", []string{})
	store.runStatus = map[string]string{"00000000-0000-4000-8000-000000000009": "running"}
	w := internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", executionRequest("key-1", "read_only", nil))
	if w.Code != 200 || !strings.Contains(w.Body.String(), `"status":"reserved"`) {
		t.Fatalf("reserve: %d %s", w.Code, w.Body)
	}
	var execution ToolExecution
	if err := json.Unmarshal(w.Body.Bytes(), &execution); err != nil {
		t.Fatal(err)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/start", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"running"`) {
		t.Fatalf("start: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/complete", `{"result":{"ok":true}}`); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"completed"`) {
		t.Fatalf("complete: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", executionRequest("key-1", "read_only", nil)); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"completed"`) || !strings.Contains(w.Body.String(), `"ok":true`) {
		t.Fatalf("replay: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", executionRequest("key-1", "read_only", nil)); w.Code != 200 {
		t.Fatalf("second replay: %d %s", w.Code, w.Body)
	}
}

func TestToolExecutionReadOnlyRetryAndMutatingApprovalConsumption(t *testing.T) {
	store, s := authSetup(t, "admin", []string{})
	store.runStatus = map[string]string{"00000000-0000-4000-8000-000000000009": "running"}
	w := internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", executionRequest("key-retry", "read_only", nil))
	var execution ToolExecution
	if err := json.Unmarshal(w.Body.Bytes(), &execution); err != nil || w.Code != 200 {
		t.Fatalf("reserve: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/start", ""); w.Code != 200 {
		t.Fatalf("start: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/fail", `{"error_code":"tool_timeout"}`); w.Code != 200 {
		t.Fatalf("fail: %d %s", w.Code, w.Body)
	}
	w = internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", executionRequest("key-retry", "read_only", nil))
	if w.Code != 200 || !strings.Contains(w.Body.String(), `"attempt":2`) || !strings.Contains(w.Body.String(), `"status":"reserved"`) {
		t.Fatalf("retry: %d %s", w.Code, w.Body)
	}

	approval := seedApproval(store, "approved", time.Now().UTC().Add(time.Minute), "running")
	approval.ToolID, approval.ToolVersion, approval.ArgumentsDigest = "test.write", "1.0.0", strings.Repeat("a", 64)
	store.approvalMu.Lock()
	store.approvals[approval.ID] = approval
	store.approvalMu.Unlock()
	body := strings.Replace(executionRequest("key-write", "write", &approval.ID), `"tool_id":"test.read"`, `"tool_id":"test.write"`, 1)
	w = internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", body)
	if w.Code != 200 || !strings.Contains(w.Body.String(), `"approval_id":"`+approval.ID+`"`) {
		t.Fatalf("mutating reserve: %d %s", w.Code, w.Body)
	}
	store.approvalMu.Lock()
	status := store.approvals[approval.ID].Status
	store.approvalMu.Unlock()
	if status != "consumed" {
		t.Fatalf("approval not consumed: %s", status)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", body); w.Code != 409 {
		t.Fatalf("reused approval execution: %d %s", w.Code, w.Body)
	}
}

func TestToolExecutionUnknownIsNotRetriedAndAuthIsRequired(t *testing.T) {
	store, s := authSetup(t, "admin", []string{})
	store.runStatus = map[string]string{"00000000-0000-4000-8000-000000000009": "running"}
	w := internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", executionRequest("key-unknown", "read_only", nil))
	var execution ToolExecution
	if err := json.Unmarshal(w.Body.Bytes(), &execution); err != nil {
		t.Fatal(err)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/start", ""); w.Code != 200 {
		t.Fatalf("start: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/unknown", `{"error_code":"effect_unknown"}`); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"unknown"`) {
		t.Fatalf("unknown: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/reserve", executionRequest("key-unknown", "read_only", nil)); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"unknown"`) {
		t.Fatalf("unknown retried: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/reconcile",
		`{"status":"completed","result":{"reconciled":true}}`); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"status":"completed"`) {
		t.Fatalf("reconcile: %d %s", w.Code, w.Body)
	}
	if w = internalRequest(s, "POST", "/internal/v1/tool-executions/"+execution.ID+"/reconcile",
		`{"status":"completed","result":{"reconciled":true}}`); w.Code != 409 {
		t.Fatalf("double reconcile: %d %s", w.Code, w.Body)
	}
	req := httptest.NewRequest("POST", "/internal/v1/tool-executions/reserve", strings.NewReader(executionRequest("key-auth", "read_only", nil)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	s.ServeHTTP(rec, req)
	if rec.Code != 401 {
		t.Fatalf("internal auth: %d %s", rec.Code, rec.Body)
	}
}

func TestConcurrentReserveOnlyOneExecutionWins(t *testing.T) {
	store, s := authSetup(t, "admin", []string{})
	store.runStatus = map[string]string{"00000000-0000-4000-8000-000000000009": "running"}
	var wg sync.WaitGroup
	codes := make(chan int, 2)
	for range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			codes <- internalRequest(s, "POST", "/internal/v1/tool-executions/reserve",
				executionRequest("key-concurrent", "read_only", nil)).Code
		}()
	}
	wg.Wait()
	close(codes)
	seen := map[int]int{}
	for code := range codes {
		seen[code]++
	}
	if seen[200] != 1 || seen[409] != 1 {
		t.Fatalf("concurrent reserve: %v", seen)
	}
}
