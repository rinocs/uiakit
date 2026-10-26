package main

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
)

const agentRunColumns = `r.id::text,r.conversation_id::text,r.status,r.assistant_id::text,
	r.assistant_version,coalesce(r.assistant_config->>'model',''),r.created_at,r.finished_at,r.updated_at,r.cancel_requested_at`

func scanAgentRun(row interface{ Scan(...any) error }) (AgentRun, error) {
	var run AgentRun
	e := row.Scan(&run.ID, &run.ConversationID, &run.Status, &run.AssistantID,
		&run.AssistantVersion, &run.Model, &run.CreatedAt, &run.FinishedAt, &run.UpdatedAt,
		&run.CancelRequestedAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return AgentRun{}, ErrNotFound
	}
	return run, e
}

func (s *PostgresStore) AgentRuns(ctx context.Context) ([]AgentRun, error) {
	rows, e := s.pool.Query(ctx, `SELECT `+agentRunColumns+`
		FROM agent_runs r JOIN conversations c ON c.id=r.conversation_id
		WHERE c.owner_id=$1 OR $2 ORDER BY r.created_at DESC,r.id LIMIT 200`,
		currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin())
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []AgentRun{}
	for rows.Next() {
		run, e := scanAgentRun(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, run)
	}
	return out, rows.Err()
}

func (s *PostgresStore) AgentRun(ctx context.Context, id string) (AgentRun, error) {
	return scanAgentRun(s.pool.QueryRow(ctx, `SELECT `+agentRunColumns+`
		FROM agent_runs r JOIN conversations c ON c.id=r.conversation_id
		WHERE r.id=$1 AND (c.owner_id=$2 OR $3)`,
		id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
}

func (s *PostgresStore) CancelAgentRun(ctx context.Context, id string) (AgentRun, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return AgentRun{}, e
	}
	defer tx.Rollback(ctx)
	run, e := scanAgentRun(tx.QueryRow(ctx, `SELECT `+agentRunColumns+`
		FROM agent_runs r JOIN conversations c ON c.id=r.conversation_id
		WHERE r.id=$1 AND (c.owner_id=$2 OR $3) FOR UPDATE OF r`,
		id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
	if e != nil {
		return AgentRun{}, e
	}
	if run.Status != "queued" && run.Status != "running" && run.Status != "waiting_approval" {
		return AgentRun{}, ErrConflict
	}
	if _, e = tx.Exec(ctx, `UPDATE agent_runs SET status='cancelled',
		cancel_requested_at=now(),updated_at=now() WHERE id=$1`, id); e != nil {
		return AgentRun{}, e
	}
	var correlationID string
	if e = tx.QueryRow(ctx, `SELECT correlation_id::text FROM agent_runs WHERE id=$1`, id).Scan(&correlationID); e != nil {
		return AgentRun{}, e
	}
	if e = recordAudit(ctx, tx, AuditRecord{
		ActorID: currentPrincipal(ctx).ID, Action: "agent_run.cancelled", TargetID: id,
		TargetType: "agent_run", RunID: id, CorrelationID: correlationID,
		Outcome: "cancelled", Details: map[string]any{"previous_status": run.Status},
	}); e != nil {
		return AgentRun{}, e
	}
	if e = tx.Commit(ctx); e != nil {
		return AgentRun{}, e
	}
	run.Status = "cancelled"
	now := nowUTC()
	run.UpdatedAt = now
	run.CancelRequestedAt = &now
	return run, nil
}
