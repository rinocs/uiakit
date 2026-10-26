package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strings"

	"github.com/go-chi/chi/v5"
)

var ErrPreconditionFailed = errors.New("precondition_failed")
var ErrInvalidConfig = errors.New("invalid_configuration")

type AssistantLimits struct {
	MaxInputChars   int     `json:"max_input_chars"`
	MaxOutputChars  int     `json:"max_output_chars"`
	DurationSeconds float64 `json:"duration_seconds"`
	MaxSteps        int     `json:"max_steps"`
	MaxToolCalls    int     `json:"max_tool_calls"`
	MaxTokens       int     `json:"max_tokens"`
}
type MemoryConfig struct {
	Conversation bool `json:"conversation"`
	Semantic     bool `json:"semantic"`
}
type AssistantPolicy struct {
	RequireToolApproval bool `json:"require_tool_approval"`
}
type Assistant struct {
	ID               string          `json:"id"`
	Version          int             `json:"version"`
	Name             string          `json:"name"`
	Description      string          `json:"description"`
	Model            string          `json:"model"`
	SystemPrompt     string          `json:"system_prompt"`
	Directives       []string        `json:"directives"`
	Tools            []string        `json:"tools"`
	Skills           []string        `json:"skills"`
	KnowledgeBaseIDs []string        `json:"knowledge_base_ids"`
	Memory           MemoryConfig    `json:"memory"`
	Limits           AssistantLimits `json:"limits"`
	Policy           AssistantPolicy `json:"policy"`
	StructuredOutput json.RawMessage `json:"structured_output,omitempty"`
}

func defaultAssistant() Assistant {
	return Assistant{Directives: []string{}, Tools: []string{}, Skills: []string{}, KnowledgeBaseIDs: []string{}, Memory: MemoryConfig{Conversation: true}, Limits: AssistantLimits{64000, 64000, 120, 4, 8, 8192}, Policy: AssistantPolicy{RequireToolApproval: true}}
}

var directiveName = regexp.MustCompile(`^[a-z][a-z0-9_.-]{0,99}$`)

func (a Assistant) validate() error {
	if strings.TrimSpace(a.Name) == "" || len(a.Name) > 200 || len(a.Description) > 4000 || len(a.Model) == 0 || len(a.Model) > 200 || len(a.SystemPrompt) > 16000 {
		return ErrInvalidConfig
	}
	if len(a.Directives) > 64 || len(a.Tools) > 64 || len(a.Skills) > 0 || len(a.KnowledgeBaseIDs) > 64 || a.Memory.Semantic || !a.Policy.RequireToolApproval {
		return ErrInvalidConfig
	}
	seen := map[string]bool{}
	for _, name := range a.Directives {
		if !directiveName.MatchString(name) || seen[name] {
			return ErrInvalidConfig
		}
		seen[name] = true
	}
	seen = map[string]bool{}
	for _, id := range a.Tools {
		if !toolIDPattern.MatchString(id) || seen[id] {
			return ErrInvalidConfig
		}
		seen[id] = true
	}
	seen = map[string]bool{}
	for _, id := range a.KnowledgeBaseIDs {
		if !validID(id) || seen[id] {
			return ErrInvalidConfig
		}
		seen[id] = true
	}
	if a.Limits.MaxInputChars < 1 || a.Limits.MaxInputChars > 64000 || a.Limits.MaxOutputChars < 1 || a.Limits.MaxOutputChars > 64000 || a.Limits.DurationSeconds <= 0 || a.Limits.DurationSeconds > 120 || a.Limits.MaxSteps < 0 || a.Limits.MaxSteps > 16 || a.Limits.MaxToolCalls < 0 || a.Limits.MaxToolCalls > 32 || a.Limits.MaxTokens < 0 || a.Limits.MaxTokens > 1000000 {
		return ErrInvalidConfig
	}
	if len(a.StructuredOutput) > 0 {
		var schema map[string]any
		if len(a.StructuredOutput) > 16384 || json.Unmarshal(a.StructuredOutput, &schema) != nil || len(schema) == 0 {
			return ErrInvalidConfig
		}
	}
	return nil
}
func containsNull(value any) bool {
	switch v := value.(type) {
	case nil:
		return true
	case map[string]any:
		for _, x := range v {
			if containsNull(x) {
				return true
			}
		}
	case []any:
		for _, x := range v {
			if containsNull(x) {
				return true
			}
		}
	}
	return false
}
func applyAssistantPatch(current Assistant, patch json.RawMessage) (Assistant, error) {
	var fields map[string]any
	if json.Unmarshal(patch, &fields) != nil || len(fields) == 0 || containsNull(fields) {
		return Assistant{}, ErrInvalidConfig
	}
	for _, key := range []string{"id", "version", "owner_id"} {
		if _, ok := fields[key]; ok {
			return Assistant{}, ErrInvalidConfig
		}
	}
	// Round-trip copies slice backing arrays before applying a partial update.
	original, _ := json.Marshal(current)
	var next Assistant
	json.Unmarshal(original, &next)
	decoder := json.NewDecoder(bytes.NewReader(patch))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&next) != nil {
		return Assistant{}, ErrInvalidConfig
	}
	if e := next.validate(); e != nil {
		return Assistant{}, e
	}
	return next, nil
}
func (s *server) validateAssistantModel(ctx context.Context, a Assistant) error {
	models, e := s.store.Models(ctx)
	if e != nil {
		return e
	}
	for _, m := range models {
		if m.ID == a.Model && m.supports("chat") && m.supports("streaming") {
			return s.validateAssistantDirectives(ctx, a.Directives)
		}
	}
	return ErrInvalidConfig
}
func etag(version int) string { return fmt.Sprintf(`"%d"`, version) }
func (s *server) assistantRoutes(r chi.Router) {
	r.With(requireScope("assistants:read")).Get("/v1/assistants/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		a, e := s.store.Assistant(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		w.Header().Set("ETag", etag(a.Version))
		respond(w, 200, a)
	})
	r.With(requireScope("assistants:read")).Get("/v1/assistants/{id}/versions", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		rows, e := s.store.AssistantVersions(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		respond(w, 200, rows)
	})
	r.With(requireScope("assistants:write")).Patch("/v1/assistants/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if !validID(id) {
			problem(w, 422, "invalid_id")
			return
		}
		expected, ok := parseIfMatch(w, r)
		if !ok {
			return
		}
		var patch json.RawMessage
		if !decode(w, r, &patch) {
			return
		}
		current, e := s.store.Assistant(r.Context(), id)
		if e != nil {
			storeError(w, e)
			return
		}
		candidate, e := applyAssistantPatch(current, patch)
		if e != nil {
			storeError(w, e)
			return
		}
		if e = s.validateAssistantModel(r.Context(), candidate); e != nil {
			storeError(w, e)
			return
		}
		updated, e := s.store.UpdateAssistant(r.Context(), id, expected, patch)
		if e != nil {
			storeError(w, e)
			return
		}
		w.Header().Set("ETag", etag(updated.Version))
		respond(w, 200, updated)
	})
}
