package main

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5"
)

const approvalColumns = `a.id::text,a.run_id::text,a.tool_id,a.tool_version,a.arguments_digest,
	a.policy_digest,a.policy_snapshot,a.requested_by,a.status,a.created_at,a.expires_at,
	a.decided_at,a.decided_by,a.consumed_at`

func scanApproval(row interface{ Scan(...any) error }) (Approval, error) {
	var approval Approval
	var policy []byte
	e := row.Scan(&approval.ID, &approval.RunID, &approval.ToolID, &approval.ToolVersion,
		&approval.ArgumentsDigest, &approval.PolicyDigest, &policy, &approval.RequestedBy,
		&approval.Status, &approval.CreatedAt, &approval.ExpiresAt, &approval.DecidedAt,
		&approval.DecidedBy, &approval.ConsumedAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return Approval{}, ErrNotFound
	}
	approval.PolicySnapshot = append(json.RawMessage(nil), policy...)
	return approval, e
}

func (s *PostgresStore) expireApprovals(ctx context.Context, id string) error {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	query := `UPDATE approvals SET status='expired'
		WHERE status IN ('pending','approved') AND expires_at<=now()`
	args := []any{}
	if id != "" {
		query += ` AND id=$1`
		args = append(args, id)
	}
	rows, e := tx.Query(ctx, query+` RETURNING id::text,run_id::text,arguments_digest,tool_id,tool_version`, args...)
	if e != nil {
		return e
	}
	type expiredApproval struct{ id, runID, digest, toolID, toolVersion string }
	expired := []expiredApproval{}
	for rows.Next() {
		var item expiredApproval
		if e = rows.Scan(&item.id, &item.runID, &item.digest, &item.toolID, &item.toolVersion); e != nil {
			rows.Close()
			return e
		}
		expired = append(expired, item)
	}
	rows.Close()
	if e = rows.Err(); e != nil {
		return e
	}
	for _, item := range expired {
		actor, correlation, e := runAuditIdentity(ctx, tx, item.runID)
		if e != nil {
			return e
		}
		if e = recordAudit(ctx, tx, AuditRecord{
			ActorID: actor, Action: "approval.expired", TargetID: item.id,
			TargetType: "approval", RunID: item.runID, CorrelationID: correlation,
			Digest: item.digest, Outcome: "expired",
			Details: map[string]any{"tool_id": item.toolID, "tool_version": item.toolVersion},
		}); e != nil {
			return e
		}
	}
	return tx.Commit(ctx)
}

func (s *PostgresStore) Approvals(ctx context.Context) ([]Approval, error) {
	if e := s.expireApprovals(ctx, ""); e != nil {
		return nil, e
	}
	rows, e := s.pool.Query(ctx, `SELECT `+approvalColumns+`
		FROM approvals a ORDER BY a.created_at DESC,a.id LIMIT 200`)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []Approval{}
	for rows.Next() {
		approval, e := scanApproval(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, approval)
	}
	return out, rows.Err()
}

func (s *PostgresStore) Approval(ctx context.Context, id string) (Approval, error) {
	if e := s.expireApprovals(ctx, id); e != nil {
		return Approval{}, e
	}
	return scanApproval(s.pool.QueryRow(ctx, `SELECT `+approvalColumns+`
		FROM approvals a WHERE a.id=$1`, id))
}

