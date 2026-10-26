package uai

import (
	"encoding/json"
	"io"
)

type Health struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

type PrincipalInfo struct {
	PrincipalID string   `json:"principal_id"`
	Role        string   `json:"role"`
	Scopes      []string `json:"scopes"`
}

type ErrorResponse struct {
	Error string `json:"error"`
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
	Memory           map[string]any  `json:"memory"`
	Limits           map[string]any  `json:"limits"`
	Policy           map[string]any  `json:"policy"`
	StructuredOutput json.RawMessage `json:"structured_output"`
}

type AssistantInput struct {
	Name             string         `json:"name"`
	Description      string         `json:"description,omitempty"`
	Model            string         `json:"model"`
	SystemPrompt     string         `json:"system_prompt"`
	Directives       []string       `json:"directives,omitempty"`
	KnowledgeBaseIDs []string       `json:"knowledge_base_ids,omitempty"`
	Memory           map[string]any `json:"memory,omitempty"`
	Limits           map[string]any `json:"limits,omitempty"`
	Policy           map[string]any `json:"policy,omitempty"`
}

type AssistantPatch struct {
	Name             *string         `json:"name,omitempty"`
	Description      *string         `json:"description,omitempty"`
	Model            *string         `json:"model,omitempty"`
	SystemPrompt     *string         `json:"system_prompt,omitempty"`
	Directives       *[]string       `json:"directives,omitempty"`
	KnowledgeBaseIDs *[]string       `json:"knowledge_base_ids,omitempty"`
	Memory           map[string]any  `json:"memory,omitempty"`
	Limits           map[string]any  `json:"limits,omitempty"`
	Policy           map[string]any  `json:"policy,omitempty"`
	StructuredOutput json.RawMessage `json:"structured_output,omitempty"`
}

type Conversation struct {
	ID          string `json:"id"`
	AssistantID string `json:"assistant_id"`
}

