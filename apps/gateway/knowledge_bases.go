package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

const (
	knowledgeBaseActive     = "active"
	knowledgeBaseReindexing = "reindexing"
	knowledgeBaseBuilding   = "building"
	knowledgeBaseReady      = "ready"
	knowledgeBaseFailed     = "failed"
	knowledgeBaseSuperseded = "superseded"
)

type KnowledgeBaseEmbedding struct {
	Provider  string `json:"provider"`
	Model     string `json:"model"`
	Version   string `json:"version"`
	Dimension int    `json:"dimension"`
}

func (e KnowledgeBaseEmbedding) validate() error {
	if (e.Provider != "ollama" && e.Provider != "openai-compatible") || strings.TrimSpace(e.Model) == "" ||
		len(e.Model) > 200 || strings.TrimSpace(e.Version) == "" || len(e.Version) > 200 ||
		e.Dimension < 1 || e.Dimension > 8192 {
		return ErrInvalidConfig
	}
	return nil
}

func (e KnowledgeBaseEmbedding) indexVersion() string {
	sum := sha256.Sum256([]byte(fmt.Sprintf("%s\x00%s\x00%s\x00%d", e.Provider, e.Model, e.Version, e.Dimension)))
	return hex.EncodeToString(sum[:])
}

func (e KnowledgeBaseEmbedding) collectionName(knowledgeBaseID string) string {
	return "uai_" + strings.ReplaceAll(knowledgeBaseID, "-", "") + "_" + e.indexVersion()[:16]
}

type knowledgeBaseEmbeddingInput struct {
	Provider  string `json:"provider"`
	Model     string `json:"model"`
	Version   string `json:"version"`
	Dimension *int   `json:"dimension"`
}

func (in *knowledgeBaseEmbeddingInput) resolve() (*KnowledgeBaseEmbedding, error) {
	if in == nil {
		return nil, nil
	}
	if in.Dimension == nil {
		return nil, ErrInvalidConfig
	}
	embedding := &KnowledgeBaseEmbedding{Provider: in.Provider, Model: in.Model, Version: in.Version, Dimension: *in.Dimension}
	if e := embedding.validate(); e != nil {
		return nil, e
	}
	return embedding, nil
}

type KnowledgeBaseConfig struct {
	ChunkSize    int `json:"chunk_size"`
	ChunkOverlap int `json:"chunk_overlap"`
}

func defaultKnowledgeBaseConfig() KnowledgeBaseConfig {
	return KnowledgeBaseConfig{ChunkSize: 1000, ChunkOverlap: 200}
}

func (c KnowledgeBaseConfig) validate() error {
	if c.ChunkSize < 100 || c.ChunkSize > 8000 || c.ChunkOverlap < 0 || c.ChunkOverlap >= c.ChunkSize {
		return ErrInvalidConfig
	}
	return nil
}

type knowledgeBaseConfigInput struct {
	ChunkSize    *int `json:"chunk_size"`
	ChunkOverlap *int `json:"chunk_overlap"`
}

func (in *knowledgeBaseConfigInput) resolve(fallback KnowledgeBaseConfig) (KnowledgeBaseConfig, error) {
	if in == nil {
		return fallback, nil
	}
	if in.ChunkSize == nil || in.ChunkOverlap == nil {
		return KnowledgeBaseConfig{}, ErrInvalidConfig
	}
	config := KnowledgeBaseConfig{ChunkSize: *in.ChunkSize, ChunkOverlap: *in.ChunkOverlap}
	if e := config.validate(); e != nil {
		return KnowledgeBaseConfig{}, e
	}
	return config, nil
}

type KnowledgeBaseVersion struct {
	Version        int                     `json:"version"`
	State          string                  `json:"state"`
	Config         KnowledgeBaseConfig     `json:"config"`
	Embedding      *KnowledgeBaseEmbedding `json:"embedding,omitempty"`
	CollectionName string                  `json:"collection_name,omitempty"`
	ChunkCount     int                     `json:"chunk_count"`
	ReadyAt        *time.Time              `json:"ready_at,omitempty"`
	Attempts       int                     `json:"attempts"`
	ErrorCode      string                  `json:"error_code,omitempty"`
	CreatedAt      time.Time               `json:"created_at"`
}

