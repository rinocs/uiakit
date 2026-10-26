package main

import (
	"net/http"

	"github.com/go-chi/chi/v5"
)

type RetentionPolicy struct {
	ConversationDays int
	AuditDays        int
	ApprovalDays     int
	CleanupDays      int
}

type RetentionResult struct {
	Conversations int `json:"conversations"`
	Approvals     int `json:"approvals"`
	AuditEvents   int `json:"audit_events"`
	CleanupJobs   int `json:"cleanup_jobs"`
}

func (s *server) deleteConversation(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	if err := s.store.DeleteConversation(r.Context(), id); err != nil {
		storeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *server) internalRetentionRoutes(r chi.Router) {
	r.Route("/internal/v1/retention", func(r chi.Router) {
		r.Use(s.requireInternal)
		r.Post("/run", func(w http.ResponseWriter, r *http.Request) {
			policy := RetentionPolicy{
				ConversationDays: s.config.RetentionConversationDays,
				AuditDays:        s.config.RetentionAuditDays,
				ApprovalDays:     s.config.RetentionApprovalDays,
				CleanupDays:      s.config.RetentionCleanupDays,
			}
			result, err := s.store.RunRetention(r.Context(), policy)
			if err != nil {
				storeError(w, err)
				return
			}
			respond(w, 200, result)
		})
	})
}
