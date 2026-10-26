package uai

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"
)

const maxErrorBody = 1 << 20

type Client struct {
	BaseURL    string
	APIKey     string
	HTTPClient *http.Client
	Headers    http.Header
}

type Option func(*Client) error

func WithHTTPClient(client *http.Client) Option {
	return func(c *Client) error {
		if client == nil {
			return &ValidationError{Message: "HTTP client is required"}
		}
		c.HTTPClient = client
		return nil
	}
}

func WithHeader(name, value string) Option {
	return func(c *Client) error {
		c.Headers.Set(name, value)
		return nil
	}
}

func New(baseURL, apiKey string, options ...Option) (*Client, error) {
	if strings.TrimSpace(baseURL) == "" {
		return nil, &ValidationError{Message: "base URL is required"}
	}
	if strings.TrimSpace(apiKey) == "" {
		return nil, &ValidationError{Message: "API key is required"}
	}
	parsed, err := url.Parse(baseURL)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, &ValidationError{Message: "base URL must be absolute"}
	}
	client := &Client{
		BaseURL:    strings.TrimRight(baseURL, "/"),
		APIKey:     apiKey,
		HTTPClient: &http.Client{},
		Headers:    make(http.Header),
	}
	for _, option := range options {
		if err := option(client); err != nil {
			return nil, err
		}
	}
	return client, nil
}