type KnowledgeBase struct {
	ID            string    `json:"id"`
	Name          string    `json:"name"`
	Description   string    `json:"description"`
	Revision      int       `json:"revision"`
	ActiveVersion int       `json:"active_version"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

func (k KnowledgeBase) validate() error {
	if strings.TrimSpace(k.Name) == "" || len(k.Name) > 200 || len(k.Description) > 4000 ||
		k.Revision < 1 || k.ActiveVersion < 1 {
		return ErrInvalidConfig
	}
	return nil
}

func parseIfMatch(w http.ResponseWriter, r *http.Request) (int, bool) {
	header := r.Header.Get("If-Match")
	if header == "" {
		problem(w, 428, "if_match_required")
		return 0, false
	}
	number, e := strconv.Unquote(header)
	if e != nil {
		problem(w, 422, "invalid_if_match")
		return 0, false
	}
	expected, e := strconv.Atoi(number)
	if e != nil || expected < 1 || number != strconv.Itoa(expected) {
		problem(w, 422, "invalid_if_match")
		return 0, false
	}
	return expected, true
}

func (s *server) knowledgeBaseRoutes(r chi.Router) {
	r.With(requireScope("knowledge-bases:read")).Get("/v1/knowledge-bases", func(w http.ResponseWriter, r *http.Request) {
		rows, e := s.store.KnowledgeBases(r.Context())
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, rows)
	})
	r.With(requireScope("knowledge-bases:write")).Post("/v1/knowledge-bases", func(w http.ResponseWriter, r *http.Request) {
		var input struct {
			Name        string                       `json:"name"`
			Description string                       `json:"description"`
			Config      *knowledgeBaseConfigInput    `json:"config"`
			Embedding   *knowledgeBaseEmbeddingInput `json:"embedding"`
		}
		if !decode(w, r, &input) {
			return
		}
		config, e := input.Config.resolve(defaultKnowledgeBaseConfig())
		if e != nil {
			storeError(w, e)
			return
		}
		embedding, e := input.Embedding.resolve()
		if e != nil {
			storeError(w, e)
			return
		}
		candidate := KnowledgeBase{Name: input.Name, Description: input.Description, Revision: 1, ActiveVersion: 1}
		if e := candidate.validate(); e != nil {
			storeError(w, e)
			return
		}
		kb, e := s.store.CreateKnowledgeBase(r.Context(), input.Name, input.Description, config, embedding)
		if e != nil {
			storeError(w, e)
			return
		}
		w.Header().Set("ETag", etag(kb.Revision))
		respond(w, 201, kb)
	})
	r.With(requireScope("knowledge-bases:read")).Get("/v1/knowledge-bases/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		kb, e := s.store.KnowledgeBase(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		w.Header().Set("ETag", etag(kb.Revision))
		respond(w, 200, kb)
	})
	r.With(requireScope("knowledge-bases:write")).Patch("/v1/knowledge-bases/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		expected, ok := parseIfMatch(w, r)
		if !ok {
			return
		}
		var patch map[string]json.RawMessage
		if !decode(w, r, &patch) {
			return
		}
		if len(patch) == 0 {
			problem(w, 422, "invalid_body")
			return
		}
		current, e := s.store.KnowledgeBase(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		candidate := current
		for key, raw := range patch {
			switch key {
			case "name":
				if string(raw) == "null" || json.Unmarshal(raw, &candidate.Name) != nil {
					problem(w, 422, "invalid_configuration")
					return
				}
			case "description":
				if string(raw) == "null" || json.Unmarshal(raw, &candidate.Description) != nil {
					problem(w, 422, "invalid_configuration")
					return
				}
			default:
				problem(w, 422, "invalid_configuration")
				return
			}
		}
		if e = candidate.validate(); e != nil {
			storeError(w, e)
			return
		}
		updated, e := s.store.UpdateKnowledgeBase(r.Context(), id, expected, candidate)
		if e != nil {
			storeError(w, e)
			return
		}
		w.Header().Set("ETag", etag(updated.Revision))
		respond(w, 200, updated)
	})
	r.With(requireScope("knowledge-bases:write")).Delete("/v1/knowledge-bases/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		expected, ok := parseIfMatch(w, r)
		if !ok {
			return
		}
		if e := s.store.DeleteKnowledgeBase(r.Context(), id, expected); e != nil {
			storeError(w, e)
			return
		}
		w.WriteHeader(204)
	})
	r.With(requireScope("knowledge-bases:read")).Get("/v1/knowledge-bases/{id}/versions", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		rows, e := s.store.KnowledgeBaseVersions(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, rows)
	})
	r.With(requireScope("knowledge-bases:write")).Post("/v1/knowledge-bases/{id}/versions", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		expected, ok := parseIfMatch(w, r)
		if !ok {
			return
		}
		var input struct {
			Config    *knowledgeBaseConfigInput    `json:"config"`
			Embedding *knowledgeBaseEmbeddingInput `json:"embedding"`
		}
		if !decode(w, r, &input) {
			return
		}
		if input.Config == nil {
			problem(w, 422, "invalid_configuration")
			return
		}
		config, e := input.Config.resolve(KnowledgeBaseConfig{})
		if e != nil {
			storeError(w, e)
			return
		}
		embedding, e := input.Embedding.resolve()
		if e != nil {
			storeError(w, e)
			return
		}
		kb, version, e := s.store.CreateKnowledgeBaseVersion(r.Context(), id, expected, config, embedding)
		if e != nil {
			storeError(w, e)
			return
		}
		w.Header().Set("ETag", etag(kb.Revision))
		respond(w, 201, version)
	})
}
