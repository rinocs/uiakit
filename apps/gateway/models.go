package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"slices"
)

type ModelDefinition struct {
	ID              string   `json:"id"`
	Provider        string   `json:"provider"`
	Capabilities    []string `json:"capabilities"`
	MaxOutputTokens *int     `json:"max_output_tokens"`
	ContextWindow   *int     `json:"context_window"`
}

func (m ModelDefinition) supports(capability string) bool {
	return slices.Contains(m.Capabilities, capability)
}
func (m ModelDefinition) validate() error {
	if m.ID == "" || len(m.ID) > 200 || m.Provider != "openai-compatible" || len(m.Capabilities) == 0 {
		return ErrInvalidConfig
	}
	seen := map[string]bool{}
	for _, c := range m.Capabilities {
		if !slices.Contains([]string{"chat", "streaming", "tool_calling", "structured_output", "embeddings", "reranking", "vision"}, c) || seen[c] {
			return ErrInvalidConfig
		}
		seen[c] = true
	}
	if m.MaxOutputTokens != nil && *m.MaxOutputTokens < 1 || m.ContextWindow != nil && *m.ContextWindow < 1 {
		return ErrInvalidConfig
	}
	return nil
}
func loadRuntimeModels(ctx context.Context, c Config) ([]ModelDefinition, error) {
	req, e := http.NewRequestWithContext(ctx, "GET", c.RuntimeURL+"/internal/v1/models", nil)
	if e != nil {
		return nil, e
	}
	req.Header.Set("Authorization", "Bearer "+c.InternalKey)
	// Never forward the service key through a redirect.
	client := &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, e := client.Do(req)
	if e != nil {
		return nil, e
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, errors.New("runtime catalog unavailable")
	}
	data, e := io.ReadAll(io.LimitReader(response.Body, 65537))
	if e != nil || len(data) > 65536 {
		return nil, errors.New("runtime catalog oversized")
	}
	var models []ModelDefinition
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&models); e != nil {
		return nil, e
	}
	if decoder.Decode(new(any)) != io.EOF {
		return nil, ErrInvalidConfig
	}
	if len(models) != 1 || models[0].ID != c.Model {
		return nil, ErrInvalidConfig
	}
	for _, m := range models {
		if e = m.validate(); e != nil {
			return nil, e
		}
	}
	return models, nil
}