func (c *Client) Health(ctx context.Context) (*Health, error) {
	var out Health
	if err := c.doJSON(ctx, "health", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) Me(ctx context.Context) (*PrincipalInfo, error) {
	var out PrincipalInfo
	if err := c.doJSON(ctx, "me", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ListAssistants(ctx context.Context) ([]Assistant, error) {
	var out []Assistant
	if err := c.doJSON(ctx, "listAssistants", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) CreateAssistant(ctx context.Context, input AssistantInput) (*Assistant, error) {
	var out Assistant
	if err := c.doJSON(ctx, "createAssistant", nil, nil, input, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) GetAssistant(ctx context.Context, id string) (*Assistant, error) {
	var out Assistant
	if err := c.doJSON(ctx, "getAssistant", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) UpdateAssistant(ctx context.Context, id string, patch AssistantPatch, ifMatch string) (*Assistant, error) {
	var out Assistant
	headers := make(http.Header)
	headers.Set("If-Match", ifMatch)
	if err := c.doJSON(ctx, "updateAssistant", pathID(id), nil, patch, &out, headers); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ListAssistantVersions(ctx context.Context, id string) ([]Assistant, error) {
	var out []Assistant
	if err := c.doJSON(ctx, "listAssistantVersions", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) CreateConversation(ctx context.Context, input ConversationInput) (*Conversation, error) {
	var out Conversation
	if err := c.doJSON(ctx, "createConversation", nil, nil, input, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) DeleteConversation(ctx context.Context, conversationID string) error {
	return c.doJSON(ctx, "deleteConversation", pathID(conversationID), nil, nil, nil, nil)
}

func (c *Client) GetMessages(ctx context.Context, conversationID string) ([]Message, error) {
	var out []Message
	if err := c.doJSON(ctx, "getMessages", pathID(conversationID), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) SendMessage(ctx context.Context, conversationID string, input MessageInput, idempotencyKey string) (*MessageStream, error) {
	if strings.TrimSpace(idempotencyKey) == "" {
		return nil, &ValidationError{Message: "Idempotency-Key is required for sendMessage"}
	}
	payload, err := json.Marshal(input)
	if err != nil {
		return nil, &ValidationError{Message: "message input cannot be encoded"}
	}
	headers := make(http.Header)
	headers.Set("Idempotency-Key", idempotencyKey)
	headers.Set("Accept", "text/event-stream")
	response, err := c.do(ctx, Operations["sendMessage"], pathID(conversationID), nil, payload, "application/json", headers)
	if err != nil {
		return nil, err
	}
	contentType := response.Header.Get("Content-Type")
	if !strings.HasPrefix(strings.ToLower(contentType), "text/event-stream") {
		response.Body.Close()
		return nil, &StreamProtocolError{Message: "gateway did not return an SSE stream"}
	}
	runID := response.Header.Get("X-Run-ID")
	if runID == "" {
		response.Body.Close()
		return nil, &StreamProtocolError{Message: "gateway did not return X-Run-ID"}
	}
	assistantVersion, _ := strconv.Atoi(response.Header.Get("X-Assistant-Version"))

	stream := &MessageStream{
		RunID:            runID,
		AssistantVersion: assistantVersion,
		client:           c,
		ctx:              ctx,
		body:             response.Body,
		decoder:          &SSEDecoder{},
		done:             make(chan struct{}),
	}
	go func() {
		select {
		case <-ctx.Done():
			stream.cancelRun()
		case <-stream.done:
		}
	}()
	return stream, nil
}

func (c *Client) ListCredentials(ctx context.Context) ([]Credential, error) {
	var out []Credential
	if err := c.doJSON(ctx, "listCredentials", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) CreateCredential(ctx context.Context, input CredentialInput) (*CredentialSecret, error) {
	var out CredentialSecret
	if err := c.doJSON(ctx, "createCredential", nil, nil, input, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) RotateCredential(ctx context.Context, id string, input CredentialRotation) (*CredentialSecret, error) {
	var out CredentialSecret
	if err := c.doJSON(ctx, "rotateCredential", pathID(id), nil, input, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) RevokeCredential(ctx context.Context, id string) (map[string]string, error) {
	var out map[string]string
	if err := c.doJSON(ctx, "revokeCredential", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) ListModels(ctx context.Context) ([]ModelDefinition, error) {
	var out []ModelDefinition
	if err := c.doJSON(ctx, "listModels", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) ListTools(ctx context.Context) ([]ToolDefinition, error) {
	var out []ToolDefinition
	if err := c.doJSON(ctx, "listTools", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) ListPlugins(ctx context.Context) (*PluginCatalog, error) {
	var out PluginCatalog
	if err := c.doJSON(ctx, "listPlugins", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ConfigurePlugin(ctx context.Context, id string, setting PluginSetting, ifMatch string) (*PluginUpdate, error) {
	var out PluginUpdate
	headers := make(http.Header)
	headers.Set("If-Match", ifMatch)
	if err := c.doJSON(ctx, "configurePlugin", pathID(id), nil, setting, &out, headers); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) RemovePluginConfiguration(ctx context.Context, id, ifMatch string) (*PluginUpdate, error) {
	var out PluginUpdate
	headers := make(http.Header)
	headers.Set("If-Match", ifMatch)
	if err := c.doJSON(ctx, "removePluginConfiguration", pathID(id), nil, nil, &out, headers); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) PluginHealth(ctx context.Context, id string) (*PluginHealth, error) {
	var out PluginHealth
	if err := c.doJSON(ctx, "pluginHealth", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ListKnowledgeBases(ctx context.Context) ([]KnowledgeBase, error) {
	var out []KnowledgeBase
	if err := c.doJSON(ctx, "listKnowledgeBases", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) CreateKnowledgeBase(ctx context.Context, input KnowledgeBaseInput) (*KnowledgeBase, error) {
	var out KnowledgeBase
	if err := c.doJSON(ctx, "createKnowledgeBase", nil, nil, input, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) GetKnowledgeBase(ctx context.Context, id string) (*KnowledgeBase, error) {
	var out KnowledgeBase
	if err := c.doJSON(ctx, "getKnowledgeBase", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) UpdateKnowledgeBase(ctx context.Context, id string, patch KnowledgeBasePatch, ifMatch string) (*KnowledgeBase, error) {
	var out KnowledgeBase
	headers := make(http.Header)
	headers.Set("If-Match", ifMatch)
	if err := c.doJSON(ctx, "updateKnowledgeBase", pathID(id), nil, patch, &out, headers); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) DeleteKnowledgeBase(ctx context.Context, id, ifMatch string) error {
	headers := make(http.Header)
	headers.Set("If-Match", ifMatch)
	return c.doJSON(ctx, "deleteKnowledgeBase", pathID(id), nil, nil, nil, headers)
}

func (c *Client) ListKnowledgeBaseVersions(ctx context.Context, id string) ([]KnowledgeBaseVersion, error) {
	var out []KnowledgeBaseVersion
	if err := c.doJSON(ctx, "listKnowledgeBaseVersions", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) CreateKnowledgeBaseVersion(ctx context.Context, id string, input KnowledgeBaseVersionInput, ifMatch string) (*KnowledgeBaseVersion, error) {
	var out KnowledgeBaseVersion
	headers := make(http.Header)
	headers.Set("If-Match", ifMatch)
	if err := c.doJSON(ctx, "createKnowledgeBaseVersion", pathID(id), nil, input, &out, headers); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ExportKnowledgeBase(ctx context.Context, id string) (*KnowledgeBaseExport, error) {
	var out KnowledgeBaseExport
	if err := c.doJSON(ctx, "exportKnowledgeBase", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ListDocuments(ctx context.Context, knowledgeBaseID string) ([]Document, error) {
	var query url.Values
	if knowledgeBaseID != "" {
		query = url.Values{"knowledge_base_id": []string{knowledgeBaseID}}
	}
	var out []Document
	if err := c.doJSON(ctx, "listDocuments", nil, query, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) UploadDocument(ctx context.Context, input DocumentUpload) (*Document, error) {
	if input.File == nil {
		return nil, &ValidationError{Message: "document file is required"}
	}
	if strings.TrimSpace(input.KnowledgeBaseID) == "" {
		return nil, &ValidationError{Message: "knowledge base id is required"}
	}
	var buffer bytes.Buffer
	writer := multipart.NewWriter(&buffer)
	if err := writer.WriteField("knowledge_base_id", input.KnowledgeBaseID); err != nil {
		return nil, &ValidationError{Message: "cannot encode multipart request"}
	}
	if input.Title != "" {
		if err := writer.WriteField("title", input.Title); err != nil {
			return nil, &ValidationError{Message: "cannot encode multipart request"}
		}
	}
	filename := input.Filename
	if filename == "" {
		filename = "document"
	}
	part, err := writer.CreateFormFile("file", filename)
	if err != nil {
		return nil, &ValidationError{Message: "cannot encode multipart file"}
	}
	if _, err := io.Copy(part, input.File); err != nil {
		return nil, &NetworkError{Err: err}
	}
	if err := writer.Close(); err != nil {
		return nil, &ValidationError{Message: "cannot close multipart request"}
	}
	response, err := c.do(ctx, Operations["uploadDocument"], nil, nil, buffer.Bytes(), writer.FormDataContentType(), nil)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	var out Document
	if err := json.NewDecoder(io.LimitReader(response.Body, 8<<20)).Decode(&out); err != nil {
		return nil, &ResponseError{Message: "invalid document response", Err: err}
	}
	return &out, nil
}

func (c *Client) GetDocument(ctx context.Context, id string) (*Document, error) {
	var out Document
	if err := c.doJSON(ctx, "getDocument", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) DeleteDocument(ctx context.Context, id string) error {
	return c.doJSON(ctx, "deleteDocument", pathID(id), nil, nil, nil, nil)
}

func (c *Client) GetDocumentJob(ctx context.Context, id string) (*DocumentJob, error) {
	var out DocumentJob
	if err := c.doJSON(ctx, "getDocumentJob", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) CancelDocumentJob(ctx context.Context, id string) (*DocumentJob, error) {
	var out DocumentJob
	if err := c.doJSON(ctx, "cancelDocumentJob", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ListAgentRuns(ctx context.Context) ([]AgentRun, error) {
	var out []AgentRun
	if err := c.doJSON(ctx, "listAgentRuns", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) GetAgentRun(ctx context.Context, id string) (*AgentRun, error) {
	var out AgentRun
	if err := c.doJSON(ctx, "getAgentRun", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) CancelAgentRun(ctx context.Context, id string) (*AgentRun, error) {
	var out AgentRun
	if err := c.doJSON(ctx, "cancelAgentRun", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ListApprovals(ctx context.Context) ([]Approval, error) {
	var out []Approval
	if err := c.doJSON(ctx, "listApprovals", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) GetApproval(ctx context.Context, id string) (*Approval, error) {
	var out Approval
	if err := c.doJSON(ctx, "getApproval", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) ApproveApproval(ctx context.Context, id string) (*Approval, error) {
	var out Approval
	if err := c.doJSON(ctx, "approveApproval", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) RejectApproval(ctx context.Context, id string) (*Approval, error) {
	var out Approval
	if err := c.doJSON(ctx, "rejectApproval", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) CreateWidgetToken(ctx context.Context, input WidgetTokenInput) (*WidgetToken, error) {
	var out WidgetToken
	if err := c.doJSON(ctx, "createWidgetToken", nil, nil, input, &out, nil); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) RevokeWidgetToken(ctx context.Context, id string) (map[string]string, error) {
	var out map[string]string
	if err := c.doJSON(ctx, "revokeWidgetToken", pathID(id), nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) ListAuditEvents(ctx context.Context) ([]AuditEvent, error) {
	var out []AuditEvent
	if err := c.doJSON(ctx, "listAuditEvents", nil, nil, nil, &out, nil); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) doJSON(ctx context.Context, operationID string, params map[string]string, query url.Values, body any, out any, headers http.Header) error {
	operation, ok := Operations[operationID]
	if !ok {
		return &ValidationError{Message: "unknown operation " + operationID}
	}
	var payload []byte
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return &ValidationError{Message: "request body cannot be encoded"}
		}
		payload = encoded
	}
	response, err := c.do(ctx, operation, params, query, payload, contentTypeFor(payload), headers)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if out == nil {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
		return nil
	}
	if response.StatusCode == http.StatusNoContent {
		return nil
	}
	if err := json.NewDecoder(io.LimitReader(response.Body, 16<<20)).Decode(out); err != nil {
		return &ResponseError{Message: "invalid JSON response", Err: err}
	}
	return nil
}

func (c *Client) do(ctx context.Context, operation Operation, params map[string]string, query url.Values, body []byte, contentType string, headers http.Header) (*http.Response, error) {
	if headers == nil {
		headers = make(http.Header)
	}
	if operation.RequiresIdempotencyKey && strings.TrimSpace(headers.Get("Idempotency-Key")) == "" {
		return nil, &ValidationError{Message: "Idempotency-Key is required for " + operation.Method + " " + operation.Path}
	}
	if operation.RequiresIfMatch && strings.TrimSpace(headers.Get("If-Match")) == "" {
		return nil, &ValidationError{Message: "If-Match is required for " + operation.Method + " " + operation.Path}
	}
	path := operation.Path
	for name, value := range params {
		path = strings.ReplaceAll(path, "{"+name+"}", url.PathEscape(value))
	}
	if strings.Contains(path, "{") {
		return nil, &ValidationError{Message: "missing path parameter for " + operation.Path}
	}
	target := c.BaseURL + path
	if len(query) > 0 {
		target += "?" + query.Encode()
	}
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	request, err := http.NewRequestWithContext(ctx, operation.Method, target, reader)
	if err != nil {
		return nil, &ValidationError{Message: "cannot build request"}
	}
	requestHeaders := c.Headers.Clone()
	requestHeaders.Set("Authorization", "Bearer "+c.APIKey)
	if requestHeaders.Get("Accept") == "" {
		requestHeaders.Set("Accept", "application/json")
	}
	if contentType != "" {
		requestHeaders.Set("Content-Type", contentType)
	}
	for name, values := range headers {
		for _, value := range values {
			requestHeaders.Set(name, value)
		}
	}
	request.Header = requestHeaders

	response, err := c.HTTPClient.Do(request)
	if err != nil {
		if ctx.Err() != nil {
			if errors.Is(ctx.Err(), context.DeadlineExceeded) {
				return nil, &TimeoutError{Err: ctx.Err()}
			}
			return nil, &AbortError{Err: ctx.Err()}
		}
		if errors.Is(err, context.DeadlineExceeded) {
			return nil, &TimeoutError{Err: err}
		}
		return nil, &NetworkError{Err: err}
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		defer response.Body.Close()
		raw, _ := io.ReadAll(io.LimitReader(response.Body, maxErrorBody))
		code := "http_" + strconv.Itoa(response.StatusCode)
		var payload ErrorResponse
		if json.Unmarshal(raw, &payload) == nil && payload.Error != "" {
			code = payload.Error
		}
		return nil, &APIError{Status: response.StatusCode, Code: code, Body: string(raw)}
	}
	return response, nil
}

func contentTypeFor(payload []byte) string {
	if payload == nil {
		return ""
	}
	return "application/json"
}

func pathID(id string) map[string]string {
	return map[string]string{"id": id}
}

type MessageStream struct {
	RunID            string
	AssistantVersion int

	client  *Client
	ctx     context.Context
	body    io.ReadCloser
	decoder *SSEDecoder
	pending []SSEEvent
	done    chan struct{}

	terminal   bool
	closed     bool
	closeOnce  sync.Once
	cancelOnce sync.Once
}

func (s *MessageStream) Next() (RuntimeEvent, error) {
	if s.terminal {
		return RuntimeEvent{}, io.EOF
	}
	if s.closed {
		return RuntimeEvent{}, io.EOF
	}
	for len(s.pending) == 0 {
		buffer := make([]byte, 32*1024)
		count, err := s.body.Read(buffer)
		if count > 0 {
			s.pending = append(s.pending, s.decoder.Push(buffer[:count])...)
		}
		if len(s.pending) > 0 {
			break
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				s.pending = append(s.pending, s.decoder.End()...)
				if len(s.pending) == 0 {
					s.finish()
					return RuntimeEvent{}, &StreamIncompleteError{RunID: s.RunID}
				}
				break
			}
			if s.ctx.Err() != nil {
				s.cancelRun()
			}
			s.finish()
			return RuntimeEvent{}, s.readError(err)
		}
	}
	raw := s.pending[0]
	s.pending = s.pending[1:]
	event, err := parseRuntimeEvent(raw)
	if err != nil {
		s.finish()
		return RuntimeEvent{}, err
	}
	switch event.EventType {
	case "response.completed":
		s.finish()
		return event, nil
	case "agent.failed":
		var payload FailurePayload
		_ = event.DecodePayload(&payload)
		s.finish()
		return event, &AgentFailedError{Event: event, Code: payload.Code}
	case "agent.cancelled":
		var payload CancelledPayload
		_ = event.DecodePayload(&payload)
		if payload.Code == "" {
			payload.Code = "cancelled"
		}
		s.finish()
		return event, &AgentCancelledError{Event: event, Code: payload.Code}
	}
	return event, nil
}

func (s *MessageStream) Close() error {
	s.finish()
	return nil
}

func (s *MessageStream) finish() {
	s.terminal = true
	s.closeOnce.Do(func() {
		s.closed = true
		_ = s.body.Close()
		close(s.done)
	})
}

func (s *MessageStream) readError(err error) error {
	if s.ctx.Err() != nil {
		if errors.Is(s.ctx.Err(), context.DeadlineExceeded) {
			return &TimeoutError{Err: s.ctx.Err()}
		}
		return &AbortError{Err: s.ctx.Err()}
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return &TimeoutError{Err: err}
	}
	return &NetworkError{Err: err}
}

func (s *MessageStream) cancelRun() {
	s.cancelOnce.Do(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		response, err := s.client.do(ctx, Operations["cancelAgentRun"], pathID(s.RunID), nil, nil, "", nil)
		if err == nil && response != nil {
			response.Body.Close()
		}
	})
}

func parseRuntimeEvent(raw SSEEvent) (RuntimeEvent, error) {
	var event RuntimeEvent
	if err := json.Unmarshal([]byte(raw.Data), &event); err != nil {
		return RuntimeEvent{}, &StreamProtocolError{Message: "SSE data is not valid JSON", Err: err}
	}
	switch event.EventType {
	case "agent.started", "response.delta", "response.completed", "agent.failed", "agent.cancelled":
	default:
		return RuntimeEvent{}, &StreamProtocolError{Message: "unknown SSE event_type"}
	}
	if raw.Event != "" && raw.Event != event.EventType {
		return RuntimeEvent{}, &StreamProtocolError{Message: "SSE event name does not match event_type"}
	}
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(event.Payload, &payload); err != nil || payload == nil {
		return RuntimeEvent{}, &StreamProtocolError{Message: "SSE payload must be an object"}
	}
	switch event.EventType {
	case "response.delta", "response.completed":
		var text string
		if err := json.Unmarshal(payload["text"], &text); err != nil {
			return RuntimeEvent{}, &StreamProtocolError{Message: "SSE payload.text is required"}
		}
	case "agent.failed":
		var code string
		if err := json.Unmarshal(payload["code"], &code); err != nil || code == "" {
			return RuntimeEvent{}, &StreamProtocolError{Message: "SSE payload.code is required"}
		}
	case "agent.cancelled":
		if rawCode, ok := payload["code"]; ok {
			var code string
			if err := json.Unmarshal(rawCode, &code); err != nil {
				return RuntimeEvent{}, &StreamProtocolError{Message: "SSE payload.code must be a string"}
			}
		}
	}
	return event, nil
}

func (c *Client) String() string {
	return fmt.Sprintf("uai.Client(%s)", c.BaseURL)
}
