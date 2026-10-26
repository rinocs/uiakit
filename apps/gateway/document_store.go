package main

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
)

const documentColumns = `d.id::text,d.knowledge_base_id::text,d.filename,d.title,d.mime_type,
	d.size_bytes,d.sha256,d.blob_key,d.created_at,j.state`

func scanDocument(row interface{ Scan(...any) error }) (Document, error) {
	var d Document
	e := row.Scan(&d.ID, &d.KnowledgeBaseID, &d.Filename, &d.Title, &d.MIMEType,
		&d.SizeBytes, &d.SHA256, &d.BlobKey, &d.CreatedAt, &d.IngestionState)
	if errors.Is(e, pgx.ErrNoRows) {
		return Document{}, ErrNotFound
	}
	return d, e
}

func (s *PostgresStore) Documents(ctx context.Context, kbID string) ([]Document, error) {
	if kbID != "" {
		if _, e := s.KnowledgeBase(ctx, kbID); e != nil {
			return nil, e
		}
	}
	var filter any
	if kbID != "" {
		filter = kbID
	}
	rows, e := s.pool.Query(ctx, `SELECT `+documentColumns+`
		FROM documents d
		JOIN knowledge_bases k ON k.id=d.knowledge_base_id
		JOIN document_jobs j ON j.document_id=d.id
		WHERE (k.owner_id=$1 OR $2) AND ($3::uuid IS NULL OR d.knowledge_base_id=$3::uuid)
		ORDER BY d.created_at DESC,d.id`, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin(), filter)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []Document{}
	for rows.Next() {
		doc, e := scanDocument(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, doc)
	}
	return out, rows.Err()
}

