package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

func nowUTC() time.Time { return time.Now().UTC() }

func (s *PostgresStore) KnowledgeBases(ctx context.Context) ([]KnowledgeBase, error) {
	actor := currentPrincipal(ctx)
	rows, e := s.pool.Query(ctx, `SELECT id::text,name,description,revision,active_version,created_at,updated_at
		FROM knowledge_bases WHERE owner_id=$1 OR $2 ORDER BY created_at,id`, actor.ID, actor.isAdmin())
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []KnowledgeBase{}
	for rows.Next() {
		var kb KnowledgeBase
		if e = rows.Scan(&kb.ID, &kb.Name, &kb.Description, &kb.Revision, &kb.ActiveVersion, &kb.CreatedAt, &kb.UpdatedAt); e != nil {
			return nil, e
		}
		out = append(out, kb)
	}
	return out, rows.Err()
}

func (s *PostgresStore) KnowledgeBase(ctx context.Context, id string) (KnowledgeBase, error) {
	actor := currentPrincipal(ctx)
	var kb KnowledgeBase
	e := s.pool.QueryRow(ctx, `SELECT id::text,name,description,revision,active_version,created_at,updated_at
		FROM knowledge_bases WHERE id=$1 AND (owner_id=$2 OR $3)`, id, actor.ID, actor.isAdmin()).
		Scan(&kb.ID, &kb.Name, &kb.Description, &kb.Revision, &kb.ActiveVersion, &kb.CreatedAt, &kb.UpdatedAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return KnowledgeBase{}, ErrNotFound
	}
	return kb, e
}

func (s *PostgresStore) KnowledgeBaseVersions(ctx context.Context, id string) ([]KnowledgeBaseVersion, error) {
	if _, e := s.KnowledgeBase(ctx, id); e != nil {
		return nil, e
	}
	rows, e := s.pool.Query(ctx, `SELECT version,state,config,embedding_provider,embedding_model,
		embedding_version,embedding_dimension,collection_name,chunk_count,ready_at,attempts,
		coalesce(error_code,''),created_at FROM knowledge_base_versions
		WHERE knowledge_base_id=$1 ORDER BY version`, id)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []KnowledgeBaseVersion{}
	for rows.Next() {
		var v KnowledgeBaseVersion
		var config []byte
		var provider, model, version, collection sql.NullString
		var dimension sql.NullInt64
		var ready sql.NullTime
		if e = rows.Scan(&v.Version, &v.State, &config, &provider, &model, &version, &dimension,
			&collection, &v.ChunkCount, &ready, &v.Attempts, &v.ErrorCode, &v.CreatedAt); e != nil {
			return nil, e
		}
		if e = json.Unmarshal(config, &v.Config); e != nil {
			return nil, e
		}
		if provider.Valid && model.Valid && version.Valid && dimension.Valid {
			v.Embedding = &KnowledgeBaseEmbedding{Provider: provider.String, Model: model.String,
				Version: version.String, Dimension: int(dimension.Int64)}
		}
		if collection.Valid {
			v.CollectionName = collection.String
		}
		if ready.Valid {
			v.ReadyAt = &ready.Time
		}
		out = append(out, v)
	}
	return out, rows.Err()
}

