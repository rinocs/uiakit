package main

import (
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
)

type DocumentJob struct {
	ID             string     `json:"id"`
	DocumentID     string     `json:"document_id"`
	State          string     `json:"state"`
	Attempts       int        `json:"attempts"`
	ErrorCode      string     `json:"error_code,omitempty"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	DeadLetteredAt *time.Time `json:"dead_lettered_at,omitempty"`
}

func (s *server) jobRoutes(r chi.Router) {
	r.With(requireScope("documents:read")).Get("/v1/documents/{id}/job", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		job, e := s.store.DocumentJob(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, job)
	})
	r.With(requireScope("documents:write")).Post("/v1/documents/{id}/job/cancel", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		job, e := s.store.CancelDocumentJob(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, job)
	})
}