type ConversationInput struct {
	AssistantID string `json:"assistant_id"`
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type MessageInput struct {
	Content string `json:"content"`
}

type Credential struct {
	ID          string   `json:"id"`
	PrincipalID string   `json:"principal_id"`
	Name        string   `json:"name"`
	Scopes      []string `json:"scopes"`
	CreatedAt   string   `json:"created_at"`
	ExpiresAt   string   `json:"expires_at"`
	RevokedAt   string   `json:"revoked_at"`
}

type CredentialInput struct {
	Name      string   `json:"name"`
	Scopes    []string `json:"scopes"`
	ExpiresAt string   `json:"expires_at,omitempty"`
}

type CredentialRotation struct {
	ExpiresAt string `json:"expires_at,omitempty"`
}

type CredentialSecret struct {
	Credential Credential `json:"credential"`
	APIKey     string     `json:"api_key"`
}

type ModelDefinition struct {
	ID              string   `json:"id"`
	Provider        string   `json:"provider"`
	Capabilities    []string `json:"capabilities"`
	MaxOutputTokens int      `json:"max_output_tokens"`
	ContextWindow   int      `json:"context_window"`
}

type ToolDefinition struct {
	ID           string         `json:"id"`
	Name         string         `json:"name"`
	Description  string         `json:"description"`
	Version      string         `json:"version"`
	InputSchema  map[string]any `json:"input_schema"`
	OutputSchema map[string]any `json:"output_schema"`
	Permissions  []string       `json:"permissions"`
	RiskLevel    string         `json:"risk_level"`
}

type PluginCatalog struct {
	Plugins []map[string]any `json:"plugins"`
}

type PluginSetting struct {
	Enabled bool           `json:"enabled"`
	Config  map[string]any `json:"config"`
}

type PluginUpdate struct {
	Revision int  `json:"revision"`
	Applied  bool `json:"applied"`
}

type PluginHealth struct {
	ID     string `json:"id"`
	State  string `json:"state"`
	Status string `json:"status"`
	Error  string `json:"error"`
}

type KnowledgeBase struct {
	ID            string         `json:"id"`
	Name          string         `json:"name"`
	Description   string         `json:"description"`
	Revision      int            `json:"revision"`
	ActiveVersion int            `json:"active_version"`
	CreatedAt     string         `json:"created_at"`
	UpdatedAt     string         `json:"updated_at"`
	Config        map[string]any `json:"config"`
}

type KnowledgeBaseInput struct {
	Name        string         `json:"name"`
	Description string         `json:"description,omitempty"`
	Config      map[string]any `json:"config,omitempty"`
}

type KnowledgeBasePatch struct {
	Name        *string        `json:"name,omitempty"`
	Description *string        `json:"description,omitempty"`
	Config      map[string]any `json:"config,omitempty"`
}

type KnowledgeBaseVersion struct {
	Version    int            `json:"version"`
	State      string         `json:"state"`
	Config     map[string]any `json:"config"`
	CreatedAt  string         `json:"created_at"`
	ChunkCount int            `json:"chunk_count"`
	Attempts   int            `json:"attempts"`
	Embedding  map[string]any `json:"embedding"`
	ReadyAt    string         `json:"ready_at"`
}

type KnowledgeBaseVersionInput struct {
	ChunkSize    int `json:"chunk_size,omitempty"`
	ChunkOverlap int `json:"chunk_overlap,omitempty"`
}

type KnowledgeBaseExport struct {
	KnowledgeBase KnowledgeBase          `json:"knowledge_base"`
	Versions      []KnowledgeBaseVersion `json:"versions"`
	Documents     []Document             `json:"documents"`
	Chunks        []map[string]any       `json:"chunks"`
	ExportedAt    string                 `json:"exported_at"`
}

type Document struct {
	ID              string `json:"id"`
	KnowledgeBaseID string `json:"knowledge_base_id"`
	Filename        string `json:"filename"`
	Title           string `json:"title"`
	MimeType        string `json:"mime_type"`
	SizeBytes       int64  `json:"size_bytes"`
	SHA256          string `json:"sha256"`
	CreatedAt       string `json:"created_at"`
	IngestionState  string `json:"ingestion_state"`
}

type DocumentJob struct {
	ID             string `json:"id"`
	DocumentID     string `json:"document_id"`
	State          string `json:"state"`
	Attempts       int    `json:"attempts"`
	ErrorCode      string `json:"error_code"`
	CreatedAt      string `json:"created_at"`
	UpdatedAt      string `json:"updated_at"`
	DeadLetteredAt string `json:"dead_lettered_at"`
}

type DocumentUpload struct {
	KnowledgeBaseID string
	Title           string
	Filename        string
	ContentType     string
	File            io.Reader
}

type AgentRun struct {
	ID                string         `json:"id"`
	ConversationID    string         `json:"conversation_id"`
	Status            string         `json:"status"`
	AssistantID       string         `json:"assistant_id"`
	AssistantVersion  int            `json:"assistant_version"`
	Model             string         `json:"model"`
	CreatedAt         string         `json:"created_at"`
	UpdatedAt         string         `json:"updated_at"`
	FinishedAt        string         `json:"finished_at"`
	CancelRequestedAt string         `json:"cancel_requested_at"`
	Usage             map[string]any `json:"usage"`
	ErrorCode         string         `json:"error_code"`
}

type Approval struct {
	ID              string         `json:"id"`
	RunID           string         `json:"run_id"`
	ToolID          string         `json:"tool_id"`
	ToolVersion     string         `json:"tool_version"`
	ArgumentsDigest string         `json:"arguments_digest"`
	PolicyDigest    string         `json:"policy_digest"`
	PolicySnapshot  map[string]any `json:"policy_snapshot"`
	RequestedBy     string         `json:"requested_by"`
	Status          string         `json:"status"`
	CreatedAt       string         `json:"created_at"`
	ExpiresAt       string         `json:"expires_at"`
	DecidedAt       string         `json:"decided_at"`
	DecidedBy       string         `json:"decided_by"`
	ConsumedAt      string         `json:"consumed_at"`
}

type AuditEvent struct {
	ID               string         `json:"id"`
	ActorPrincipalID string         `json:"actor_principal_id"`
	Action           string         `json:"action"`
	TargetID         string         `json:"target_id"`
	TargetType       string         `json:"target_type"`
	RunID            string         `json:"run_id"`
	Outcome          string         `json:"outcome"`
	CreatedAt        string         `json:"created_at"`
	Details          map[string]any `json:"details"`
}

type WidgetTokenInput struct {
	AssistantID      string `json:"assistant_id"`
	ConversationID   string `json:"conversation_id"`
	Subject          string `json:"subject,omitempty"`
	Origin           string `json:"origin"`
	ExpiresInSeconds int    `json:"expires_in_seconds,omitempty"`
}

type WidgetToken struct {
	Token          string   `json:"token"`
	ID             string   `json:"id"`
	AssistantID    string   `json:"assistant_id"`
	ConversationID string   `json:"conversation_id"`
	Subject        string   `json:"subject"`
	Scopes         []string `json:"scopes"`
	Origin         string   `json:"origin"`
	ExpiresAt      string   `json:"expires_at"`
	RevokedAt      string   `json:"revoked_at"`
	CreatedAt      string   `json:"created_at"`
	CreatedBy      string   `json:"created_by"`
}

type RuntimeEvent struct {
	EventID       string          `json:"event_id"`
	EventType     string          `json:"event_type"`
	EventVersion  int             `json:"event_version"`
	Timestamp     string          `json:"timestamp"`
	RunID         string          `json:"run_id"`
	CorrelationID string          `json:"correlation_id"`
	Payload       json.RawMessage `json:"payload"`
}

func (e RuntimeEvent) DecodePayload(target any) error {
	return json.Unmarshal(e.Payload, target)
}

type StartedPayload struct{}

type TextPayload struct {
	Text string `json:"text"`
}

type CompletedPayload struct {
	Text      string           `json:"text"`
	Usage     map[string]int   `json:"usage"`
	Citations []map[string]any `json:"citations"`
}

type FailurePayload struct {
	Code string `json:"code"`
}

type CancelledPayload struct {
	Code string `json:"code"`
}
