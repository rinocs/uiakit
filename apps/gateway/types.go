package main

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

var ErrNotFound = errors.New("not_found")
var ErrConflict = errors.New("conflict")
var ErrExportTooLarge = errors.New("export_too_large")

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}
type Event struct {
	ID            string          `json:"event_id"`
	Type          string          `json:"event_type"`
	Version       int             `json:"event_version"`
	Timestamp     time.Time       `json:"timestamp"`
	RunID         string          `json:"run_id"`
	CorrelationID string          `json:"correlation_id"`
	Payload       json.RawMessage `json:"payload"`
}
type RetrievalTarget struct {
	KnowledgeBaseID    string `json:"knowledge_base_id"`
	Collection         string `json:"collection"`
	IndexVersion       string `json:"index_version"`
	EmbeddingProvider  string `json:"embedding_provider"`
	EmbeddingModel     string `json:"embedding_model"`
	EmbeddingVersion   string `json:"embedding_version"`
	EmbeddingDimension int    `json:"embedding_dimension"`
}

type AgentRun struct {
	ID                string     `json:"id"`
	ConversationID    string     `json:"conversation_id"`
	Status            string     `json:"status"`
	AssistantID       string     `json:"assistant_id"`
	AssistantVersion  int        `json:"assistant_version"`
	Model             string     `json:"model"`
	CreatedAt         time.Time  `json:"created_at"`
	FinishedAt        *time.Time `json:"finished_at,omitempty"`
	UpdatedAt         time.Time  `json:"updated_at"`
	CancelRequestedAt *time.Time `json:"cancel_requested_at,omitempty"`
}

type Approval struct {
	ID              string          `json:"id"`
	RunID           string          `json:"run_id"`
	ToolID          string          `json:"tool_id"`
	ToolVersion     string          `json:"tool_version"`
	ArgumentsDigest string          `json:"arguments_digest"`
	PolicyDigest    string          `json:"policy_digest"`
	PolicySnapshot  json.RawMessage `json:"policy_snapshot"`
	RequestedBy     string          `json:"requested_by"`
	Status          string          `json:"status"`
	CreatedAt       time.Time       `json:"created_at"`
	ExpiresAt       time.Time       `json:"expires_at"`
	DecidedAt       *time.Time      `json:"decided_at,omitempty"`
	DecidedBy       *string         `json:"decided_by,omitempty"`
	ConsumedAt      *time.Time      `json:"consumed_at,omitempty"`
}

type ToolExecution struct {
	ID              string          `json:"id"`
	RunID           string          `json:"run_id"`
	ToolID          string          `json:"tool_id"`
	ToolVersion     string          `json:"tool_version"`
	ArgumentsDigest string          `json:"arguments_digest"`
	ApprovalID      *string         `json:"approval_id,omitempty"`
	RiskLevel       string          `json:"risk_level"`
	IdempotencyKey  string          `json:"idempotency_key"`
	Status          string          `json:"status"`
	Attempt         int             `json:"attempt"`
	MaxAttempts     int             `json:"max_attempts"`
	Result          json.RawMessage `json:"result,omitempty"`
	ErrorCode       *string         `json:"error_code,omitempty"`
	CreatedAt       time.Time       `json:"created_at"`
	StartedAt       *time.Time      `json:"started_at,omitempty"`
	FinishedAt      *time.Time      `json:"finished_at,omitempty"`
	UpdatedAt       time.Time       `json:"updated_at"`
}

type ToolExecutionRequest struct {
	RunID           string  `json:"run_id"`
	ToolID          string  `json:"tool_id"`
	ToolVersion     string  `json:"tool_version"`
	ArgumentsDigest string  `json:"arguments_digest"`
	ApprovalID      *string `json:"approval_id,omitempty"`
	RiskLevel       string  `json:"risk_level"`
	IdempotencyKey  string  `json:"idempotency_key"`
	MaxAttempts     int     `json:"max_attempts"`
	PrincipalID     string  `json:"principal_id,omitempty"`
	CorrelationID   string  `json:"correlation_id,omitempty"`
}

type ToolExecutionFinish struct {
	Result    json.RawMessage `json:"result,omitempty"`
	ErrorCode string          `json:"error_code,omitempty"`
}

