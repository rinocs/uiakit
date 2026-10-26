package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
)

// AuditEvent is the protected, append-only security trail. Details never contain
// credentials, authorization headers, prompts, tool arguments or tool results.
type AuditEvent struct {
	ID               int64           `json:"id"`
	ActorPrincipalID string          `json:"actor_principal_id"`
	Action           string          `json:"action"`
	TargetID         string          `json:"target_id"`
	TargetType       string          `json:"target_type"`
	RunID            string          `json:"run_id,omitempty"`
	CorrelationID    string          `json:"correlation_id,omitempty"`
	Digest           string          `json:"digest,omitempty"`
	Outcome          string          `json:"outcome"`
	Details          json.RawMessage `json:"details"`
	CreatedAt        time.Time       `json:"created_at"`
}

type AuditFilter struct {
	RunID    string
	Action   string
	TargetID string
	Limit    int
}

type AuditRecord struct {
	ActorID       string
	Action        string
	TargetID      string
	TargetType    string
	RunID         string
	CorrelationID string
	Digest        string
	Outcome       string
	Details       map[string]any
}

var auditActionPattern = regexp.MustCompile(`^[a-z][a-z0-9_.-]{0,99}$`)
var auditKindPattern = regexp.MustCompile(`^[a-z][a-z0-9_]{0,49}$`)
var auditDigestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

func digestString(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func digestJSON(value any) string {
	data, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	return digestString(string(data))
}

func sensitiveAuditKey(key string) bool {
	normalized := strings.ToLower(strings.ReplaceAll(key, "-", "_"))
	switch normalized {
	case "authorization", "proxy_authorization", "cookie", "set_cookie", "x_api_key",
		"api_key", "apikey", "token", "access_token", "refresh_token", "id_token",
		"password", "passwd", "client_secret", "secret", "private_key", "key_digest",
		"credential", "credentials", "policy_snapshot", "system_prompt", "prompt",
		"messages", "content", "arguments", "result", "body", "headers",
		"request_body", "response_body":
		return true
	}
	return strings.Contains(normalized, "secret") || strings.Contains(normalized, "password") ||
		strings.Contains(normalized, "token") || strings.Contains(normalized, "authorization") ||
		strings.Contains(normalized, "cookie")
}

// redactAuditValue recursively removes sensitive fields before persistence or read.
func redactAuditValue(value any) any {
	switch v := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(v))
		for key, item := range v {
			if sensitiveAuditKey(key) {
				out[key] = "[redacted]"
				continue
			}
			out[key] = redactAuditValue(item)
		}
		return out
	case []any:
		out := make([]any, len(v))
		for i, item := range v {
			out[i] = redactAuditValue(item)
		}
		return out
	case []string:
		out := make([]any, len(v))
		for i, item := range v {
			out[i] = item
		}
		return out
	case json.RawMessage:
		var decoded any
		if json.Unmarshal(v, &decoded) != nil {
			return "[redacted]"
		}
		return redactAuditValue(decoded)
	case []byte:
		return redactAuditValue(json.RawMessage(v))
	case string, bool, nil, float64, int, int64, json.Number:
		return v
	default:
		// Unknown structures are not safe to persist without an explicit projection.
		return "[redacted]"
	}
}

func redactAuditDetails(details map[string]any) map[string]any {
	if details == nil {
		return map[string]any{}
	}
	redacted, ok := redactAuditValue(details).(map[string]any)
	if !ok {
		return map[string]any{}
	}
	return redacted
}

func recordAudit(ctx context.Context, tx pgx.Tx, record AuditRecord) error {
	if record.ActorID == "" {
		record.ActorID = currentPrincipal(ctx).ID
	}
	if record.TargetType == "" {
		record.TargetType = "resource"
	}
	if record.Outcome == "" {
		record.Outcome = "success"
	}
	if record.ActorID == "" || !auditActionPattern.MatchString(record.Action) ||
		!validID(record.TargetID) || !auditKindPattern.MatchString(record.TargetType) ||
		!auditKindPattern.MatchString(record.Outcome) {
		return ErrInvalidConfig
	}
	if record.RunID != "" && !validID(record.RunID) {
		return ErrInvalidConfig
	}
	if record.CorrelationID != "" && !validID(record.CorrelationID) {
		return ErrInvalidConfig
	}
	if record.Digest != "" && !auditDigestPattern.MatchString(record.Digest) {
		return ErrInvalidConfig
	}
	data, err := json.Marshal(redactAuditDetails(record.Details))
	if err != nil || len(data) > 16384 {
		return ErrInvalidConfig
	}
	var runID, correlationID, digest any
	if record.RunID != "" {
		runID = record.RunID
	}
	if record.CorrelationID != "" {
		correlationID = record.CorrelationID
	}
	if record.Digest != "" {
		digest = record.Digest
	}
	_, err = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id,
		target_type,run_id,correlation_id,digest,outcome,details)
		VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
		record.ActorID, record.Action, record.TargetID, record.TargetType,
		runID, correlationID, digest, record.Outcome, data)
	return err
}

