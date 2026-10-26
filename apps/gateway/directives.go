package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"
)

var ErrDirectiveRuntimeUnavailable = errors.New("directive_runtime_unavailable")

// The runtime owns registry/dependency semantics; validate before storing a new
// assistant version. Run preflight checks the selection again against its registry.
func (s *server) validateAssistantDirectives(ctx context.Context, selected []string) error {
	if len(selected) == 0 {
		return nil
	}
	if err := s.ensurePlugins(ctx); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	body, err := json.Marshal(struct {
		Directives []string `json:"directives"`
	}{selected})
	if err != nil {
		return ErrInvalidConfig
	}
	req, err := http.NewRequestWithContext(ctx, "POST", s.config.RuntimeURL+"/internal/v1/directives/validate", bytes.NewReader(body))
	if err != nil {
		return ErrDirectiveRuntimeUnavailable
	}
	req.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	req.Header.Set("Content-Type", "application/json")
	// Never send the internal key or repeat the validation through redirects.
	client := *s.client
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	response, err := client.Do(req)
	if err != nil {
		return ErrDirectiveRuntimeUnavailable
	}
	defer response.Body.Close()
	switch response.StatusCode {
	case http.StatusNoContent:
		return nil
	case http.StatusUnprocessableEntity:
		return ErrInvalidConfig
	default:
		return ErrDirectiveRuntimeUnavailable
	}
}