type Run struct {
	ID, ConversationID, Content, Model, SystemPrompt, Status, CorrelationID, OwnerID string
	Messages                                                                         []Message
	Events                                                                           []Event
	AssistantConfig                                                                  Assistant
	ModelSnapshot                                                                    *ModelDefinition
	RetrievalTargets                                                                 []RetrievalTarget
}

type KnowledgeBaseStore interface {
	KnowledgeBases(context.Context) ([]KnowledgeBase, error)
	KnowledgeBase(context.Context, string) (KnowledgeBase, error)
	KnowledgeBaseVersions(context.Context, string) ([]KnowledgeBaseVersion, error)
	CreateKnowledgeBase(context.Context, string, string, KnowledgeBaseConfig, *KnowledgeBaseEmbedding) (KnowledgeBase, error)
	UpdateKnowledgeBase(context.Context, string, int, KnowledgeBase) (KnowledgeBase, error)
	DeleteKnowledgeBase(context.Context, string, int) error
	CreateKnowledgeBaseVersion(context.Context, string, int, KnowledgeBaseConfig, *KnowledgeBaseEmbedding) (KnowledgeBase, KnowledgeBaseVersion, error)
	KnowledgeBaseExport(context.Context, string) (KnowledgeBaseExport, error)
}

type DocumentStore interface {
	Documents(context.Context, string) ([]Document, error)
	Document(context.Context, string) (Document, error)
	DocumentByHash(context.Context, string, string) (Document, error)
	CreateDocument(context.Context, Document) (Document, bool, error)
	DeleteDocument(context.Context, string) (Document, error)
	DocumentJob(context.Context, string) (DocumentJob, error)
	CancelDocumentJob(context.Context, string) (DocumentJob, error)
}

// Store is the gateway persistence boundary; all idempotency and conversation
// concurrency decisions belong to Start's transaction, not HTTP process memory.
type AgentRunStore interface {
	AgentRuns(context.Context) ([]AgentRun, error)
	AgentRun(context.Context, string) (AgentRun, error)
	CancelAgentRun(context.Context, string) (AgentRun, error)
}

type AuditStore interface {
	AuditEvents(context.Context, AuditFilter) ([]AuditEvent, error)
}

type ProviderStore interface {
	ProviderConfiguration(context.Context) (ProviderConfiguration, error)
	SaveProviderConfiguration(context.Context, int, ProviderConfiguration) (ProviderConfiguration, error)
	AssistantsUsingModel(context.Context, string) (int, error)
}

type ApprovalStore interface {
	Approvals(context.Context) ([]Approval, error)
	Approval(context.Context, string) (Approval, error)
	DecideApproval(context.Context, string, string) (Approval, error)
}

type ToolExecutionStore interface {
	ReserveToolExecution(context.Context, ToolExecutionRequest) (ToolExecution, error)
	StartToolExecution(context.Context, string) (ToolExecution, error)
	CompleteToolExecution(context.Context, string, json.RawMessage) (ToolExecution, error)
	FailToolExecution(context.Context, string, string) (ToolExecution, error)
	UnknownToolExecution(context.Context, string, string) (ToolExecution, error)
	ReconcileToolExecution(context.Context, string, string, json.RawMessage, string) (ToolExecution, error)
	ToolExecution(context.Context, string) (ToolExecution, error)
}

type Store interface {
	CredentialStore
	WidgetTokenStore
	PluginStore
	KnowledgeBaseStore
	DocumentStore
	AgentRunStore
	AuditStore
	ProviderStore
	ApprovalStore
	ToolExecutionStore
	Models(context.Context) ([]ModelDefinition, error)
	SyncModels(context.Context, []ModelDefinition) error
	Assistant(context.Context, string) (Assistant, error)
	AssistantVersions(context.Context, string) ([]Assistant, error)
	UpdateAssistant(context.Context, string, int, json.RawMessage) (Assistant, error)
	Health(context.Context) error
	Assistants(context.Context) ([]Assistant, error)
	CreateAssistant(context.Context, Assistant) (Assistant, error)
	CreateConversation(context.Context, string) (string, error)
	DeleteConversation(context.Context, string) error
	RunRetention(context.Context, RetentionPolicy) (RetentionResult, error)
	Messages(context.Context, string) ([]Message, error)
	Start(context.Context, string, string, string) (Run, error)
	Finish(context.Context, Run, []Event, string) error
}

func newID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
