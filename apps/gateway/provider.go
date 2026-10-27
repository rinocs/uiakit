package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

var providerSecretRef = regexp.MustCompile(`^(MODEL_API_KEY|PROVIDER_API_KEY_[A-Z0-9_]{1,63})$`)

type ProviderModel struct {
	ID            string   `json:"id"`
	Capabilities  []string `json:"capabilities"`
	ContextWindow *int     `json:"context_window"`
}

type ProviderConfiguration struct {
	Revision        int             `json:"revision"`
	Provider        string          `json:"provider"`
	BaseURL         string          `json:"base_url"`
	APIKeyRef       string          `json:"api_key_ref"`
	MaxOutputTokens int             `json:"max_output_tokens"`
	Models          []ProviderModel `json:"models"`
}

type ProviderView struct {
	Revision         int               `json:"revision"`
	Managed          bool              `json:"managed"`
	Applied          bool              `json:"applied"`
	Provider         string            `json:"provider"`
	BaseURL          string            `json:"base_url"`
	APIKeyRef        string            `json:"api_key_ref"`
	APIKeyConfigured bool              `json:"api_key_configured"`
	MaxOutputTokens  int               `json:"max_output_tokens"`
	Models           []ModelDefinition `json:"models"`
}

type ProviderUpdate struct {
	Provider        string          `json:"provider"`
	BaseURL         string          `json:"base_url"`
	APIKeyRef       string          `json:"api_key_ref"`
	MaxOutputTokens int             `json:"max_output_tokens"`
	Models          []ProviderModel `json:"models"`
}

type ProviderDiscovery struct {
	Provider  string `json:"provider"`
	BaseURL   string `json:"base_url"`
	APIKeyRef string `json:"api_key_ref"`
}

type ProviderModelList struct {
	Models []string `json:"models"`
}

type runtimeProviderState struct {
	Revision         int                      `json:"revision"`
	Provider         string                   `json:"provider"`
	BaseURL          string                   `json:"base_url"`
	APIKeyRef        string                   `json:"api_key_ref"`
	APIKeyConfigured bool                     `json:"api_key_configured"`
	MaxOutputTokens  int                      `json:"max_output_tokens"`
	Models           []ModelDefinition        `json:"models"`
	Profiles         []providerRuntimeProfile `json:"profiles,omitempty"`
}

type providerRuntimeConfig struct {
	Revision        int             `json:"revision"`
	Provider        string          `json:"provider"`
	BaseURL         string          `json:"base_url"`
	APIKeyRef       string          `json:"api_key_ref"`
	MaxOutputTokens int             `json:"max_output_tokens"`
	Models          []ProviderModel `json:"models"`
}

func validProviderKind(value string) bool {
	return value == "openai-compatible" || value == "ollama"
}

func validProviderBaseURL(value string) bool {
	if value == "" || len(value) > 2000 {
		return false
	}
	parsed, err := url.Parse(value)
	return err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") &&
		parsed.Host != "" && parsed.User == nil && parsed.RawQuery == "" && parsed.Fragment == ""
}

func validProviderSecretRef(value string) bool {
	return value == "" || providerSecretRef.MatchString(value)
}

func validModelID(value string) bool {
	if value == "" || len(value) > 200 || value != strings.TrimSpace(value) {
		return false
	}
	for _, char := range value {
		if char < 0x20 || char == 0x7f {
			return false
		}
	}
	return true
}

func validProviderConfiguration(config ProviderConfiguration) bool {
	if !validProviderKind(config.Provider) || !validProviderBaseURL(config.BaseURL) ||
		!validProviderSecretRef(config.APIKeyRef) || config.MaxOutputTokens < 1 ||
		config.MaxOutputTokens > 8192 || len(config.Models) < 1 || len(config.Models) > 50 {
		return false
	}
	if config.Provider == "ollama" && config.APIKeyRef != "" {
		return false
	}
	seen := map[string]bool{}
	for _, model := range config.Models {
		if !validModelID(model.ID) || seen[model.ID] {
			return false
		}
		seen[model.ID] = true
		if model.ContextWindow != nil && *model.ContextWindow < 1 {
			return false
		}
		caps := map[string]bool{}
		for _, capability := range model.Capabilities {
			if capability != "tool_calling" && capability != "structured_output" || caps[capability] {
				return false
			}
			if config.Provider == "ollama" {
				return false
			}
			caps[capability] = true
		}
	}
	return true
}

