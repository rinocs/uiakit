package main

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrations embed.FS

type PostgresStore struct{ pool *pgxpool.Pool }

func OpenStore(ctx context.Context, url string) (*PostgresStore, error) {
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		return nil, err
	}
	s := &PostgresStore{pool: pool}
	tx, err := pool.Begin(ctx)
	if err != nil {
		pool.Close()
		return nil, err
	}
	defer tx.Rollback(ctx)
	// Serialize migration and crash recovery. MVP is a single gateway replica.
	if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(714201)"); err == nil {
		err = applyMigrations(ctx, tx)
	}

	if err == nil {
		// Interrupted runs cannot be resumed blindly: mark failed with a replayable event.
		var rows pgx.Rows
		rows, err = tx.Query(ctx, "SELECT id::text,correlation_id::text FROM agent_runs WHERE status='running'")
		if err == nil {
			type interruptedRun struct{ id, correlationID string }
			runs := []interruptedRun{}
			for rows.Next() {
				var run interruptedRun
				if e := rows.Scan(&run.id, &run.correlationID); e != nil {
					err = e
					break
				}
				runs = append(runs, run)
			}
			if err == nil {
				err = rows.Err()
			}
			rows.Close()
			for _, run := range runs {
				if err != nil {
					break
				}
				events, _ := json.Marshal([]Event{{ID: newID(), Type: "agent.failed", Version: 1, Timestamp: time.Now().UTC(), RunID: run.id, CorrelationID: run.correlationID, Payload: json.RawMessage(`{"code":"gateway_restarted"}`)}})
				_, err = tx.Exec(ctx, "UPDATE agent_runs SET status='failed',events=$2,finished_at=now(),updated_at=now() WHERE id=$1", run.id, events)
			}
		}
	}
	if err == nil {
		err = tx.Commit(ctx)
	}
	if err != nil {
		_ = tx.Rollback(ctx)
		pool.Close()
		return nil, err
	}
	return s, nil
}
func (s *PostgresStore) Health(ctx context.Context) error { return s.pool.Ping(ctx) }
func (s *PostgresStore) CreateConversation(ctx context.Context, assistant string) (string, error) {
	id := newID()
	tag, e := s.pool.Exec(ctx, "INSERT INTO conversations(id,assistant_id,owner_id) SELECT $1,id,$3 FROM assistants WHERE id=$2 AND (owner_id=$3 OR $4)", id, assistant, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin())
	if e == nil && tag.RowsAffected() == 0 {
		e = ErrNotFound
	}
	return id, e
}
func (s *PostgresStore) Messages(ctx context.Context, id string) ([]Message, error) {
	principal := currentPrincipal(ctx)
	var assistantID string
	var owned bool
	err := s.pool.QueryRow(ctx, "SELECT assistant_id::text,(owner_id=$2 OR $3) FROM conversations WHERE id=$1", id, principal.ID, principal.isAdmin()).Scan(&assistantID, &owned)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	if !owned {
		widget := principal.Widget
		if widget == nil || widget.ConversationID != id || widget.AssistantID != assistantID {
			return nil, ErrNotFound
		}
	}
	rows, e := s.pool.Query(ctx, `SELECT m.role,m.content FROM messages m JOIN agent_runs r ON r.id=m.run_id WHERE m.conversation_id=$1 AND r.status='completed' ORDER BY m.sequence`, id)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []Message{}
	for rows.Next() {
		var m Message
		if e := rows.Scan(&m.Role, &m.Content); e != nil {
			return nil, e
		}
		out = append(out, m)
	}
	return out, rows.Err()
}
func (s *PostgresStore) Start(ctx context.Context, id, key, content string) (Run, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return Run{}, e
	}
	defer tx.Rollback(ctx)
	r := Run{ConversationID: id, Content: content, Status: "running", RetrievalTargets: []RetrievalTarget{}}
	var configData []byte
	var assistantID string
	var version int
	principal := currentPrincipal(ctx)
	query := `SELECT a.id::text,a.current_version,c.owner_id FROM conversations c JOIN assistants a ON a.id=c.assistant_id WHERE c.id=$1 AND (c.owner_id=$2 OR $3) FOR UPDATE OF c FOR SHARE OF a`
	args := []any{id, principal.ID, principal.isAdmin()}
	if widget := principal.Widget; widget != nil {
		query = `SELECT a.id::text,a.current_version,c.owner_id FROM conversations c JOIN assistants a ON a.id=c.assistant_id WHERE c.id=$1 AND (c.owner_id=$2 OR $3 OR (c.id::text=$4 AND c.assistant_id::text=$5)) FOR UPDATE OF c FOR SHARE OF a`
		args = append(args, widget.ConversationID, widget.AssistantID)
	}
	e = tx.QueryRow(ctx, query, args...).Scan(&assistantID, &version, &r.OwnerID)
	if errors.Is(e, pgx.ErrNoRows) {
		return r, ErrNotFound
	}
	if e != nil {
		return r, e
	}
	var existingContent string
	var events []byte
	var modelData []byte
	e = tx.QueryRow(ctx, "SELECT id::text,content,status,events,assistant_config,model_snapshot,correlation_id::text FROM agent_runs WHERE conversation_id=$1 AND idempotency_key=$2", id, key).Scan(&r.ID, &existingContent, &r.Status, &events, &configData, &modelData, &r.CorrelationID)
	if e == nil {
		if existingContent != content || r.Status == "running" {
			return r, ErrConflict
		}
		if e = json.Unmarshal(events, &r.Events); e != nil {
			return r, e
		}
		if e = json.Unmarshal(configData, &r.AssistantConfig); e != nil {
			return r, e
		}
		r.Model = r.AssistantConfig.Model
		r.SystemPrompt = r.AssistantConfig.SystemPrompt
		if len(modelData) > 0 {
			if e = json.Unmarshal(modelData, &r.ModelSnapshot); e != nil {
				return r, e
			}
		}
		return r, tx.Commit(ctx)
	}
	if !errors.Is(e, pgx.ErrNoRows) {
		return r, e
	}
	if e = tx.QueryRow(ctx, "SELECT config FROM assistant_versions WHERE assistant_id=$1 AND version=$2", assistantID, version).Scan(&configData); e != nil {
		return r, e
	}
	if e = json.Unmarshal(configData, &r.AssistantConfig); e != nil {
		return r, e
	}
	r.Model = r.AssistantConfig.Model
	r.SystemPrompt = r.AssistantConfig.SystemPrompt
	if len(r.AssistantConfig.KnowledgeBaseIDs) > 0 {
		rows, e := tx.Query(ctx, `SELECT k.id::text,kv.collection_name,kv.embedding_provider,
			kv.embedding_model,kv.embedding_version,kv.embedding_dimension
			FROM knowledge_bases k JOIN knowledge_base_versions kv
			  ON kv.knowledge_base_id=k.id AND kv.version=k.active_version
			WHERE k.id=ANY($1::uuid[]) AND (k.owner_id=$2 OR $3)
			  AND kv.collection_name IS NOT NULL AND kv.embedding_provider IS NOT NULL`,
			r.AssistantConfig.KnowledgeBaseIDs, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin())
		if e != nil {
			return r, e
		}
		for rows.Next() {
			var target RetrievalTarget
			if e = rows.Scan(&target.KnowledgeBaseID, &target.Collection, &target.EmbeddingProvider,
				&target.EmbeddingModel, &target.EmbeddingVersion, &target.EmbeddingDimension); e != nil {
				rows.Close()
				return r, e
			}
			target.IndexVersion = KnowledgeBaseEmbedding{Provider: target.EmbeddingProvider,
				Model: target.EmbeddingModel, Version: target.EmbeddingVersion,
				Dimension: target.EmbeddingDimension}.indexVersion()
			r.RetrievalTargets = append(r.RetrievalTargets, target)
		}
		if e = rows.Err(); e != nil {
			rows.Close()
			return r, e
		}
		rows.Close()
	}
	e = tx.QueryRow(ctx, "SELECT definition FROM model_configurations WHERE id=$1", r.Model).Scan(&modelData)
	if errors.Is(e, pgx.ErrNoRows) {
		return r, ErrInvalidConfig
	}
	if e != nil {
		return r, e
	}
	if e = json.Unmarshal(modelData, &r.ModelSnapshot); e != nil {
		return r, e
	}
	if r.ModelSnapshot == nil || !r.ModelSnapshot.supports("chat") || !r.ModelSnapshot.supports("streaming") {
		return r, ErrInvalidConfig
	}
	var active bool
	if e = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM agent_runs WHERE conversation_id=$1 AND status='running')", id).Scan(&active); e != nil {
		return r, e
	}
	if active {
		return r, ErrConflict
	}
	rows, e := tx.Query(ctx, `SELECT m.role,m.content FROM messages m JOIN agent_runs r ON r.id=m.run_id WHERE m.conversation_id=$1 AND r.status='completed' AND $2 ORDER BY m.sequence`, id, r.AssistantConfig.Memory.Conversation)
	if e != nil {
		return r, e
	}
	total := len(content) + len(r.SystemPrompt)
	for rows.Next() {
		var m Message
		if e = rows.Scan(&m.Role, &m.Content); e != nil {
			break
		}
		r.Messages = append(r.Messages, m)
		total += len(m.Content)
	}
	if e == nil {
		e = rows.Err()
	}
	rows.Close()
	if e != nil {
		return r, e
	}
	// Fail explicitly instead of silently dropping conversation turns.
	if len(r.Messages) >= 100 || total > r.AssistantConfig.Limits.MaxInputChars {
		return r, ErrConflict
	}
	r.ID = newID()
	r.CorrelationID = newID()
	r.Messages = append(r.Messages, Message{Role: "user", Content: content})
	if _, e = tx.Exec(ctx, "INSERT INTO agent_runs(id,conversation_id,idempotency_key,content,status,assistant_id,assistant_version,assistant_config,model_snapshot,correlation_id) VALUES($1,$2,$3,$4,'running',$5,$6,$7,$8,$9)", r.ID, id, key, content, r.AssistantConfig.ID, r.AssistantConfig.Version, configData, modelData, r.CorrelationID); e != nil {
		return r, e
	}
	if _, e = tx.Exec(ctx, "INSERT INTO messages(conversation_id,run_id,role,content) VALUES($1,$2,'user',$3)", id, r.ID, content); e != nil {
		return r, e
	}
	if e = recordAudit(ctx, tx, AuditRecord{
		ActorID: currentPrincipal(ctx).ID, Action: "agent_run.started",
		TargetID: r.ID, TargetType: "agent_run", RunID: r.ID,
		CorrelationID: r.CorrelationID, Digest: digestString(content), Outcome: "success",
		Details: map[string]any{"assistant_id": r.AssistantConfig.ID,
			"assistant_version": r.AssistantConfig.Version, "model": r.Model,
			"actor_role": currentPrincipal(ctx).Role, "scopes": currentPrincipal(ctx).Scopes},
	}); e != nil {
		return r, e
	}
	return r, tx.Commit(ctx)
}
func (s *PostgresStore) Finish(ctx context.Context, r Run, events []Event, status string) error {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if len(events) == 0 || events[len(events)-1].Type != "response.completed" &&
		events[len(events)-1].Type != "agent.failed" && events[len(events)-1].Type != "agent.cancelled" {
		status = "failed"
		events = append(events, Event{ID: newID(), Type: "agent.failed", Version: 1, Timestamp: time.Now().UTC(), RunID: r.ID, CorrelationID: r.CorrelationID, Payload: json.RawMessage(`{"code":"execution_interrupted"}`)})
	}
	data, e := json.Marshal(events)
	if e != nil {
		return e
	}
	// Cancellation is durable before the stream closes; the final event can still
	// be persisted without changing the terminal state.
	where := "status='running'"
	if status == "cancelled" {
		where = "status IN ('running','cancelled')"
	}
	tag, e := tx.Exec(ctx, "UPDATE agent_runs SET status=$2,events=$3,finished_at=now(),updated_at=now() WHERE id=$1 AND "+where+" AND conversation_id IN (SELECT id FROM conversations WHERE owner_id=$4)", r.ID, status, data, r.OwnerID)
	if e != nil {
		return e
	}
	if tag.RowsAffected() == 0 {
		return ErrConflict
	}
	if status == "completed" {
		var payload struct {
			Text string `json:"text"`
		}
		if e = json.Unmarshal(events[len(events)-1].Payload, &payload); e != nil {
			return e
		}
		if payload.Text == "" {
			return errors.New("empty_completed_output")
		}
		if _, e = tx.Exec(ctx, "INSERT INTO messages(conversation_id,run_id,role,content) VALUES($1,$2,'assistant',$3)", r.ConversationID, r.ID, payload.Text); e != nil {
			return e
		}
	}
	return tx.Commit(ctx)
}

func applyMigrations(ctx context.Context, tx pgx.Tx) error {
	files, err := migrations.ReadDir("migrations")
	if err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, "CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now())"); err != nil {
		return err
	}
	var version, count int
	if err = tx.QueryRow(ctx, "SELECT COALESCE(max(version),0),count(*) FROM schema_migrations").Scan(&version, &count); err != nil {
		return err
	}
	if version != count || version > len(files) {
		return errors.New("unsupported database schema version")
	}
	for i, file := range files {
		if file.IsDir() || len(file.Name()) < 4 || file.Name()[:3] != fmt.Sprintf("%03d", i+1) {
			return errors.New("invalid migration sequence")
		}
		if i+1 <= version {
			continue
		}
		sql, err := migrations.ReadFile("migrations/" + file.Name())
		if err != nil {
			return err
		}
		if _, err = tx.Exec(ctx, string(sql)); err != nil {
			return err
		}
	}
	return nil
}
