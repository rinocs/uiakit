package main

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"regexp"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

const toolExecutionColumns = `e.id::text,e.run_id::text,e.tool_id,e.tool_version,e.arguments_digest,
	e.approval_id::text,e.risk_level,e.idempotency_key,e.status,e.attempt,e.max_attempts,e.result,
	e.error_code,e.created_at,e.started_at,e.finished_at,e.updated_at`

const toolExecutionReturningColumns = `id::text,run_id::text,tool_id,tool_version,arguments_digest,
	approval_id::text,risk_level,idempotency_key,status,attempt,max_attempts,result,
	error_code,created_at,started_at,finished_at,updated_at`

var executionCodePattern = regexp.MustCompile(`^[a-z][a-z0-9_]{0,63}$`)

func scanToolExecution(row interface{ Scan(...any) error }) (ToolExecution, error) {
	var execution ToolExecution
	var result []byte
	e := row.Scan(&execution.ID, &execution.RunID, &execution.ToolID, &execution.ToolVersion,
		&execution.ArgumentsDigest, &execution.ApprovalID, &execution.RiskLevel,
		&execution.IdempotencyKey, &execution.Status, &execution.Attempt,
		&execution.MaxAttempts, &result, &execution.ErrorCode, &execution.CreatedAt,
		&execution.StartedAt, &execution.FinishedAt, &execution.UpdatedAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return ToolExecution{}, ErrNotFound
	}
	if len(result) > 0 {
		execution.Result = append(json.RawMessage(nil), result...)
	}
	return execution, e
}

func validateExecutionRequest(request ToolExecutionRequest) error {
	if !validID(request.RunID) || !toolIDPattern.MatchString(request.ToolID) ||
		!toolVersionPattern.MatchString(request.ToolVersion) || len(request.ArgumentsDigest) != 64 {
		return ErrInvalidConfig
	}
	if _, e := hex.DecodeString(request.ArgumentsDigest); e != nil {
		return ErrInvalidConfig
	}
	if request.RiskLevel != "read_only" && request.RiskLevel != "write" && request.RiskLevel != "destructive" {
		return ErrInvalidConfig
	}
	if request.IdempotencyKey == "" || len(request.IdempotencyKey) > 200 ||
		strings.TrimSpace(request.IdempotencyKey) != request.IdempotencyKey {
		return ErrInvalidConfig
	}
	if request.MaxAttempts < 1 || request.MaxAttempts > 3 {
		return ErrInvalidConfig
	}
	if request.ApprovalID != nil && !validID(*request.ApprovalID) {
		return ErrInvalidConfig
	}
	if len(request.PrincipalID) > 200 ||
		(request.CorrelationID != "" && !validID(request.CorrelationID)) {
		return ErrInvalidConfig
	}
	if request.RiskLevel != "read_only" && (request.ApprovalID == nil || request.MaxAttempts != 1) {
		return ErrInvalidConfig
	}
	return nil
}

func validateExecutionResult(result json.RawMessage) error {
	if len(result) == 0 || len(result) > 131072 || !json.Valid(result) {
		return ErrInvalidConfig
	}
	return nil
}

func validateExecutionCode(code string) error {
	if !executionCodePattern.MatchString(code) {
		return ErrInvalidConfig
	}
	return nil
}

