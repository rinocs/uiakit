package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"regexp"
	"slices"
	"time"
	"unicode/utf8"
)

type ToolDefinition struct {
	ID           string          `json:"id"`
	Name         string          `json:"name"`
	Description  string          `json:"description"`
	Version      string          `json:"version"`
	InputSchema  json.RawMessage `json:"input_schema"`
	OutputSchema json.RawMessage `json:"output_schema"`
	Permissions  []string        `json:"permissions"`
	RiskLevel    string          `json:"risk_level"`
	Timeout      float64         `json:"timeout"`
	RetryPolicy  string          `json:"retry_policy"`
	Executor     string          `json:"executor"`
}

var toolIDPattern = regexp.MustCompile(`^[a-z][a-z0-9_.-]{0,99}$`)
var toolVersionPattern = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)
var toolPermissionPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]*:[a-z][a-z0-9_-]*$`)

func (tool ToolDefinition) validate() error {
	if !toolIDPattern.MatchString(tool.ID) || utf8.RuneCountInString(tool.Name) < 1 || utf8.RuneCountInString(tool.Name) > 200 || utf8.RuneCountInString(tool.Description) > 4000 || len(tool.Version) > 50 || !toolVersionPattern.MatchString(tool.Version) || !slices.Contains([]string{"read_only", "write", "destructive"}, tool.RiskLevel) || tool.Timeout <= 0 || tool.Timeout > 120 || tool.RetryPolicy != "never" || !slices.Contains([]string{"builtin", "http", "mcp", "isolated"}, tool.Executor) || len(tool.Permissions) < 1 || len(tool.Permissions) > 32 {
		return ErrInvalidConfig
	}
	if err := tool.validateConnector(); err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, permission := range tool.Permissions {
		if len(permission) > 100 || !toolPermissionPattern.MatchString(permission) || seen[permission] {
			return ErrInvalidConfig
		}
		seen[permission] = true
	}
	for _, schema := range []json.RawMessage{tool.InputSchema, tool.OutputSchema} {
		var fields map[string]any
		if json.Unmarshal(schema, &fields) != nil || len(fields) == 0 {
			return ErrInvalidConfig
		}
	}
	return nil
}

func (s *server) runtimeTools(ctx context.Context) ([]ToolDefinition, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, "GET", s.config.RuntimeURL+"/internal/v1/tools", nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	client := *s.client
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	response, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, ErrInvalidConfig
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, 1048577))
	if err != nil || len(data) > 1048576 {
		return nil, ErrInvalidConfig
	}
	var entries []json.RawMessage
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(&entries); err != nil {
		return nil, err
	}
	if entries == nil || len(entries) > 64 || decoder.Decode(new(any)) != io.EOF {
		return nil, ErrInvalidConfig
	}
	tools := make([]ToolDefinition, 0, len(entries))
	seen := map[string]bool{}
	for _, data := range entries {
		// Bound the actual UTF-8 descriptor, not Go's HTML-escaped re-encoding.
		if len(data) > 8192 {
			return nil, ErrInvalidConfig
		}
		var tool ToolDefinition
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.DisallowUnknownFields()
		if err = decoder.Decode(&tool); err != nil {
			return nil, err
		}
		if err = tool.validate(); err != nil {
			return nil, err
		}
		if seen[tool.ID] {
			return nil, ErrInvalidConfig
		}
		seen[tool.ID] = true
		tools = append(tools, tool)
	}
	return tools, nil
}

func (s *server) tools(w http.ResponseWriter, r *http.Request) {
	if err := s.ensurePlugins(r.Context()); err != nil {
		storeError(w, err)
		return
	}
	catalog, err := s.runtimeTools(r.Context())
	if err != nil {
		problem(w, 503, "runtime_unavailable")
		return
	}
	respond(w, 200, catalog)
}
