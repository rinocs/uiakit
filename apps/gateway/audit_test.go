package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestAuditRedactionRemovesCredentialsAndBodiesRecursively(t *testing.T) {
	value := redactAuditDetails(map[string]any{
		"authorization": "Bearer secret",
		"nested":        map[string]any{"api_key": "k", "tool": "read"},
		"list":          []any{map[string]any{"password": "p"}, "ok"},
		"arguments":     map[string]any{"q": "private"},
		"result":        "private result",
	})
	encoded, _ := json.Marshal(value)
	text := string(encoded)
	for _, secret := range []string{"Bearer", `"k"`, `"p"`, "private", `"q"`} {
		if strings.Contains(text, secret) {
			t.Fatalf("audit details leaked %q: %s", secret, text)
		}
	}
	if !strings.Contains(text, `"[redacted]"`) || !strings.Contains(text, `"tool":"read"`) {
		t.Fatal(text)
	}
}

func TestAuditRejectsInvalidRecordsBeforeWriting(t *testing.T) {
	for _, record := range []AuditRecord{
		{ActorID: "user-1", Action: "Bad Action", TargetID: "00000000-0000-4000-8000-000000000001"},
		{ActorID: "user-1", Action: "tool.ok", TargetID: "bad"},
		{ActorID: "user-1", Action: "tool.ok", TargetID: "00000000-0000-4000-8000-000000000001", Digest: "short"},
	} {
		if err := recordAudit(context.Background(), nil, record); err != ErrInvalidConfig {
			t.Fatalf("expected ErrInvalidConfig, got %v", err)
		}
	}
}

func seedAudit(store *authStore, action, runID, targetID string, details string) {
	store.audits = append(store.audits, AuditEvent{
		ID: int64(len(store.audits) + 1), ActorPrincipalID: "user-1", Action: action,
		TargetID: targetID, TargetType: "tool_execution", RunID: runID,
		CorrelationID: "00000000-0000-4000-8000-000000000099", Digest: strings.Repeat("a", 64),
		Outcome: "completed", Details: json.RawMessage(details), CreatedAt: time.Now().UTC(),
	})
}

func TestAuditReadRequiresScopeFiltersAndRedacts(t *testing.T) {
	store, s := authSetup(t, "admin", []string{"audit:read"})
	runID := "00000000-0000-4000-8000-000000000003"
	seedAudit(store, "tool_execution.completed", runID,
		"00000000-0000-4000-8000-000000000004", `{"authorization":"Bearer secret","tool_id":"t"}`)
	seedAudit(store, "approval.approved", "00000000-0000-4000-8000-000000000005",
		"00000000-0000-4000-8000-000000000006", `{"safe":true}`)

	if direct, err := store.AuditEvents(context.Background(), AuditFilter{RunID: runID}); err != nil || len(direct) != 1 {
		t.Fatalf("direct audit seed: %d %v", len(direct), err)
	}
	w := scopedRequest(s, "GET", "/v1/audit-events?run_id="+runID, "")
	if w.Code != 200 || strings.Contains(w.Body.String(), "Bearer secret") ||
		!strings.Contains(w.Body.String(), `"tool_execution.completed"`) ||
		!strings.Contains(w.Body.String(), `"[redacted]"`) {
		t.Fatalf("audit read: %d %s", w.Code, w.Body)
	}
	if w = scopedRequest(s, "GET", "/v1/audit-events?action=tool_execution.completed&limit=1", ""); w.Code != 200 {
		t.Fatal(w.Code, w.Body)
	}
	if w = scopedRequest(s, "GET", "/v1/audit-events?run_id=bad", ""); w.Code != 422 {
		t.Fatal(w.Code, w.Body)
	}
	if w = scopedRequest(s, "GET", "/v1/audit-events?limit=0", ""); w.Code != 422 {
		t.Fatal(w.Code, w.Body)
	}

	_, reader := authSetup(t, "operator", []string{"audit:read"})
	if w = scopedRequest(reader, "GET", "/v1/audit-events", ""); w.Code != 403 {
		t.Fatalf("operator without audit role scope: %d", w.Code)
	}
}