func (s *PostgresStore) CreateKnowledgeBase(ctx context.Context, name, description string, config KnowledgeBaseConfig, embedding *KnowledgeBaseEmbedding) (KnowledgeBase, error) {
	candidate := KnowledgeBase{Name: name, Description: description, Revision: 1, ActiveVersion: 1}
	if e := candidate.validate(); e != nil {
		return candidate, e
	}
	if e := config.validate(); e != nil {
		return candidate, e
	}
	if embedding != nil {
		if e := embedding.validate(); e != nil {
			return candidate, e
		}
	}
	configData, e := json.Marshal(config)
	if e != nil {
		return candidate, e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return candidate, e
	}
	defer tx.Rollback(ctx)
	candidate.ID = newID()
	candidate.CreatedAt = nowUTC()
	candidate.UpdatedAt = candidate.CreatedAt
	if _, e = tx.Exec(ctx, `INSERT INTO knowledge_bases(id,owner_id,name,description,revision,active_version,created_at,updated_at)
		VALUES($1,$2,$3,$4,1,1,$5,$5)`, candidate.ID, currentPrincipal(ctx).ID, name, description, candidate.CreatedAt); e != nil {
		return candidate, e
	}
	var provider, model, version, collection any
	var dimension any
	if embedding != nil {
		provider, model, version, dimension = embedding.Provider, embedding.Model,
			embedding.Version, embedding.Dimension
		collection = embedding.collectionName(candidate.ID)
	}
	if _, e = tx.Exec(ctx, `INSERT INTO knowledge_base_versions(knowledge_base_id,version,state,config,
		embedding_provider,embedding_model,embedding_version,embedding_dimension,collection_name,created_at)
		VALUES($1,1,$2,$3,$4,$5,$6,$7,$8,$9)`, candidate.ID, knowledgeBaseActive, configData,
		provider, model, version, dimension, collection, candidate.CreatedAt); e != nil {
		return candidate, e
	}
	if _, e = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id) VALUES($1,'knowledge_base.created',$2)`,
		currentPrincipal(ctx).ID, candidate.ID); e != nil {
		return candidate, e
	}
	if e = tx.Commit(ctx); e != nil {
		return candidate, e
	}
	return candidate, nil
}

func (s *PostgresStore) UpdateKnowledgeBase(ctx context.Context, id string, expected int, candidate KnowledgeBase) (KnowledgeBase, error) {
	if e := candidate.validate(); e != nil {
		return KnowledgeBase{}, e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return KnowledgeBase{}, e
	}
	defer tx.Rollback(ctx)
	var current KnowledgeBase
	e = tx.QueryRow(ctx, `SELECT id::text,name,description,revision,active_version,created_at,updated_at
		FROM knowledge_bases WHERE id=$1 AND (owner_id=$2 OR $3) FOR UPDATE`,
		id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()).
		Scan(&current.ID, &current.Name, &current.Description, &current.Revision, &current.ActiveVersion, &current.CreatedAt, &current.UpdatedAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return KnowledgeBase{}, ErrNotFound
	}
	if e != nil {
		return KnowledgeBase{}, e
	}
	if current.Revision != expected {
		return KnowledgeBase{}, ErrPreconditionFailed
	}
	current.Name, current.Description = candidate.Name, candidate.Description
	if e = tx.QueryRow(ctx, `UPDATE knowledge_bases SET name=$2,description=$3,revision=revision+1,updated_at=now()
		WHERE id=$1 RETURNING revision,created_at,updated_at`, id, current.Name, current.Description).
		Scan(&current.Revision, &current.CreatedAt, &current.UpdatedAt); e != nil {
		return KnowledgeBase{}, e
	}
	if _, e = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id) VALUES($1,'knowledge_base.updated',$2)`,
		currentPrincipal(ctx).ID, id); e != nil {
		return KnowledgeBase{}, e
	}
	if e = tx.Commit(ctx); e != nil {
		return KnowledgeBase{}, e
	}
	return current, nil
}

func (s *PostgresStore) DeleteKnowledgeBase(ctx context.Context, id string, expected int) error {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	var revision int
	e = tx.QueryRow(ctx, `SELECT revision FROM knowledge_bases WHERE id=$1 AND (owner_id=$2 OR $3) FOR UPDATE`,
		id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()).Scan(&revision)
	if errors.Is(e, pgx.ErrNoRows) {
		return ErrNotFound
	}
	if e != nil {
		return e
	}
	if revision != expected {
		return ErrPreconditionFailed
	}
	var inUse bool
	if e = tx.QueryRow(ctx, `SELECT EXISTS(
		SELECT 1 FROM assistant_versions v
		JOIN assistants a ON a.id=v.assistant_id AND a.current_version=v.version
		WHERE v.config->'knowledge_base_ids' ? $1)`, id).Scan(&inUse); e != nil {
		return e
	}
	if inUse {
		return ErrConflict
	}
	if e = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM documents WHERE knowledge_base_id=$1)`, id).Scan(&inUse); e != nil {
		return e
	}
	if inUse {
		return ErrConflict
	}
	if _, e = tx.Exec(ctx, `INSERT INTO deletion_tombstones(id,resource_type,resource_id,deleted_by,reason)
		VALUES($1,'knowledge_base',$2,$3,'manual') ON CONFLICT (resource_type,resource_id) DO NOTHING`,
		newID(), id, currentPrincipal(ctx).ID); e != nil {
		return e
	}
	if _, e = tx.Exec(ctx, `DELETE FROM knowledge_bases WHERE id=$1`, id); e != nil {
		return e
	}
	if _, e = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id) VALUES($1,'knowledge_base.deleted',$2)`,
		currentPrincipal(ctx).ID, id); e != nil {
		return e
	}
	return tx.Commit(ctx)
}