func validProviderDiscovery(discovery ProviderDiscovery) bool {
	if !validProviderKind(discovery.Provider) || !validProviderBaseURL(discovery.BaseURL) ||
		!validProviderSecretRef(discovery.APIKeyRef) {
		return false
	}
	return discovery.Provider != "ollama" || discovery.APIKeyRef == ""
}

func providerDefinitions(config ProviderConfiguration) []ModelDefinition {
	definitions := make([]ModelDefinition, 0, len(config.Models))
	maxTokens := config.MaxOutputTokens
	for _, model := range config.Models {
		capabilities := append([]string{"chat", "streaming"}, model.Capabilities...)
		sort.Strings(capabilities)
		definitions = append(definitions, ModelDefinition{
			ID: model.ID, Provider: config.Provider, Capabilities: capabilities,
			MaxOutputTokens: &maxTokens, ContextWindow: model.ContextWindow,
		})
	}
	sort.Slice(definitions, func(i, j int) bool { return definitions[i].ID < definitions[j].ID })
	return definitions
}

func runtimeProviderConfig(config ProviderConfiguration) providerRuntimeConfig {
	return providerRuntimeConfig{
		Revision: config.Revision, Provider: config.Provider, BaseURL: config.BaseURL,
		APIKeyRef: config.APIKeyRef, MaxOutputTokens: config.MaxOutputTokens,
		Models: config.Models,
	}
}

func providerView(config ProviderConfiguration, state *runtimeProviderState, managed bool) ProviderView {
	view := ProviderView{
		Revision: config.Revision, Managed: managed, Applied: false,
		Provider: config.Provider, BaseURL: config.BaseURL, APIKeyRef: config.APIKeyRef,
		MaxOutputTokens: config.MaxOutputTokens, Models: providerDefinitions(config),
	}
	if state != nil {
		view.APIKeyConfigured = state.APIKeyConfigured
		view.Applied = !managed || state.Revision == config.Revision
	}
	if !managed {
		view.Provider, view.BaseURL, view.APIKeyRef = state.Provider, state.BaseURL, state.APIKeyRef
		view.MaxOutputTokens, view.Models = state.MaxOutputTokens, state.Models
	}
	return view
}