func (s *PostgresStore) ReserveToolExecution(ctx context.Context, request ToolExecutionRequest) (ToolExecution, error) {
	if e := validateExecutionRequest(request); e != nil {
		return ToolExecution{}, e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return ToolExecution{}, e
	}
	defer tx.Rollback(ctx)
	execution, e := scanToolExecution(tx.QueryRow(ctx, `SELECT `+toolExecutionColumns+`
		FROM tool_executions e WHERE e.run_id=$1 AND e.idempotency_key=$2 FOR UPDATE`,
		request.RunID, request.IdempotencyKey))
	if e == nil {
		execution, e = s.existingExecution(ctx, tx, execution, request)
		if e != nil {
			return ToolExecution{}, e
		}
		return execution, tx.Commit(ctx)
	}
	if !errors.Is(e, ErrNotFound) {
		return ToolExecution{}, e
	}
	now := nowUTC()
	if request.ApprovalID != nil {
		var status, runID, toolID, toolVersion, digest string
		var expires time.Time
		e = tx.QueryRow(ctx, `SELECT status,run_id::text,tool_id,tool_version,arguments_digest,expires_at
			FROM approvals WHERE id=$1 FOR UPDATE`, *request.ApprovalID).Scan(
			&status, &runID, &toolID, &toolVersion, &digest, &expires)
		if errors.Is(e, pgx.ErrNoRows) {
			return ToolExecution{}, ErrNotFound
		}
		if e != nil {
			return ToolExecution{}, e
		}
		if status != "approved" || !expires.After(now) || runID != request.RunID ||
			toolID != request.ToolID || toolVersion != request.ToolVersion ||
			digest != request.ArgumentsDigest {
			return ToolExecution{}, ErrConflict
		}
		if _, e = tx.Exec(ctx, `UPDATE approvals SET status='consumed',consumed_at=$2 WHERE id=$1`,
			*request.ApprovalID, now); e != nil {
			return ToolExecution{}, e
		}
	}
	id := newID()
	row := tx.QueryRow(ctx, `INSERT INTO tool_executions(id,run_id,tool_id,tool_version,arguments_digest,
		approval_id,risk_level,idempotency_key,status,attempt,max_attempts,created_at,updated_at)
		VALUES($1,$2,$3,$4,$5,$6,$7,$8,'reserved',1,$9,$10,$10)
		ON CONFLICT (run_id,idempotency_key) DO NOTHING
		RETURNING `+toolExecutionReturningColumns,
		id, request.RunID, request.ToolID, request.ToolVersion, request.ArgumentsDigest,
		request.ApprovalID, request.RiskLevel, request.IdempotencyKey, request.MaxAttempts, now)
	execution, e = scanToolExecution(row)
	created := e == nil
	if errors.Is(e, ErrNotFound) {
		execution, e = scanToolExecution(tx.QueryRow(ctx, `SELECT `+toolExecutionColumns+`
			FROM tool_executions e WHERE e.run_id=$1 AND e.idempotency_key=$2 FOR UPDATE`,
			request.RunID, request.IdempotencyKey))
		if e == nil {
			execution, e = s.existingExecution(ctx, tx, execution, request)
		}
	}
	if e != nil {
		return ToolExecution{}, e
	}
	if created {
		if e = toolExecutionAudit(ctx, tx, execution, "tool_execution.reserved", "reserved"); e != nil {
			return ToolExecution{}, e
		}
	}
	return execution, tx.Commit(ctx)
}