func (s *PostgresStore) CreateKnowledgeBaseVersion(ctx context.Context, id string, expected int, config KnowledgeBaseConfig, embedding *KnowledgeBaseEmbedding) (KnowledgeBase, KnowledgeBaseVersion, error) {
	if e := config.validate(); e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	if embedding != nil {
		if e := embedding.validate(); e != nil {
			return KnowledgeBase{}, KnowledgeBaseVersion{}, e
		}
	}
	configData, e := json.Marshal(config)
	if e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	defer tx.Rollback(ctx)
	var kb KnowledgeBase
	e = tx.QueryRow(ctx, `SELECT id::text,name,description,revision,active_version,created_at,updated_at
		FROM knowledge_bases WHERE id=$1 AND (owner_id=$2 OR $3) FOR UPDATE`,
		id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()).
		Scan(&kb.ID, &kb.Name, &kb.Description, &kb.Revision, &kb.ActiveVersion, &kb.CreatedAt, &kb.UpdatedAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, ErrNotFound
	}
	if e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	if kb.Revision != expected {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, ErrPreconditionFailed
	}
	var reindexing bool
	if e = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM knowledge_base_versions WHERE knowledge_base_id=$1
		AND state IN ('reindexing','building'))`, id).Scan(&reindexing); e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	if reindexing {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, ErrConflict
	}
	if embedding == nil {
		var provider, model, version sql.NullString
		var dimension sql.NullInt64
		e = tx.QueryRow(ctx, `SELECT embedding_provider,embedding_model,embedding_version,embedding_dimension
			FROM knowledge_base_versions WHERE knowledge_base_id=$1 AND version=$2`,
			id, kb.ActiveVersion).Scan(&provider, &model, &version, &dimension)
		if e != nil {
			return KnowledgeBase{}, KnowledgeBaseVersion{}, e
		}
		if provider.Valid && model.Valid && version.Valid && dimension.Valid {
			embedding = &KnowledgeBaseEmbedding{Provider: provider.String, Model: model.String,
				Version: version.String, Dimension: int(dimension.Int64)}
			if e = embedding.validate(); e != nil {
				return KnowledgeBase{}, KnowledgeBaseVersion{}, e
			}
		}
	}
	var next int
	if e = tx.QueryRow(ctx, `SELECT COALESCE(max(version),0)+1 FROM knowledge_base_versions WHERE knowledge_base_id=$1`, id).Scan(&next); e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	version := KnowledgeBaseVersion{Version: next, State: knowledgeBaseReindexing, Config: config,
		Embedding: embedding, CreatedAt: nowUTC()}
	var provider, model, embVersion, collection any
	var dimension any
	if embedding != nil {
		provider, model, embVersion, dimension = embedding.Provider, embedding.Model,
			embedding.Version, embedding.Dimension
		version.CollectionName = embedding.collectionName(id)
		collection = version.CollectionName
		if _, e = tx.Exec(ctx, `UPDATE knowledge_base_versions SET collection_name=NULL
			WHERE knowledge_base_id=$1 AND collection_name=$2`, id, version.CollectionName); e != nil {
			return KnowledgeBase{}, KnowledgeBaseVersion{}, e
		}
	}
	if _, e = tx.Exec(ctx, `INSERT INTO knowledge_base_versions(knowledge_base_id,version,state,config,
		embedding_provider,embedding_model,embedding_version,embedding_dimension,collection_name,created_at)
		VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`, id, version.Version, version.State, configData,
		provider, model, embVersion, dimension, collection, version.CreatedAt); e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	if e = tx.QueryRow(ctx, `UPDATE knowledge_bases SET revision=revision+1,updated_at=now()
		WHERE id=$1 RETURNING revision,created_at,updated_at`, id).
		Scan(&kb.Revision, &kb.CreatedAt, &kb.UpdatedAt); e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	if _, e = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id) VALUES($1,'knowledge_base.version_created',$2)`,
		currentPrincipal(ctx).ID, id); e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	if e = tx.Commit(ctx); e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	return kb, version, nil
}

func validateKnowledgeBasesTx(ctx context.Context, tx pgx.Tx, ids []string) error {
	if len(ids) == 0 {
		return nil
	}
	for _, id := range ids {
		if !validID(id) {
			return ErrInvalidConfig
		}
	}
	rows, e := tx.Query(ctx, `SELECT id::text FROM knowledge_bases
		WHERE id=ANY($1::uuid[]) AND (owner_id=$2 OR $3) FOR SHARE`,
		ids, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin())
	if e != nil {
		return ErrInvalidConfig
	}
	defer rows.Close()
	count := 0
	for rows.Next() {
		count++
	}
	if e = rows.Err(); e != nil {
		return e
	}
	if count != len(ids) {
		return ErrInvalidConfig
	}
	return nil
}