func (s *PostgresStore) DecideApproval(ctx context.Context, id, decision string) (Approval, error) {
	if decision != "approve" && decision != "reject" {
		return Approval{}, ErrInvalidConfig
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return Approval{}, e
	}
	defer tx.Rollback(ctx)
	approval, e := scanApproval(tx.QueryRow(ctx, `SELECT `+approvalColumns+`
		FROM approvals a WHERE a.id=$1 FOR UPDATE`, id))
	if e != nil {
		return Approval{}, e
	}
	now := nowUTC()
	if approval.Status == "pending" && !approval.ExpiresAt.After(now) {
		if _, e = tx.Exec(ctx, `UPDATE approvals SET status='expired' WHERE id=$1`, id); e != nil {
			return Approval{}, e
		}
		_, correlation, e := runAuditIdentity(ctx, tx, approval.RunID)
		if e != nil {
			return Approval{}, e
		}
		if e = recordAudit(ctx, tx, AuditRecord{
			ActorID: currentPrincipal(ctx).ID, Action: "approval.expired", TargetID: id,
			TargetType: "approval", RunID: approval.RunID, CorrelationID: correlation,
			Digest: approval.ArgumentsDigest, Outcome: "expired",
			Details: map[string]any{"tool_id": approval.ToolID, "tool_version": approval.ToolVersion},
		}); e != nil {
			return Approval{}, e
		}
		if e = tx.Commit(ctx); e != nil {
			return Approval{}, e
		}
		return Approval{}, ErrConflict
	}
	if approval.Status != "pending" {
		return Approval{}, ErrConflict
	}
	var runStatus, correlationID string
	e = tx.QueryRow(ctx, `SELECT status,correlation_id::text FROM agent_runs WHERE id=$1 FOR UPDATE`,
		approval.RunID).Scan(&runStatus, &correlationID)
	if errors.Is(e, pgx.ErrNoRows) {
		return Approval{}, ErrNotFound
	}
	if e != nil {
		return Approval{}, e
	}
	if runStatus != "waiting_approval" {
		if _, e = tx.Exec(ctx, `UPDATE approvals SET status='invalidated' WHERE id=$1`, id); e != nil {
			return Approval{}, e
		}
		if e = recordAudit(ctx, tx, AuditRecord{
			ActorID: currentPrincipal(ctx).ID, Action: "approval.invalidated", TargetID: id,
			TargetType: "approval", RunID: approval.RunID, CorrelationID: correlationID,
			Digest: approval.ArgumentsDigest, Outcome: "invalidated",
			Details: map[string]any{"tool_id": approval.ToolID, "tool_version": approval.ToolVersion,
				"run_status": runStatus},
		}); e != nil {
			return Approval{}, e
		}
		if e = tx.Commit(ctx); e != nil {
			return Approval{}, e
		}
		return Approval{}, ErrConflict
	}
	decidedBy := currentPrincipal(ctx).ID
	status, action := "approved", "approval.approved"
	runStatus = "running"
	if decision == "reject" {
		status, action, runStatus = "rejected", "approval.rejected", "failed"
	}
	if _, e = tx.Exec(ctx, `UPDATE approvals SET status=$2,decided_at=$3,decided_by=$4 WHERE id=$1`,
		id, status, now, decidedBy); e != nil {
		return Approval{}, e
	}
	if decision == "approve" {
		_, e = tx.Exec(ctx, `UPDATE agent_runs SET status='running',updated_at=$2 WHERE id=$1`,
			approval.RunID, now)
	} else {
		_, e = tx.Exec(ctx, `UPDATE agent_runs SET status='failed',finished_at=$2,updated_at=$2
			WHERE id=$1`, approval.RunID, now)
	}
	if e != nil {
		return Approval{}, e
	}
	if e = recordAudit(ctx, tx, AuditRecord{
		ActorID: decidedBy, Action: action, TargetID: id, TargetType: "approval",
		RunID: approval.RunID, CorrelationID: correlationID,
		Digest: approval.ArgumentsDigest, Outcome: status,
		Details: map[string]any{"decision": decision, "tool_id": approval.ToolID,
			"tool_version": approval.ToolVersion, "policy_digest": approval.PolicyDigest,
			"requested_by": approval.RequestedBy},
	}); e != nil {
		return Approval{}, e
	}
	if e = tx.Commit(ctx); e != nil {
		return Approval{}, e
	}
	approval.Status = status
	approval.DecidedAt = &now
	approval.DecidedBy = &decidedBy
	return approval, nil
}