func (s *server) runtimeProviderRequest(ctx context.Context, method, path string,
	body any) (int, []byte, error) {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return 0, nil, err
		}
		reader = bytes.NewReader(data)
	}
	request, err := http.NewRequestWithContext(ctx, method, s.config.RuntimeURL+path, reader)
	if err != nil {
		return 0, nil, err
	}
	request.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	client := &http.Client{Timeout: 20 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(request)
	if err != nil {
		return 0, nil, err
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	return response.StatusCode, data, err
}

func fetchRuntimeProviderState(ctx context.Context, s *server) (runtimeProviderState, error) {
	status, data, err := s.runtimeProviderRequest(ctx, "GET", "/internal/v1/provider/state", nil)
	if err != nil {
		return runtimeProviderState{}, err
	}
	if status != 200 {
		return runtimeProviderState{}, errors.New("provider_state_unavailable")
	}
	var state runtimeProviderState
	err = json.Unmarshal(data, &state)
	return state, err
}

func runtimeErrorCode(data []byte) string {
	var body struct {
		Detail string `json:"detail"`
	}
	if json.Unmarshal(data, &body) == nil && body.Detail != "" {
		return body.Detail
	}
	return "runtime_error"
}

func (s *server) syncRuntimeModels(ctx context.Context) error {
	models, err := loadRuntimeModels(ctx, s.config)
	if err != nil {
		return err
	}
	return s.store.SyncModels(ctx, models)
}

func (s *server) applySavedProvider(ctx context.Context) error {
	config, err := s.store.ProviderConfiguration(ctx)
	if errors.Is(err, ErrNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	status, data, err := s.runtimeProviderRequest(ctx, "POST", "/internal/v1/provider/apply",
		runtimeProviderConfig(config))
	if err != nil {
		return err
	}
	if status != 200 {
		return errors.New(runtimeErrorCode(data))
	}
	return nil
}

func providerExpected(w http.ResponseWriter, r *http.Request) (int, bool) {
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
	if err != nil || expected < 0 || number != strconv.Itoa(expected) {
		problem(w, 422, "invalid_if_match")
		return 0, false
	}
	return expected, true
}

func removedModelInUse(ctx context.Context, s *server, current, next []ProviderModel) (string, error) {
	keep := map[string]bool{}
	for _, model := range next {
		keep[model.ID] = true
	}
	for _, model := range current {
		if keep[model.ID] {
			continue
		}
		count, err := s.store.AssistantsUsingModel(ctx, model.ID)
		if err != nil {
			return "", err
		}
		if count > 0 {
			return model.ID, nil
		}
	}
	return "", nil
}

func (s *server) provider(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	config, err := s.store.ProviderConfiguration(ctx)
	if errors.Is(err, ErrNotFound) {
		state, err := fetchRuntimeProviderState(ctx, s)
		if err != nil {
			problem(w, 503, "runtime_unavailable")
			return
		}
		w.Header().Set("ETag", etag(0))
		respond(w, 200, providerView(ProviderConfiguration{}, &state, false))
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	var state *runtimeProviderState
	if current, err := fetchRuntimeProviderState(ctx, s); err == nil {
		state = &current
	}
	w.Header().Set("ETag", etag(config.Revision))
	respond(w, 200, providerView(config, state, true))
}

func (s *server) updateProvider(w http.ResponseWriter, r *http.Request) {
	expected, ok := providerExpected(w, r)
	if !ok {
		return
	}
	var body ProviderUpdate
	if !decode(w, r, &body) {
		return
	}
	next := ProviderConfiguration{
		Provider: body.Provider, BaseURL: body.BaseURL, APIKeyRef: body.APIKeyRef,
		MaxOutputTokens: body.MaxOutputTokens, Models: body.Models,
	}
	if !validProviderConfiguration(next) {
		problem(w, 422, "invalid_configuration")
		return
	}
	ctx := r.Context()
	current, err := s.store.ProviderConfiguration(ctx)
	var currentModels []ProviderModel
	switch {
	case errors.Is(err, ErrNotFound):
		state, stateErr := fetchRuntimeProviderState(ctx, s)
		if stateErr != nil {
			problem(w, 503, "runtime_unavailable")
			return
		}
		for _, model := range state.Models {
			currentModels = append(currentModels, ProviderModel{ID: model.ID})
		}
	case err != nil:
		problem(w, 500, "store_error")
		return
	default:
		currentModels = current.Models
	}
	if modelID, err := removedModelInUse(ctx, s, currentModels, next.Models); err != nil {
		problem(w, 500, "store_error")
		return
	} else if modelID != "" {
		problem(w, 409, "model_in_use")
		return
	}
	next.Revision = expected + 1
	status, data, err := s.runtimeProviderRequest(ctx, "POST", "/internal/v1/provider/validate",
		runtimeProviderConfig(next))
	if err != nil {
		problem(w, 503, "runtime_unavailable")
		return
	}
	if status == 422 {
		problem(w, 422, runtimeErrorCode(data))
		return
	}
	if status != 200 {
		problem(w, 503, "runtime_unavailable")
		return
	}
	saved, err := s.store.SaveProviderConfiguration(ctx, expected, next)
	if errors.Is(err, ErrConflict) {
		problem(w, 412, "version_conflict")
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	status, data, err = s.runtimeProviderRequest(ctx, "POST", "/internal/v1/provider/apply",
		runtimeProviderConfig(saved))
	if err != nil || status != 200 {
		problem(w, 502, "provider_pending")
		return
	}
	var state runtimeProviderState
	if err := json.Unmarshal(data, &state); err != nil {
		problem(w, 502, "provider_pending")
		return
	}
	if err := s.syncRuntimeModels(ctx); err != nil {
		problem(w, 502, "provider_pending")
		return
	}
	w.Header().Set("ETag", etag(saved.Revision))
	respond(w, 200, providerView(saved, &state, true))
}

func (s *server) discoverProviderModels(w http.ResponseWriter, r *http.Request) {
	var body ProviderDiscovery
	if !decode(w, r, &body) {
		return
	}
	if !validProviderDiscovery(body) {
		problem(w, 422, "invalid_configuration")
		return
	}
	status, data, err := s.runtimeProviderRequest(r.Context(), "POST",
		"/internal/v1/provider/models", body)
	if err != nil {
		problem(w, 503, "runtime_unavailable")
		return
	}
	if status == 422 {
		problem(w, 422, runtimeErrorCode(data))
		return
	}
	if status != 200 {
		problem(w, 503, "runtime_unavailable")
		return
	}
	var found ProviderModelList
	if err := json.Unmarshal(data, &found); err != nil {
		problem(w, 502, "runtime_unavailable")
		return
	}
	if found.Models == nil {
		found.Models = []string{}
	}
	respond(w, 200, found)
}

// ProviderProfileView is the public, credential-free representation of a provider profile.
type ProviderProfileView struct {
	ID               string          `json:"id"`
	Name             string          `json:"name"`
	Provider         string          `json:"provider"`
	BaseURL          string          `json:"base_url"`
	SecretSource     string          `json:"secret_source"`
	SecretConfigured bool            `json:"secret_configured"`
	SecretReadable   bool            `json:"secret_readable"`
	MaxOutputTokens  int             `json:"max_output_tokens"`
	Revision         int             `json:"revision"`
	Applied          bool            `json:"applied"`
	Managed          bool            `json:"managed"`
	Models           []ProviderModel `json:"models"`
}

type ProviderProfileList struct {
	Profiles []ProviderProfileView `json:"profiles"`
}

type ProviderProfileInput struct {
	Name            string          `json:"name"`
	Provider        string          `json:"provider"`
	BaseURL         string          `json:"base_url"`
	MaxOutputTokens int             `json:"max_output_tokens"`
	Models          []ProviderModel `json:"models"`
}

type ProviderProfileCreate struct {
	ID string `json:"id"`
	ProviderProfileInput
}

type providerRuntimePlane struct {
	Revision int64                    `json:"revision"`
	Profiles []providerRuntimeProfile `json:"profiles"`
}

type providerRuntimeProfile struct {
	ID              string          `json:"id"`
	Name            string          `json:"name"`
	Provider        string          `json:"provider"`
	BaseURL         string          `json:"base_url"`
	APIKey          string          `json:"api_key"`
	APIKeyRef       string          `json:"api_key_ref"`
	MaxOutputTokens int             `json:"max_output_tokens"`
	Models          []ProviderModel `json:"models"`
}

var providerProfileID = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,31}$`)

func validProviderProfileInput(id, name, kind, baseURL string, maxTokens int, models []ProviderModel) bool {
	if !providerProfileID.MatchString(id) || name == "" || len(name) > 80 || name != strings.TrimSpace(name) ||
		!validProviderKind(kind) || !validProviderBaseURL(baseURL) || maxTokens < 1 || maxTokens > 8192 ||
		len(models) < 1 || len(models) > 50 {
		return false
	}
	seen := make(map[string]bool, len(models))
	for _, model := range models {
		if !validModelID(model.ID) || seen[model.ID] || len(id)+1+len(model.ID) > 200 {
			return false
		}
		seen[model.ID] = true
		if model.ContextWindow != nil && *model.ContextWindow < 1 {
			return false
		}
		caps := make(map[string]bool, len(model.Capabilities))
		for _, capability := range model.Capabilities {
			if (capability != "tool_calling" && capability != "structured_output") || caps[capability] || kind == "ollama" {
				return false
			}
			caps[capability] = true
		}
	}
	return true
}

func providerProfileValidationCode(id string, input ProviderProfileInput) string {
	if !providerProfileID.MatchString(id) {
		return "invalid_profile_id"
	}
	if !validProviderBaseURL(input.BaseURL) {
		return "invalid_provider_url"
	}
	if input.Name == "" || len(input.Name) > 80 || input.Name != strings.TrimSpace(input.Name) ||
		!validProviderKind(input.Provider) || input.MaxOutputTokens < 1 || input.MaxOutputTokens > 8192 ||
		len(input.Models) < 1 || len(input.Models) > 50 {
		return "invalid_configuration"
	}
	seen := make(map[string]bool, len(input.Models))
	for _, model := range input.Models {
		if !validModelID(model.ID) || len(id)+1+len(model.ID) > 200 {
			return "invalid_model_id"
		}
		if seen[model.ID] {
			return "duplicate_model_id"
		}
		seen[model.ID] = true
		if model.ContextWindow != nil && *model.ContextWindow < 1 {
			return "invalid_configuration"
		}
		caps := make(map[string]bool, len(model.Capabilities))
		for _, capability := range model.Capabilities {
			if (capability != "tool_calling" && capability != "structured_output") || caps[capability] || input.Provider == "ollama" {
				return "invalid_configuration"
			}
			caps[capability] = true
		}
	}
	return ""
}

func providerProfileView(profile ProviderProfile, applied int64) ProviderProfileView {
	source := "none"
	if profile.SecretCipher != nil {
		source = "stored"
	} else if profile.SecretRef != "" {
		source = "env"
	}
	return ProviderProfileView{
		ID: profile.ID, Name: profile.Name, Provider: profile.Provider, BaseURL: profile.BaseURL,
		SecretSource: source, SecretConfigured: source != "none", SecretReadable: profile.SecretCipher == nil || profile.SecretKeyVersion == providerSecretKeyVersion,
		MaxOutputTokens: profile.MaxOutputTokens, Revision: profile.Revision,
		Applied: applied >= profile.ConfigSeq, Managed: true, Models: profile.Models,
	}
}

func (s *server) providerProfileView(profile ProviderProfile, applied int64) ProviderProfileView {
	view := providerProfileView(profile, applied)
	if profile.SecretCipher != nil {
		view.SecretReadable = s.config.SecretKey != nil && profile.SecretKeyVersion == providerSecretKeyVersion
	}
	return view
}

func (s *server) runtimePlane(ctx context.Context) (providerRuntimePlane, error) {
	profiles, err := s.store.ProviderProfiles(ctx)
	if err != nil {
		return providerRuntimePlane{}, err
	}
	revision, err := s.store.ProviderAppliedRevision(ctx)
	if err != nil {
		return providerRuntimePlane{}, err
	}
	// The store's applied counter is not the desired revision. Use the greatest
	// profile config sequence so concurrent profile writes share one plane.
	for _, profile := range profiles {
		if profile.ConfigSeq > revision {
			revision = profile.ConfigSeq
		}
	}
	plane := providerRuntimePlane{Revision: revision, Profiles: make([]providerRuntimeProfile, 0, len(profiles))}
	for _, profile := range profiles {
		runtimeProfile := providerRuntimeProfile{
			ID: profile.ID, Name: profile.Name, Provider: profile.Provider, BaseURL: profile.BaseURL,
			MaxOutputTokens: profile.MaxOutputTokens, Models: profile.Models,
		}
		if profile.SecretCipher != nil {
			if s.config.SecretKey == nil {
				return providerRuntimePlane{}, errSecretUnreadable
			}
			value, openErr := s.config.SecretKey.open(profile.ID, profile.SecretCipher, profile.SecretNonce, profile.SecretKeyVersion)
			if openErr != nil {
				return providerRuntimePlane{}, errSecretUnreadable
			}
			runtimeProfile.APIKey = value
		} else {
			runtimeProfile.APIKeyRef = profile.SecretRef
		}
		plane.Profiles = append(plane.Profiles, runtimeProfile)
	}
	sort.Slice(plane.Profiles, func(i, j int) bool { return plane.Profiles[i].ID < plane.Profiles[j].ID })
	return plane, nil
}

func (s *server) applyProviderPlane(ctx context.Context) (int64, error) {
	s.providerApplyMu.Lock()
	defer s.providerApplyMu.Unlock()

	plane, err := s.runtimePlane(ctx)
	if err != nil {
		return 0, err
	}
	status, data, err := s.runtimeProviderRequest(ctx, http.MethodPost, "/internal/v1/provider/apply", plane)
	if err != nil {
		return 0, errors.New("provider_pending")
	}
	if status != http.StatusOK {
		_ = data
		return 0, errors.New("provider_pending")
	}
	if err := s.syncRuntimeModels(ctx); err != nil {
		return 0, errors.New("provider_pending")
	}
	if err := s.store.MarkProviderApplied(ctx, plane.Revision); err != nil {
		return 0, err
	}
	return plane.Revision, nil
}

func (s *server) providers(w http.ResponseWriter, r *http.Request) {
	profiles, err := s.store.ProviderProfiles(r.Context())
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	applied, err := s.store.ProviderAppliedRevision(r.Context())
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	views := make([]ProviderProfileView, 0, len(profiles))
	for _, profile := range profiles {
		views = append(views, s.providerProfileView(profile, applied))
	}
	respond(w, http.StatusOK, ProviderProfileList{Profiles: views})
}

func (s *server) createProviderProfile(w http.ResponseWriter, r *http.Request) {
	var body ProviderProfileCreate
	if !decode(w, r, &body) {
		return
	}
	input := body.ProviderProfileInput
	if code := providerProfileValidationCode(body.ID, input); code != "" {
		problem(w, 422, code)
		return
	}
	profiles, err := s.store.ProviderProfiles(r.Context())
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	if len(profiles) >= 20 {
		problem(w, 422, "too_many_profiles")
		return
	}
	saved, err := s.store.CreateProviderProfile(r.Context(), ProviderProfile{ID: body.ID, Name: input.Name,
		Provider: input.Provider, BaseURL: input.BaseURL, MaxOutputTokens: input.MaxOutputTokens, Models: input.Models})
	if errors.Is(err, ErrTooManyProfiles) {
		problem(w, 422, "too_many_profiles")
		return
	}
	if errors.Is(err, ErrConflict) {
		problem(w, 409, "version_conflict")
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	applied, err := s.applyProviderPlane(r.Context())
	if errors.Is(err, errSecretUnreadable) {
		problem(w, 502, "secret_unreadable")
		return
	}
	if err != nil && err.Error() == "provider_pending" {
		problem(w, 502, "provider_pending")
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	w.Header().Set("ETag", etag(saved.Revision))
	respond(w, http.StatusOK, s.providerProfileView(saved, applied))
}

func (s *server) providerProfile(w http.ResponseWriter, r *http.Request) {
	profile, err := s.store.ProviderProfile(r.Context(), chi.URLParam(r, "id"))
	if errors.Is(err, ErrNotFound) {
		problem(w, 404, "not_found")
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	applied, err := s.store.ProviderAppliedRevision(r.Context())
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	w.Header().Set("ETag", etag(profile.Revision))
	respond(w, http.StatusOK, s.providerProfileView(profile, applied))
}

func (s *server) updateProviderProfile(w http.ResponseWriter, r *http.Request) {
	expected, ok := providerExpected(w, r)
	if !ok {
		return
	}
	id := chi.URLParam(r, "id")
	var input ProviderProfileInput
	if !decode(w, r, &input) {
		return
	}
	if code := providerProfileValidationCode(id, input); code != "" {
		problem(w, 422, code)
		return
	}
	current, err := s.store.ProviderProfile(r.Context(), id)
	if errors.Is(err, ErrNotFound) {
		problem(w, 404, "not_found")
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	if modelID, checkErr := removedModelInUse(r.Context(), s, current.Models, input.Models); checkErr != nil {
		problem(w, 500, "store_error")
		return
	} else if modelID != "" {
		problem(w, 409, "model_in_use")
		return
	}
	saved, err := s.store.UpdateProviderProfile(r.Context(), id, expected, ProviderProfile{ID: id, Name: input.Name,
		Provider: input.Provider, BaseURL: input.BaseURL, MaxOutputTokens: input.MaxOutputTokens, Models: input.Models})
	if errors.Is(err, ErrConflict) {
		problem(w, 412, "version_conflict")
		return
	}
	if errors.Is(err, ErrNotFound) {
		problem(w, 404, "not_found")
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	applied, err := s.applyProviderPlane(r.Context())
	if err != nil {
		if errors.Is(err, errSecretUnreadable) {
			problem(w, 502, "secret_unreadable")
		} else if err.Error() == "provider_pending" {
			problem(w, 502, "provider_pending")
		} else {
			problem(w, 500, "store_error")
		}
		return
	}
	w.Header().Set("ETag", etag(saved.Revision))
	respond(w, http.StatusOK, s.providerProfileView(saved, applied))
}

func (s *server) deleteProviderProfile(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	profile, err := s.store.ProviderProfile(r.Context(), id)
	if errors.Is(err, ErrNotFound) {
		problem(w, 404, "not_found")
		return
	}
	if err != nil {
		problem(w, 500, "store_error")
		return
	}
	for _, model := range profile.Models {
		count, countErr := s.store.AssistantsUsingModel(r.Context(), id+"/"+model.ID)
		if countErr != nil {
			problem(w, 500, "store_error")
			return
		}
		if count > 0 {
			problem(w, 409, "profile_in_use")
			return
		}
	}
	if err := s.store.DeleteProviderProfile(r.Context(), id); errors.Is(err, ErrNotFound) {
		problem(w, 404, "not_found")
		return
	} else if err != nil {
		problem(w, 500, "store_error")
		return
	}
	if _, err := s.applyProviderPlane(r.Context()); err != nil {
		if errors.Is(err, errSecretUnreadable) {
			problem(w, 502, "secret_unreadable")
		} else if err.Error() == "provider_pending" {
			problem(w, 502, "provider_pending")
		} else {
			problem(w, 500, "store_error")
		}
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *server) providerRoutes(r chi.Router) {
	r.With(requireScope("providers:read")).Get("/v1/provider", s.provider)
	r.With(requireScope("providers:write")).Put("/v1/provider", s.updateProvider)
	r.With(requireScope("providers:write")).Post("/v1/provider/models", s.discoverProviderModels)
	r.With(requireScope("providers:read")).Get("/v1/providers", s.providers)
	r.With(requireScope("providers:write")).Post("/v1/providers", s.createProviderProfile)
	r.With(requireScope("providers:read")).Get("/v1/providers/{id}", s.providerProfile)
	r.With(requireScope("providers:write")).Put("/v1/providers/{id}", s.updateProviderProfile)
	r.With(requireScope("providers:write")).Delete("/v1/providers/{id}", s.deleteProviderProfile)
}

func (s *server) internalProviderRoutes(r chi.Router) {
	r.Route("/internal/v1/provider", func(r chi.Router) {
		r.Use(s.requireInternal)
		r.Get("/desired", func(w http.ResponseWriter, r *http.Request) {
			config, err := s.store.ProviderConfiguration(r.Context())
			if errors.Is(err, ErrNotFound) {
				problem(w, 404, "not_configured")
				return
			}
			if err != nil {
				problem(w, 503, "store_error")
				return
			}
			respond(w, 200, runtimeProviderConfig(config))
		})
		r.Post("/applied", func(w http.ResponseWriter, r *http.Request) {
			var body struct {
				Revision int `json:"revision"`
			}
			if !decode(w, r, &body) {
				return
			}
			if body.Revision < 1 {
				problem(w, 422, "invalid_configuration")
				return
			}
			config, err := s.store.ProviderConfiguration(r.Context())
			if errors.Is(err, ErrNotFound) {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			if err != nil {
				problem(w, 503, "store_error")
				return
			}
			if config.Revision != body.Revision {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			if err := s.syncRuntimeModels(r.Context()); err != nil {
				problem(w, 503, "catalog_unavailable")
				return
			}
			w.WriteHeader(http.StatusNoContent)
		})
	})
}