func (s *PostgresStore) existingExecution(ctx context.Context, tx pgx.Tx, execution ToolExecution,
	request ToolExecutionRequest) (ToolExecution, error) {
	if execution.ToolID != request.ToolID || execution.ToolVersion != request.ToolVersion ||
		execution.ArgumentsDigest != request.ArgumentsDigest || execution.RiskLevel != request.RiskLevel {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	if (execution.Status == "reserved" || execution.Status == "running") &&
		execution.UpdatedAt.Before(now.Add(-60*time.Second)) {
		code := "execution_lease_expired"
		execution.Status, execution.ErrorCode = "unknown", &code
		execution.FinishedAt, execution.UpdatedAt = &now, now
		_, e := tx.Exec(ctx, `UPDATE tool_executions SET status='unknown',error_code=$2,
			finished_at=$3,updated_at=$3 WHERE id=$1`, execution.ID, code, now)
		if e != nil {
			return ToolExecution{}, e
		}
		if e = toolExecutionAudit(ctx, tx, execution, "tool_execution.unknown", "unknown"); e != nil {
			return ToolExecution{}, e
		}
		return execution, nil
	}
	if execution.Status == "failed" && execution.RiskLevel == "read_only" &&
		execution.Attempt < execution.MaxAttempts {
		execution.Attempt++
		execution.Status, execution.ErrorCode = "reserved", nil
		execution.FinishedAt, execution.UpdatedAt = nil, now
		_, e := tx.Exec(ctx, `UPDATE tool_executions SET status='reserved',attempt=$2,error_code=NULL,
			finished_at=NULL,updated_at=$3 WHERE id=$1`, execution.ID, execution.Attempt, now)
		if e != nil {
			return ToolExecution{}, e
		}
		if e = toolExecutionAudit(ctx, tx, execution, "tool_execution.retried", "reserved"); e != nil {
			return ToolExecution{}, e
		}
		return execution, nil
	}
	if execution.Status == "reserved" || execution.Status == "running" {
		return ToolExecution{}, ErrConflict
	}
	return execution, nil
}

func (s *PostgresStore) StartToolExecution(ctx context.Context, id string) (ToolExecution, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return ToolExecution{}, e
	}
	defer tx.Rollback(ctx)
	execution, e := scanToolExecution(tx.QueryRow(ctx, `SELECT `+toolExecutionColumns+`
		FROM tool_executions e WHERE e.id=$1 FOR UPDATE`, id))
	if e != nil {
		return ToolExecution{}, e
	}
	if execution.Status == "running" {
		return execution, tx.Commit(ctx)
	}
	if execution.Status != "reserved" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.StartedAt, execution.UpdatedAt = "running", &now, now
	if _, e = tx.Exec(ctx, `UPDATE tool_executions SET status='running',started_at=$2,updated_at=$2
		WHERE id=$1`, id, now); e != nil {
		return ToolExecution{}, e
	}
	if e = toolExecutionAudit(ctx, tx, execution, "tool_execution.started", "running"); e != nil {
		return ToolExecution{}, e
	}
	return execution, tx.Commit(ctx)
}

func (s *PostgresStore) CompleteToolExecution(ctx context.Context, id string, result json.RawMessage) (ToolExecution, error) {
	if e := validateExecutionResult(result); e != nil {
		return ToolExecution{}, e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return ToolExecution{}, e
	}
	defer tx.Rollback(ctx)
	execution, e := scanToolExecution(tx.QueryRow(ctx, `SELECT `+toolExecutionColumns+`
		FROM tool_executions e WHERE e.id=$1 FOR UPDATE`, id))
	if e != nil {
		return ToolExecution{}, e
	}
	if execution.Status == "completed" {
		if string(execution.Result) == string(result) {
			return execution, tx.Commit(ctx)
		}
		return ToolExecution{}, ErrConflict
	}
	if execution.Status != "running" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.Result, execution.ErrorCode = "completed", result, nil
	execution.FinishedAt, execution.UpdatedAt = &now, now
	if _, e = tx.Exec(ctx, `UPDATE tool_executions SET status='completed',result=$2,error_code=NULL,
		finished_at=$3,updated_at=$3 WHERE id=$1`, id, result, now); e != nil {
		return ToolExecution{}, e
	}
	if e = toolExecutionAudit(ctx, tx, execution, "tool_execution.completed", "completed"); e != nil {
		return ToolExecution{}, e
	}
	return execution, tx.Commit(ctx)
}

func (s *PostgresStore) FailToolExecution(ctx context.Context, id, code string) (ToolExecution, error) {
	if e := validateExecutionCode(code); e != nil {
		return ToolExecution{}, e
	}
	return s.finishToolExecution(ctx, id, "failed", code)
}

func (s *PostgresStore) UnknownToolExecution(ctx context.Context, id, code string) (ToolExecution, error) {
	if e := validateExecutionCode(code); e != nil {
		return ToolExecution{}, e
	}
	return s.finishToolExecution(ctx, id, "unknown", code)
}