func runAuditIdentity(ctx context.Context, tx pgx.Tx, runID string) (string, string, error) {
	var actor, correlation string
	err := tx.QueryRow(ctx, `SELECT c.owner_id,r.correlation_id::text
		FROM agent_runs r JOIN conversations c ON c.id=r.conversation_id WHERE r.id=$1`,
		runID).Scan(&actor, &correlation)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", "", ErrNotFound
	}
	return actor, correlation, err
}

func toolExecutionAudit(ctx context.Context, tx pgx.Tx, execution ToolExecution,
	action, outcome string) error {
	actor, correlation, err := runAuditIdentity(ctx, tx, execution.RunID)
	if err != nil {
		return err
	}
	details := map[string]any{
		"tool_id": execution.ToolID, "tool_version": execution.ToolVersion,
		"risk_level": execution.RiskLevel, "attempt": execution.Attempt,
		"max_attempts": execution.MaxAttempts, "status": execution.Status,
	}
	if execution.ErrorCode != nil {
		details["error_code"] = *execution.ErrorCode
	}
	return recordAudit(ctx, tx, AuditRecord{
		ActorID: actor, Action: action, TargetID: execution.ID,
		TargetType: "tool_execution", RunID: execution.RunID,
		CorrelationID: correlation, Digest: execution.ArgumentsDigest,
		Outcome: outcome, Details: details,
	})
}

const auditColumns = `id,actor_principal_id,action,target_id::text,target_type,
	COALESCE(run_id::text,''),COALESCE(correlation_id::text,''),COALESCE(digest,''),
	outcome,details,created_at`

func scanAuditEvent(row interface{ Scan(...any) error }) (AuditEvent, error) {
	var event AuditEvent
	var details []byte
	err := row.Scan(&event.ID, &event.ActorPrincipalID, &event.Action, &event.TargetID,
		&event.TargetType, &event.RunID, &event.CorrelationID, &event.Digest,
		&event.Outcome, &details, &event.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return AuditEvent{}, ErrNotFound
	}
	if err != nil {
		return AuditEvent{}, err
	}
	event.Details = redactedAuditJSON(details)
	return event, nil
}

func redactedAuditJSON(data []byte) json.RawMessage {
	var decoded any
	if len(data) == 0 || json.Unmarshal(data, &decoded) != nil {
		return json.RawMessage(`{}`)
	}
	out, err := json.Marshal(redactAuditValue(decoded))
	if err != nil {
		return json.RawMessage(`{}`)
	}
	return out
}

func (s *PostgresStore) AuditEvents(ctx context.Context, filter AuditFilter) ([]AuditEvent, error) {
	if filter.Limit == 0 {
		filter.Limit = 100
	}
	if filter.Limit < 1 || filter.Limit > 200 ||
		(filter.RunID != "" && !validID(filter.RunID)) ||
		(filter.TargetID != "" && !validID(filter.TargetID)) ||
		(filter.Action != "" && !auditActionPattern.MatchString(filter.Action)) {
		return nil, ErrInvalidConfig
	}
	where := []string{"true"}
	args := []any{}
	if filter.RunID != "" {
		args = append(args, filter.RunID)
		where = append(where, "run_id=$"+strconv.Itoa(len(args)))
	}
	if filter.Action != "" {
		args = append(args, filter.Action)
		where = append(where, "action=$"+strconv.Itoa(len(args)))
	}
	if filter.TargetID != "" {
		args = append(args, filter.TargetID)
		where = append(where, "target_id=$"+strconv.Itoa(len(args)))
	}
	args = append(args, filter.Limit)
	rows, err := s.pool.Query(ctx, `SELECT `+auditColumns+` FROM audit_events WHERE `+
		strings.Join(where, " AND ")+` ORDER BY id DESC LIMIT $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []AuditEvent{}
	for rows.Next() {
		event, err := scanAuditEvent(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, event)
	}
	return out, rows.Err()
}

func (s *server) auditRoutes(r chi.Router) {
	r.With(requireScope("audit:read")).Get("/v1/audit-events", s.auditEvents)
}

func (s *server) auditEvents(w http.ResponseWriter, r *http.Request) {
	filter := AuditFilter{RunID: r.URL.Query().Get("run_id"),
		Action: r.URL.Query().Get("action"), TargetID: r.URL.Query().Get("target_id")}
	if raw := r.URL.Query().Get("limit"); raw != "" {
		limit, err := strconv.Atoi(raw)
		if err != nil || limit < 1 || limit > 200 {
			problem(w, 422, "invalid_limit")
			return
		}
		filter.Limit = limit
	}
	if (filter.RunID != "" && !validID(filter.RunID)) ||
		(filter.TargetID != "" && !validID(filter.TargetID)) ||
		(filter.Action != "" && !auditActionPattern.MatchString(filter.Action)) {
		problem(w, 422, "invalid_filter")
		return
	}
	events, err := s.store.AuditEvents(r.Context(), filter)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 200, events)
}
