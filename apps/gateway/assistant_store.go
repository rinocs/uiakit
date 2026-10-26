package main

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5"
)

func (s *PostgresStore) Models(ctx context.Context) ([]ModelDefinition, error) {
	rows, e := s.pool.Query(ctx, "SELECT definition FROM model_configurations ORDER BY id")
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []ModelDefinition{}
	for rows.Next() {
		var data []byte
		if e = rows.Scan(&data); e != nil {
			return nil, e
		}
		var m ModelDefinition
		if e = json.Unmarshal(data, &m); e != nil {
			return nil, e
		}
		out = append(out, m)
	}
	return out, rows.Err()
}
func (s *PostgresStore) SyncModels(ctx context.Context, models []ModelDefinition) error {
	if len(models) != 1 {
		return ErrInvalidConfig
	}
	if e := models[0].validate(); e != nil {
		return e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	for _, m := range models {
		data, e := json.Marshal(m)
		if e != nil {
			return e
		}
		if _, e = tx.Exec(ctx, "INSERT INTO model_configurations(id,definition) VALUES($1,$2) ON CONFLICT(id) DO UPDATE SET definition=EXCLUDED.definition,updated_at=now()", m.ID, data); e != nil {
			return e
		}
	}
	if _, e = tx.Exec(ctx, "DELETE FROM model_configurations WHERE id<>$1", models[0].ID); e != nil {
		return e
	}
	return tx.Commit(ctx)
}
func (s *PostgresStore) Assistants(ctx context.Context) ([]Assistant, error) {
	actor := currentPrincipal(ctx)
	rows, e := s.pool.Query(ctx, `SELECT v.config FROM assistants a JOIN assistant_versions v ON v.assistant_id=a.id AND v.version=a.current_version WHERE a.owner_id=$1 OR $2 ORDER BY a.created_at,a.id`, actor.ID, actor.isAdmin())
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []Assistant{}
	for rows.Next() {
		var data []byte
		if e = rows.Scan(&data); e != nil {
			return nil, e
		}
		var a Assistant
		if e = json.Unmarshal(data, &a); e != nil {
			return nil, e
		}
		out = append(out, a)
	}
	return out, rows.Err()
}
func (s *PostgresStore) Assistant(ctx context.Context, id string) (Assistant, error) {
	var data []byte
	e := s.pool.QueryRow(ctx, `SELECT v.config FROM assistants a JOIN assistant_versions v ON v.assistant_id=a.id AND v.version=a.current_version WHERE a.id=$1 AND (a.owner_id=$2 OR $3)`, id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()).Scan(&data)
	if errors.Is(e, pgx.ErrNoRows) {
		return Assistant{}, ErrNotFound
	}
	var a Assistant
	if e == nil {
		e = json.Unmarshal(data, &a)
	}
	return a, e
}
func (s *PostgresStore) AssistantVersions(ctx context.Context, id string) ([]Assistant, error) {
	// Check ownership even for an assistant with no visible history.
	if _, e := s.Assistant(ctx, id); e != nil {
		return nil, e
	}
	rows, e := s.pool.Query(ctx, "SELECT config FROM assistant_versions WHERE assistant_id=$1 ORDER BY version", id)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []Assistant{}
	for rows.Next() {
		var data []byte
		if e = rows.Scan(&data); e != nil {
			return nil, e
		}
		var a Assistant
		if e = json.Unmarshal(data, &a); e != nil {
			return nil, e
		}
		out = append(out, a)
	}
	return out, rows.Err()
}
func (s *PostgresStore) CreateAssistant(ctx context.Context, a Assistant) (Assistant, error) {
	if e := a.validate(); e != nil {
		return a, e
	}
	a.ID = newID()
	a.Version = 1
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return a, e
	}
	defer tx.Rollback(ctx)
	if e = validateKnowledgeBasesTx(ctx, tx, a.KnowledgeBaseIDs); e != nil {
		return a, e
	}
	_, e = tx.Exec(ctx, "INSERT INTO assistants(id,name,model,system_prompt,owner_id) VALUES($1,$2,$3,$4,$5)", a.ID, a.Name, a.Model, a.SystemPrompt, currentPrincipal(ctx).ID)
	if e != nil {
		return a, e
	}
	data, e := json.Marshal(a)
	if e != nil {
		return a, e
	}
	_, e = tx.Exec(ctx, "INSERT INTO assistant_versions(assistant_id,version,config) VALUES($1,1,$2)", a.ID, data)
	if e == nil {
		e = recordAudit(ctx, tx, AuditRecord{
			ActorID: currentPrincipal(ctx).ID, Action: "assistant.created", TargetID: a.ID,
			TargetType: "assistant", Digest: digestJSON(a), Outcome: "success",
			Details: map[string]any{"model": a.Model, "tool_count": len(a.Tools),
				"structured_output": len(a.StructuredOutput) > 0},
		})
	}
	if e == nil {
		e = tx.Commit(ctx)
	}
	return a, e
}
func (s *PostgresStore) UpdateAssistant(ctx context.Context, id string, expected int, patch json.RawMessage) (Assistant, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return Assistant{}, e
	}
	defer tx.Rollback(ctx)
	var version int
	e = tx.QueryRow(ctx, `SELECT current_version FROM assistants WHERE id=$1 AND (owner_id=$2 OR $3) FOR UPDATE`, id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()).Scan(&version)
	if errors.Is(e, pgx.ErrNoRows) {
		return Assistant{}, ErrNotFound
	}
	if e != nil {
		return Assistant{}, e
	}
	if version != expected {
		return Assistant{}, ErrPreconditionFailed
	}
	var data []byte
	if e = tx.QueryRow(ctx, "SELECT config FROM assistant_versions WHERE assistant_id=$1 AND version=$2", id, version).Scan(&data); e != nil {
		return Assistant{}, e
	}
	var current Assistant
	if e = json.Unmarshal(data, &current); e != nil {
		return current, e
	}
	if current.Version != expected {
		return current, ErrPreconditionFailed
	}
	next, e := applyAssistantPatch(current, patch)
	if e != nil {
		return next, e
	}
	next.Version++
	if e = validateKnowledgeBasesTx(ctx, tx, next.KnowledgeBaseIDs); e != nil {
		return next, e
	}
	var model ModelDefinition
	var modelData []byte
	e = tx.QueryRow(ctx, "SELECT definition FROM model_configurations WHERE id=$1", next.Model).Scan(&modelData)
	if errors.Is(e, pgx.ErrNoRows) {
		return next, ErrInvalidConfig
	}
	if e != nil {
		return next, e
	}
	if e = json.Unmarshal(modelData, &model); e != nil {
		return next, e
	}
	if !model.supports("chat") || !model.supports("streaming") {
		return next, ErrInvalidConfig
	}
	data, e = json.Marshal(next)
	if e != nil {
		return next, e
	}
	if _, e = tx.Exec(ctx, "INSERT INTO assistant_versions(assistant_id,version,config) VALUES($1,$2,$3)", id, next.Version, data); e != nil {
		return next, e
	}
	if _, e = tx.Exec(ctx, "UPDATE assistants SET current_version=$2,name=$3,model=$4,system_prompt=$5 WHERE id=$1", id, next.Version, next.Name, next.Model, next.SystemPrompt); e != nil {
		return next, e
	}
	if e = recordAudit(ctx, tx, AuditRecord{
		ActorID: currentPrincipal(ctx).ID, Action: "assistant.updated", TargetID: id,
		TargetType: "assistant", Digest: digestJSON(next), Outcome: "success",
		Details: map[string]any{"version": next.Version, "model": next.Model,
			"tool_count": len(next.Tools), "structured_output": len(next.StructuredOutput) > 0},
	}); e != nil {
		return next, e
	}
	return next, tx.Commit(ctx)
}