func (s *PostgresStore) finishToolExecution(ctx context.Context, id, status, code string) (ToolExecution, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return ToolExecution{}, e
	}
	defer tx.Rollback(ctx)
	execution, e := scanToolExecution(tx.QueryRow(ctx, `SELECT `+toolExecutionColumns+`
		FROM tool_executions e WHERE e.id=$1 FOR UPDATE`, id))
	if e != nil {
		return ToolExecution{}, e
	}
	if execution.Status == status {
		if execution.ErrorCode != nil && *execution.ErrorCode == code {
			return execution, tx.Commit(ctx)
		}
		return ToolExecution{}, ErrConflict
	}
	if execution.Status != "running" && execution.Status != "reserved" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.ErrorCode = status, &code
	execution.FinishedAt, execution.UpdatedAt = &now, now
	if _, e = tx.Exec(ctx, `UPDATE tool_executions SET status=$2,error_code=$3,finished_at=$4,updated_at=$4
		WHERE id=$1`, id, status, code, now); e != nil {
		return ToolExecution{}, e
	}
	if e = toolExecutionAudit(ctx, tx, execution, "tool_execution."+status, status); e != nil {
		return ToolExecution{}, e
	}
	return execution, tx.Commit(ctx)
}

func (s *PostgresStore) ToolExecution(ctx context.Context, id string) (ToolExecution, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return ToolExecution{}, e
	}
	defer tx.Rollback(ctx)
	tag, e := tx.Exec(ctx, `UPDATE tool_executions SET status='unknown',error_code='execution_lease_expired',
		finished_at=now(),updated_at=now()
		WHERE id=$1 AND status IN ('reserved','running') AND updated_at<now()-interval '60 seconds'`, id)
	if e != nil {
		return ToolExecution{}, e
	}
	execution, e := scanToolExecution(tx.QueryRow(ctx, `SELECT `+toolExecutionColumns+`
		FROM tool_executions e WHERE e.id=$1`, id))
	if e != nil {
		return ToolExecution{}, e
	}
	if tag.RowsAffected() > 0 {
		if e = toolExecutionAudit(ctx, tx, execution, "tool_execution.unknown", "unknown"); e != nil {
			return ToolExecution{}, e
		}
	}
	if e = tx.Commit(ctx); e != nil {
		return ToolExecution{}, e
	}
	return execution, nil
}

func (s *PostgresStore) ReconcileToolExecution(ctx context.Context, id, status string,
	result json.RawMessage, code string) (ToolExecution, error) {
	if status != "completed" && status != "failed" {
		return ToolExecution{}, ErrInvalidConfig
	}
	if status == "completed" {
		if e := validateExecutionResult(result); e != nil {
			return ToolExecution{}, e
		}
	} else if e := validateExecutionCode(code); e != nil {
		return ToolExecution{}, e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return ToolExecution{}, e
	}
	defer tx.Rollback(ctx)
	execution, e := scanToolExecution(tx.QueryRow(ctx, `SELECT `+toolExecutionColumns+`
		FROM tool_executions e WHERE e.id=$1 FOR UPDATE`, id))
	if e != nil {
		return ToolExecution{}, e
	}
	if execution.Status != "unknown" {
		return ToolExecution{}, ErrConflict
	}
	now := nowUTC()
	execution.Status, execution.FinishedAt, execution.UpdatedAt = status, &now, now
	if status == "completed" {
		execution.Result, execution.ErrorCode = result, nil
		_, e = tx.Exec(ctx, `UPDATE tool_executions SET status='completed',result=$2,error_code=NULL,
			finished_at=$3,updated_at=$3 WHERE id=$1`, id, result, now)
	} else {
		execution.Result, execution.ErrorCode = nil, &code
		_, e = tx.Exec(ctx, `UPDATE tool_executions SET status='failed',result=NULL,error_code=$2,
			finished_at=$3,updated_at=$3 WHERE id=$1`, id, code, now)
	}
	if e != nil {
		return ToolExecution{}, e
	}
	if e = toolExecutionAudit(ctx, tx, execution, "tool_execution.reconciled", status); e != nil {
		return ToolExecution{}, e
	}
	return execution, tx.Commit(ctx)
}
