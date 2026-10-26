package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"regexp"
	"slices"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
)

type PluginSetting struct {
	Enabled bool            `json:"enabled"`
	Config  json.RawMessage `json:"config"`
}
type PluginConfiguration struct {
	Revision int                      `json:"revision"`
	Settings map[string]PluginSetting `json:"settings"`
}
type PluginStore interface {
	PluginConfiguration(context.Context) (PluginConfiguration, error)
	UpdatePluginConfiguration(context.Context, int, map[string]PluginSetting) (PluginConfiguration, error)
}
type RuntimePlugin struct {
	Manifest json.RawMessage `json:"manifest"`
	State    string          `json:"state"`
}

var pluginIDPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$`)

func validPluginSettings(settings map[string]PluginSetting) bool {
	if settings == nil || len(settings) > 64 {
		return false
	}
	for id, item := range settings {
		var object map[string]json.RawMessage
		if len(id) > 200 || !pluginIDPattern.MatchString(id) || len(item.Config) > 32768 || json.Unmarshal(item.Config, &object) != nil || object == nil {
			return false
		}
	}
	return true
}

// This client never follows redirects, returns private diagnostics, or accepts code paths.
func (s *server) pluginRequest(ctx context.Context, method, path string, body any) ([]byte, int, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	var data []byte
	var err error
	if body != nil {
		data, err = json.Marshal(body)
		if err != nil {
			return nil, 0, err
		}
	}
	request, err := http.NewRequestWithContext(ctx, method, s.config.RuntimeURL+"/internal/v1/plugins"+path, bytes.NewReader(data))
	if err != nil {
		return nil, 0, err
	}
	request.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	request.Header.Set("Content-Type", "application/json")
	client := *s.client
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	response, err := client.Do(request)
	if err != nil {
		return nil, 0, err
	}
	defer response.Body.Close()
	data, err = io.ReadAll(io.LimitReader(response.Body, 2097153))
	if err != nil || len(data) > 2097152 {
		return nil, 0, ErrDirectiveRuntimeUnavailable
	}
	return data, response.StatusCode, nil
}

func strictPluginJSON(data []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if decoder.Decode(new(any)) != io.EOF {
		return ErrInvalidConfig
	}
	return nil
}
func (s *server) runtimePlugins(ctx context.Context) ([]RuntimePlugin, error) {
	data, status, err := s.pluginRequest(ctx, "GET", "", nil)
	if err != nil || status != 200 {
		return nil, ErrDirectiveRuntimeUnavailable
	}
	var entries []RuntimePlugin
	if strictPluginJSON(data, &entries) != nil || entries == nil || len(entries) > 64 {
		return nil, ErrDirectiveRuntimeUnavailable
	}
	seen := map[string]bool{}
	for _, entry := range entries {
		var manifest map[string]json.RawMessage
		var id, runtime string
		if len(entry.Manifest) > 32768 || json.Unmarshal(entry.Manifest, &manifest) != nil || json.Unmarshal(manifest["id"], &id) != nil || json.Unmarshal(manifest["runtime"], &runtime) != nil || !slices.Contains([]string{"python", "isolated_http"}, runtime) || len(id) > 200 || !pluginIDPattern.MatchString(id) || seen[id] || !slices.Contains([]string{"inactive", "active", "failed"}, entry.State) {
			return nil, ErrDirectiveRuntimeUnavailable
		}
		for key := range manifest {
			if !slices.Contains([]string{"id", "name", "version", "runtime", "compatibility", "capabilities", "dependencies", "permissions", "config", "config_schema"}, key) {
				return nil, ErrDirectiveRuntimeUnavailable
			}
		}
		seen[id] = true
	}
	return entries, nil
}
func (s *server) reconcilePluginConfiguration(ctx context.Context, config PluginConfiguration) (bool, error) {
	data, status, err := s.pluginRequest(ctx, "POST", "/reconcile", config)
	if err != nil || status != 200 {
		return false, ErrDirectiveRuntimeUnavailable
	}
	var result struct {
		Applied  bool `json:"applied"`
		Revision int  `json:"revision"`
	}
	if strictPluginJSON(data, &result) != nil || result.Revision < 0 || result.Revision > config.Revision || result.Applied && result.Revision != config.Revision {
		return false, ErrDirectiveRuntimeUnavailable
	}
	return result.Applied, nil
}
func (s *server) ensurePlugins(ctx context.Context) error {
	s.pluginMu.Lock()
	defer s.pluginMu.Unlock()
	config, err := s.store.PluginConfiguration(ctx)
	if err != nil {
		return err
	}
	// No public configuration has ever been written; the trusted build starts inactive.
	if config.Revision == 1 && len(config.Settings) == 0 {
		return nil
	}
	_, err = s.reconcilePluginConfiguration(ctx, config)
	// A failed plugin remains visible; independent core runs can still execute.
	// The runtime blocks new runs if an old active configuration is awaiting removal.
	return err
}
func (s *server) pluginRoutes(r chi.Router) {
	r.With(requireScope("plugins:read")).Get("/v1/plugins", s.plugins)
	r.With(requireScope("plugins:write")).Put("/v1/plugins/{id}", s.configurePlugin)
	r.With(requireScope("plugins:write")).Delete("/v1/plugins/{id}", s.configurePlugin)
	r.With(requireScope("plugins:read")).Get("/v1/plugins/{id}/health", s.pluginHealth)
}
func (s *server) plugins(w http.ResponseWriter, r *http.Request) {
	s.pluginMu.Lock()
	defer s.pluginMu.Unlock()
	config, err := s.store.PluginConfiguration(r.Context())
	if err != nil {
		storeError(w, err)
		return
	}
	applied, err := s.reconcilePluginConfiguration(r.Context(), config)
	// Invalid/stale desired state remains inspectable so an administrator can repair it.
	if err != nil {
		applied = false
	}
	catalog, err := s.runtimePlugins(r.Context())
	if err != nil {
		storeError(w, err)
		return
	}
	desired := map[string]bool{}
	for id, item := range config.Settings {
		desired[id] = item.Enabled
	}
	w.Header().Set("ETag", etag(config.Revision))
	respond(w, 200, map[string]any{"revision": config.Revision, "applied": applied, "plugins": catalog, "desired": desired})
}
func pluginExpected(w http.ResponseWriter, r *http.Request) (int, bool) {
	header := r.Header.Get("If-Match")
	if header == "" {
		problem(w, 428, "if_match_required")
		return 0, false
	}
	number, err := strconv.Unquote(header)
	if err != nil {
		problem(w, 422, "invalid_if_match")
		return 0, false
	}
	expected, err := strconv.Atoi(number)
	if err != nil || expected < 1 || number != strconv.Itoa(expected) {
		problem(w, 422, "invalid_if_match")
		return 0, false
	}
	return expected, true
}
func (s *server) configurePlugin(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if len(id) > 200 || !pluginIDPattern.MatchString(id) {
		problem(w, 422, "invalid_plugin_id")
		return
	}
	expected, ok := pluginExpected(w, r)
	if !ok {
		return
	}
	var body struct {
		Enabled *bool           `json:"enabled"`
		Config  json.RawMessage `json:"config"`
	}
	if r.Method != "DELETE" {
		if !decode(w, r, &body) {
			return
		}
		if body.Enabled == nil || !validPluginSettings(map[string]PluginSetting{id: {Enabled: *body.Enabled, Config: body.Config}}) {
			problem(w, 422, "invalid_plugin_configuration")
			return
		}
	}
	s.pluginMu.Lock()
	defer s.pluginMu.Unlock()
	config, err := s.store.PluginConfiguration(r.Context())
	if err != nil {
		storeError(w, err)
		return
	}
	if config.Revision != expected {
		storeError(w, ErrPreconditionFailed)
		return
	}
	if r.Method == "DELETE" {
		if _, exists := config.Settings[id]; !exists {
			storeError(w, ErrNotFound)
			return
		}
		delete(config.Settings, id)
	} else {
		config.Settings[id] = PluginSetting{Enabled: *body.Enabled, Config: body.Config}
	}
	if !validPluginSettings(config.Settings) {
		problem(w, 422, "invalid_plugin_configuration")
		return
	}
	_, status, err := s.pluginRequest(r.Context(), "POST", "/validate", config)
	if err != nil || status != 204 {
		if status == 422 {
			storeError(w, ErrInvalidConfig)
		} else {
			storeError(w, ErrDirectiveRuntimeUnavailable)
		}
		return
	}
	config, err = s.store.UpdatePluginConfiguration(r.Context(), expected, config.Settings)
	if err != nil {
		storeError(w, err)
		return
	}
	applied, applyErr := s.reconcilePluginConfiguration(r.Context(), config)
	w.Header().Set("ETag", etag(config.Revision))
	status = 200
	if applyErr != nil || !applied {
		status = 202
	}
	respond(w, status, map[string]any{"revision": config.Revision, "applied": applied && applyErr == nil})
}
func (s *server) pluginHealth(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if len(id) > 200 || !pluginIDPattern.MatchString(id) {
		problem(w, 422, "invalid_plugin_id")
		return
	}
	if err := s.ensurePlugins(r.Context()); err != nil && !errors.Is(err, ErrDirectiveRuntimeUnavailable) {
		storeError(w, err)
		return
	}
	data, status, err := s.pluginRequest(r.Context(), "GET", "/"+id+"/health", nil)
	var health struct {
		Status string `json:"status"`
	}
	if err != nil || status != 200 || strictPluginJSON(data, &health) != nil || !slices.Contains([]string{"unknown", "ok", "degraded", "unavailable"}, health.Status) {
		storeError(w, ErrDirectiveRuntimeUnavailable)
		return
	}
	respond(w, 200, health)
}
