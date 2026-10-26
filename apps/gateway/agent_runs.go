package main

import (
	"context"
	"io"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
)

func (s *server) agentRunRoutes(r chi.Router) {
	r.With(requireScope("agent-runs:read")).Get("/v1/agent-runs", func(w http.ResponseWriter, r *http.Request) {
		runs, e := s.store.AgentRuns(r.Context())
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, runs)
	})
	r.With(requireScope("agent-runs:read")).Get("/v1/agent-runs/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		run, e := s.store.AgentRun(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, run)
	})
	r.With(requireScope("agent-runs:write")).Post("/v1/agent-runs/{id}/cancel", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		run, e := s.store.CancelAgentRun(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		if entry := s.activeRun(id); entry != nil {
			entry.cancelled.Store(true)
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		cancelled := s.cancelRuntimeRun(ctx, id)
		cancel()
		if !cancelled {
			s.cancelActiveRun(id)
		}
		respond(w, 200, run)
	})
}

func (s *server) cancelRuntimeRun(ctx context.Context, id string) bool {
	req, e := http.NewRequestWithContext(ctx, "POST", s.config.RuntimeURL+"/internal/v1/runs/"+id+"/cancel", nil)
	if e != nil {
		return false
	}
	req.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	response, e := s.client.Do(req)
	if e != nil {
		return false
	}
	defer response.Body.Close()
	io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
	return response.StatusCode == 204
}
