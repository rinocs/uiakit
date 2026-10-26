package main

import (
	"crypto/subtle"
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
)

func (s *server) requireInternal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		expected := []byte("Bearer " + s.config.InternalKey)
		actual := []byte(r.Header.Get("Authorization"))
		if len(expected) != len(actual) || subtle.ConstantTimeCompare(expected, actual) != 1 {
			problem(w, 401, "unauthorized")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *server) internalToolExecutionRoutes(r chi.Router) {
	r.Route("/internal/v1/tool-executions", func(r chi.Router) {
		r.Use(s.requireInternal)
		r.Post("/reserve", func(w http.ResponseWriter, r *http.Request) {
			var request ToolExecutionRequest
			if !decode(w, r, &request) {
				return
			}
			execution, e := s.store.ReserveToolExecution(r.Context(), request)
			if e != nil {
				storeError(w, e)
				return
			}
			respond(w, 200, execution)
		})
		r.Get("/{id}", func(w http.ResponseWriter, r *http.Request) {
			id := chi.URLParam(r, "id")
			if !validID(id) {
				problem(w, 422, "invalid_id")
				return
			}
			execution, e := s.store.ToolExecution(r.Context(), id)
			if e != nil {
				storeError(w, e)
				return
			}
			respond(w, 200, execution)
		})
		r.Post("/{id}/start", func(w http.ResponseWriter, r *http.Request) {
			s.finishToolExecution(w, r, "start")
		})
		r.Post("/{id}/complete", func(w http.ResponseWriter, r *http.Request) {
			id := chi.URLParam(r, "id")
			if !validID(id) {
				problem(w, 422, "invalid_id")
				return
			}
			var body struct {
				Result any `json:"result"`
			}
			if !decode(w, r, &body) {
				return
			}
			data, e := marshalResult(body.Result)
			if e != nil {
				problem(w, 422, "invalid_result")
				return
			}
			execution, e := s.store.CompleteToolExecution(r.Context(), id, data)
			if e != nil {
				storeError(w, e)
				return
			}
			respond(w, 200, execution)
		})
		r.Post("/{id}/fail", func(w http.ResponseWriter, r *http.Request) {
			s.finishToolExecution(w, r, "fail")
		})
		r.Post("/{id}/unknown", func(w http.ResponseWriter, r *http.Request) {
			s.finishToolExecution(w, r, "unknown")
		})
		r.Post("/{id}/reconcile", func(w http.ResponseWriter, r *http.Request) {
			id := chi.URLParam(r, "id")
			if !validID(id) {
				problem(w, 422, "invalid_id")
				return
			}
			var body struct {
				Status    string `json:"status"`
				Result    any    `json:"result"`
				ErrorCode string `json:"error_code"`
			}
			if !decode(w, r, &body) {
				return
			}
			var result json.RawMessage
			if body.Status == "completed" {
				var e error
				result, e = marshalResult(body.Result)
				if e != nil {
					problem(w, 422, "invalid_result")
					return
				}
			}
			execution, e := s.store.ReconcileToolExecution(r.Context(), id, body.Status, result, body.ErrorCode)
			if e != nil {
				storeError(w, e)
				return
			}
			respond(w, 200, execution)
		})
	})
}

func (s *server) finishToolExecution(w http.ResponseWriter, r *http.Request, action string) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	if action == "start" {
		execution, e := s.store.StartToolExecution(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, execution)
		return
	}
	var body ToolExecutionFinish
	if !decode(w, r, &body) {
		return
	}
	var execution ToolExecution
	var e error
	if action == "fail" {
		execution, e = s.store.FailToolExecution(r.Context(), id, body.ErrorCode)
	} else {
		execution, e = s.store.UnknownToolExecution(r.Context(), id, body.ErrorCode)
	}
	if e != nil {
		storeError(w, e)
		return
	}
	respond(w, 200, execution)
}

func marshalResult(value any) (json.RawMessage, error) {
	data, e := json.Marshal(value)
	if e != nil {
		return nil, e
	}
	return json.RawMessage(data), nil
}
