package main

import "context"

func (s *PostgresStore) DeleteConversation(ctx context.Context, id string) error {
	principal := currentPrincipal(ctx)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	var exists bool
	err = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM conversations
		WHERE id=$1 AND (owner_id=$2 OR $3) FOR UPDATE)`,
		id, principal.ID, principal.isAdmin()).Scan(&exists)
	if err != nil {
		return err
	}
	if !exists {
		return ErrNotFound
	}
	var active bool
	if err = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM agent_runs
		WHERE conversation_id=$1 AND status='running')`, id).Scan(&active); err != nil {
		return err
	}
	if active {
		return ErrConflict
	}
	if _, err = tx.Exec(ctx, `INSERT INTO deletion_tombstones(id,resource_type,resource_id,deleted_by,reason)
		VALUES($1,'conversation',$2,$3,'manual') ON CONFLICT (resource_type,resource_id) DO NOTHING`,
		newID(), id, principal.ID); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, `DELETE FROM conversations WHERE id=$1`, id); err != nil {
		return err
	}
	if err = recordAudit(ctx, tx, AuditRecord{
		ActorID: principal.ID, Action: "conversation.deleted", TargetID: id,
		TargetType: "conversation", Outcome: "success",
		Details: map[string]any{"reason": "manual"},
	}); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *PostgresStore) RunRetention(ctx context.Context, policy RetentionPolicy) (RetentionResult, error) {
	result := RetentionResult{}
	if policy.ConversationDays <= 0 && policy.AuditDays <= 0 &&
		policy.ApprovalDays <= 0 && policy.CleanupDays <= 0 {
		return result, nil
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return result, err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, `SELECT pg_advisory_xact_lock(714203)`); err != nil {
		return result, err
	}
	if policy.ApprovalDays > 0 {
		tag, execErr := tx.Exec(ctx, `DELETE FROM approvals
			WHERE (status <> 'pending' OR expires_at < now())
			  AND COALESCE(decided_at, expires_at, created_at) < now() - make_interval(days => $1)`,
			policy.ApprovalDays)
		if execErr != nil {
			return result, execErr
		}
		result.Approvals = int(tag.RowsAffected())
	}
	if policy.AuditDays > 0 {
		tag, execErr := tx.Exec(ctx, `DELETE FROM audit_events
			WHERE created_at < now() - make_interval(days => $1)`, policy.AuditDays)
		if execErr != nil {
			return result, execErr
		}
		result.AuditEvents = int(tag.RowsAffected())
	}
	if policy.ConversationDays > 0 {
		rows, queryErr := tx.Query(ctx, `SELECT id FROM conversations
			WHERE created_at < now() - make_interval(days => $1)
			  AND NOT EXISTS (SELECT 1 FROM agent_runs r
			                  WHERE r.conversation_id=conversations.id AND r.status='running')
			FOR UPDATE`, policy.ConversationDays)
		if queryErr != nil {
			return result, queryErr
		}
		ids := []string{}
		for rows.Next() {
			var id string
			if queryErr = rows.Scan(&id); queryErr != nil {
				rows.Close()
				return result, queryErr
			}
			ids = append(ids, id)
		}
		if queryErr = rows.Err(); queryErr != nil {
			rows.Close()
			return result, queryErr
		}
		rows.Close()
		for _, id := range ids {
			if _, err = tx.Exec(ctx, `INSERT INTO deletion_tombstones(id,resource_type,resource_id,deleted_by,reason)
				VALUES($1,'conversation',$2,'system-retention','retention') ON CONFLICT (resource_type,resource_id) DO NOTHING`,
				newID(), id); err != nil {
				return result, err
			}
		}
		if len(ids) > 0 {
			tag, execErr := tx.Exec(ctx, `DELETE FROM conversations WHERE id=ANY($1::uuid[])`, ids)
			if execErr != nil {
				return result, execErr
			}
			result.Conversations = int(tag.RowsAffected())
		}
	}
	if policy.CleanupDays > 0 {
		tag, execErr := tx.Exec(ctx, `DELETE FROM vector_cleanup_jobs
			WHERE state IN ('completed','failed') AND updated_at < now() - make_interval(days => $1)`,
			policy.CleanupDays)
		if execErr != nil {
			return result, execErr
		}
		result.CleanupJobs = int(tag.RowsAffected())
	}
	if err = recordAudit(ctx, tx, AuditRecord{
		ActorID: "system-retention", Action: "retention.applied", TargetID: newID(),
		TargetType: "retention", Outcome: "success",
		Details: map[string]any{
			"conversations": result.Conversations, "approvals": result.Approvals,
			"audit_events": result.AuditEvents, "cleanup_jobs": result.CleanupJobs,
		},
	}); err != nil {
		return result, err
	}
	if err = tx.Commit(ctx); err != nil {
		return result, err
	}
	return result, nil
}