func (s *PostgresStore) Document(ctx context.Context, id string) (Document, error) {
	return scanDocument(s.pool.QueryRow(ctx, `SELECT `+documentColumns+`
		FROM documents d
		JOIN knowledge_bases k ON k.id=d.knowledge_base_id
		JOIN document_jobs j ON j.document_id=d.id
		WHERE d.id=$1 AND (k.owner_id=$2 OR $3)`,
		id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
}

func (s *PostgresStore) DocumentByHash(ctx context.Context, kbID, hash string) (Document, error) {
	return scanDocument(s.pool.QueryRow(ctx, `SELECT `+documentColumns+`
		FROM documents d
		JOIN knowledge_bases k ON k.id=d.knowledge_base_id
		JOIN document_jobs j ON j.document_id=d.id
		WHERE d.knowledge_base_id=$1 AND d.sha256=$2 AND (k.owner_id=$3 OR $4)`,
		kbID, hash, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
}

func (s *PostgresStore) CreateDocument(ctx context.Context, doc Document) (Document, bool, error) {
	if e := doc.validate(); e != nil {
		return doc, false, e
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return doc, false, e
	}
	defer tx.Rollback(ctx)
	var kb string
	e = tx.QueryRow(ctx, `SELECT id::text FROM knowledge_bases WHERE id=$1 AND (owner_id=$2 OR $3) FOR SHARE`,
		doc.KnowledgeBaseID, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()).Scan(&kb)
	if errors.Is(e, pgx.ErrNoRows) {
		return doc, false, ErrNotFound
	}
	if e != nil {
		return doc, false, e
	}
	doc.ID = newID()
	doc.CreatedAt = nowUTC()
	doc.IngestionState = "queued"
	var id string
	e = tx.QueryRow(ctx, `INSERT INTO documents(id,knowledge_base_id,uploaded_by,filename,title,mime_type,size_bytes,sha256,blob_key,created_at)
		VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
		ON CONFLICT (knowledge_base_id,sha256) DO NOTHING
		RETURNING id::text`, doc.ID, doc.KnowledgeBaseID, currentPrincipal(ctx).ID, doc.Filename,
		doc.Title, doc.MIMEType, doc.SizeBytes, doc.SHA256, doc.BlobKey, doc.CreatedAt).Scan(&id)
	if errors.Is(e, pgx.ErrNoRows) {
		existing, e := scanDocument(tx.QueryRow(ctx, `SELECT `+documentColumns+`
			FROM documents d
			JOIN knowledge_bases k ON k.id=d.knowledge_base_id
			JOIN document_jobs j ON j.document_id=d.id
			WHERE d.knowledge_base_id=$1 AND d.sha256=$2 AND (k.owner_id=$3 OR $4)`,
			doc.KnowledgeBaseID, doc.SHA256, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
		return existing, false, e
	}
	if e != nil {
		return doc, false, e
	}
	if _, e = tx.Exec(ctx, `INSERT INTO document_jobs(id,document_id,state) VALUES($1,$2,'queued')`, newID(), id); e != nil {
		return doc, false, e
	}
	if _, e = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id) VALUES($1,'document.uploaded',$2)`,
		currentPrincipal(ctx).ID, id); e != nil {
		return doc, false, e
	}
	if e = tx.Commit(ctx); e != nil {
		return doc, false, e
	}
	return doc, true, nil
}

func (s *PostgresStore) DeleteDocument(ctx context.Context, id string) (Document, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return Document{}, e
	}
	defer tx.Rollback(ctx)
	doc, e := scanDocument(tx.QueryRow(ctx, `SELECT `+documentColumns+`
		FROM documents d
		JOIN knowledge_bases k ON k.id=d.knowledge_base_id
		JOIN document_jobs j ON j.document_id=d.id
		WHERE d.id=$1 AND (k.owner_id=$2 OR $3) FOR UPDATE OF d`,
		id, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
	if e != nil {
		return Document{}, e
	}
	rows, e := tx.Query(ctx, `SELECT chunk_id FROM document_chunks WHERE document_id=$1`, id)
	if e != nil {
		return Document{}, e
	}
	chunkIDs := []string{}
	for rows.Next() {
		var chunkID string
		if e = rows.Scan(&chunkID); e != nil {
			rows.Close()
			return Document{}, e
		}
		chunkIDs = append(chunkIDs, chunkID)
	}
	if e = rows.Err(); e != nil {
		rows.Close()
		return Document{}, e
	}
	rows.Close()
	if len(chunkIDs) > 0 {
		if _, e = tx.Exec(ctx, `INSERT INTO vector_cleanup_jobs(id,document_id,knowledge_base_id,chunk_ids,state)
			VALUES($1,$2,$3,$4,'queued')
			ON CONFLICT (document_id) DO UPDATE SET chunk_ids=EXCLUDED.chunk_ids,
			state='queued',attempts=0,lease_owner=NULL,lease_until=NULL,error_code=NULL,updated_at=now()`,
			newID(), id, doc.KnowledgeBaseID, chunkIDs); e != nil {
			return Document{}, e
		}
	}
	if _, e = tx.Exec(ctx, `INSERT INTO deletion_tombstones(id,resource_type,resource_id,deleted_by,reason)
		VALUES($1,'document',$2,$3,'manual') ON CONFLICT (resource_type,resource_id) DO NOTHING`,
		newID(), id, currentPrincipal(ctx).ID); e != nil {
		return Document{}, e
	}
	if _, e = tx.Exec(ctx, `DELETE FROM documents WHERE id=$1`, id); e != nil {
		return Document{}, e
	}
	if _, e = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id) VALUES($1,'document.deleted',$2)`,
		currentPrincipal(ctx).ID, id); e != nil {
		return Document{}, e
	}
	if e = tx.Commit(ctx); e != nil {
		return Document{}, e
	}
	return doc, nil
}

func scanJob(row interface{ Scan(...any) error }) (DocumentJob, error) {
	var job DocumentJob
	e := row.Scan(&job.ID, &job.DocumentID, &job.State, &job.Attempts, &job.ErrorCode,
		&job.CreatedAt, &job.UpdatedAt, &job.DeadLetteredAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return DocumentJob{}, ErrNotFound
	}
	return job, e
}

func (s *PostgresStore) DocumentJob(ctx context.Context, documentID string) (DocumentJob, error) {
	return scanJob(s.pool.QueryRow(ctx, `SELECT j.id::text,j.document_id::text,j.state,j.attempts,
		coalesce(j.error_code,''),j.created_at,j.updated_at,j.dead_lettered_at
		FROM document_jobs j
		JOIN documents d ON d.id=j.document_id
		JOIN knowledge_bases k ON k.id=d.knowledge_base_id
		WHERE d.id=$1 AND (k.owner_id=$2 OR $3)`,
		documentID, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
}

func (s *PostgresStore) CancelDocumentJob(ctx context.Context, documentID string) (DocumentJob, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return DocumentJob{}, e
	}
	defer tx.Rollback(ctx)
	job, e := scanJob(tx.QueryRow(ctx, `SELECT j.id::text,j.document_id::text,j.state,j.attempts,
		coalesce(j.error_code,''),j.created_at,j.updated_at,j.dead_lettered_at
		FROM document_jobs j
		JOIN documents d ON d.id=j.document_id
		JOIN knowledge_bases k ON k.id=d.knowledge_base_id
		WHERE d.id=$1 AND (k.owner_id=$2 OR $3) FOR UPDATE OF j`,
		documentID, currentPrincipal(ctx).ID, currentPrincipal(ctx).isAdmin()))
	if e != nil {
		return DocumentJob{}, e
	}
	if job.State == "completed" || job.State == "failed" {
		return DocumentJob{}, ErrConflict
	}
	if job.State != "cancelled" {
		if _, e = tx.Exec(ctx, `UPDATE document_jobs SET state='cancelled',lease_owner=NULL,
			lease_until=NULL,updated_at=now() WHERE id=$1`, job.ID); e != nil {
			return DocumentJob{}, e
		}
		if _, e = tx.Exec(ctx, `INSERT INTO audit_events(actor_principal_id,action,target_id)
			VALUES($1,'job.cancelled',$2)`, currentPrincipal(ctx).ID, documentID); e != nil {
			return DocumentJob{}, e
		}
		job.State = "cancelled"
		job.UpdatedAt = nowUTC()
	}
	if e = tx.Commit(ctx); e != nil {
		return DocumentJob{}, e
	}
	return job, nil
}
