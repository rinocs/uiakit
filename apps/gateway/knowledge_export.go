package main

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
)

const (
	maxExportChunks = 2000
	maxExportBytes  = 8 << 20
)

type ExportChunk struct {
	ChunkID         string `json:"chunk_id"`
	DocumentID      string `json:"document_id"`
	DocumentHash    string `json:"document_hash"`
	DocumentVersion int    `json:"document_version"`
	Page            int    `json:"page"`
	Start           int    `json:"start"`
	End             int    `json:"end"`
	Text            string `json:"text"`
	ChunkSize       int    `json:"chunk_size"`
	Overlap         int    `json:"overlap"`
}

type KnowledgeBaseExport struct {
	KnowledgeBase KnowledgeBase          `json:"knowledge_base"`
	Versions      []KnowledgeBaseVersion `json:"versions"`
	Documents     []Document             `json:"documents"`
	Chunks        []ExportChunk          `json:"chunks"`
	ExportedAt    time.Time              `json:"exported_at"`
}

func (s *server) exportRoutes(r chi.Router) {
	r.With(requireScope("knowledge-bases:read")).Get("/v1/knowledge-bases/{id}/export", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		export, e := s.store.KnowledgeBaseExport(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		data, e := json.Marshal(export)
		if e != nil || len(data) > maxExportBytes {
			problem(w, 413, "export_too_large")
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		w.Write(data)
	})
}

func (s *PostgresStore) KnowledgeBaseExport(ctx context.Context, id string) (KnowledgeBaseExport, error) {
	kb, e := s.KnowledgeBase(ctx, id)
	if e != nil {
		return KnowledgeBaseExport{}, e
	}
	versions, e := s.KnowledgeBaseVersions(ctx, id)
	if e != nil {
		return KnowledgeBaseExport{}, e
	}
	documents, e := s.Documents(ctx, id)
	if e != nil {
		return KnowledgeBaseExport{}, e
	}
	for i := range documents {
		documents[i].BlobKey = ""
	}
	rows, e := s.pool.Query(ctx, `SELECT c.chunk_id,c.document_id::text,c.document_hash,
		c.document_version,c.page,c.start_offset,c.end_offset,c.text,c.chunk_size,c.overlap
		FROM document_chunks c JOIN documents d ON d.id=c.document_id
		WHERE d.knowledge_base_id=$1
		ORDER BY c.document_id,c.chunk_index LIMIT $2`, id, maxExportChunks+1)
	if e != nil {
		return KnowledgeBaseExport{}, e
	}
	defer rows.Close()
	chunks := []ExportChunk{}
	for rows.Next() {
		var c ExportChunk
		if e = rows.Scan(&c.ChunkID, &c.DocumentID, &c.DocumentHash, &c.DocumentVersion,
			&c.Page, &c.Start, &c.End, &c.Text, &c.ChunkSize, &c.Overlap); e != nil {
			return KnowledgeBaseExport{}, e
		}
		chunks = append(chunks, c)
	}
	if e = rows.Err(); e != nil {
		return KnowledgeBaseExport{}, e
	}
	if len(chunks) > maxExportChunks {
		return KnowledgeBaseExport{}, ErrExportTooLarge
	}
	return KnowledgeBaseExport{KnowledgeBase: kb, Versions: versions, Documents: documents,
		Chunks: chunks, ExportedAt: nowUTC()}, nil
}
