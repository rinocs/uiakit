package main

import (
	"net/http"

	"github.com/go-chi/chi/v5"
)

func (s *server) approvalRoutes(r chi.Router) {
	r.With(requireScope("approvals:read")).Get("/v1/approvals", func(w http.ResponseWriter, r *http.Request) {
		approvals, e := s.store.Approvals(r.Context())
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, approvals)
	})
	r.With(requireScope("approvals:read")).Get("/v1/approvals/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		approval, e := s.store.Approval(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, approval)
	})
	r.With(requireScope("approvals:write")).Post("/v1/approvals/{id}/approve", func(w http.ResponseWriter, r *http.Request) {
		s.decideApproval(w, r, "approve")
	})
	r.With(requireScope("approvals:write")).Post("/v1/approvals/{id}/reject", func(w http.ResponseWriter, r *http.Request) {
		s.decideApproval(w, r, "reject")
	})
}

func (s *server) decideApproval(w http.ResponseWriter, r *http.Request, decision string) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	approval, e := s.store.DecideApproval(r.Context(), id, decision)
	if e != nil {
		storeError(w, e)
		return
	}
	respond(w, 200, approval)
}
