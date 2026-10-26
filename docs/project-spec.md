# PROMPT CODEX — Universal AI Kit

## Role

Act as a **Principal Software Architect, Senior Go Engineer, Senior Python Engineer and AI/LLM Infrastructure Engineer**, with experience in:

- Distributed systems and modular architectures.
- RAG (Retrieval-Augmented Generation).
- AI agents, tool calling and MCP.
- Extensibility framework, plugins and middleware.
- Python, FastAPI, Go and who.
- PostgreSQL, Redis and vector databases.
- Docker Compose, CI/CD and application security.
- SDK, REST API, SSE and OpenAPI.

You must design and implement **Universal AI Kit (UAI)**: a self-hosted, independent, plug-and-play AI platform that can be reused across multiple software projects.

Don't just produce documentation or pseudocode. Implement working code, tests, Docker configuration, examples and documentation.

Work in incremental milestones, verifying that the software is functional at the end of each phase.

---

#1. Product vision

Universal AI Kit is a Docker-installable AI platform that lets you add RAG chatbots and AI agents to any application.

It must be:

- **Self-hosted:** no cloud services required.
- **Plug-and-play:** installation via Docker Compose.
- **API-first:** accessible from any language.
- **Framework-agnostic:** can be integrated into Laravel, Go, React, Svelte, Vue, WordPress and mobile applications.
- **Extensible:** tools, directives, hooks, plugins, skills and providers.
- **Modular:** each component replaceable via interfaces.
- **Configurable:** multiple assistants in the same installation.
- **Secure:** Authentication, authorizations, isolation, and agent execution controls.
- **Portable:** Each project can have its own independent Docker instance.
- **Open source friendly:** prefer dependencies with compatible licenses and check the relevant conditions.

The architecture can be inspired by Cheshire Cat AI, but it must not depend on its code or reproduce it automatically.

Also study the architectural concepts of Haystack, Langflow, LlamaIndex, and other frameworks when useful.

## Fundamental principle

Universal AI Kit must be an **Extensible AI Runtime**, not simply a chatbot with an HTTP endpoint.

The runtime must allow you to compose AI capabilities through interfaces, plugins, and middleware.

---

#2. Technology stack

Preferably use:

| Component | Technology |
|---|---|
| Public API Gateway | Go + who |
| AI Runtime | Python 3.12+ |
| Internal API | FastAPI |
| Configuration Database | PostgreSQL |
| Vector Database | Qdrant |
| Cache / Background Jobs | Redis |
| RAG Framework | Haystack, using adapter |
| Model Providers | Ollama, OpenAI-compatible, LiteLLM |
| Storage | Local and S3-compatible filesystem |
| Admin UI | SvelteKit or React |
| Client SDK | TypeScript, PHP, Go |
| Deployment | Docker Compose |
| Observability | OpenTelemetry |
| Testing | pytest, Go testing |

Don't introduce heavy dependencies when a simple implementation is sufficient.

Qdrant, Redis, LiteLLM and optional services must be started only when required by the enabled features, where technically possible.

---

#3. Component architecture

Organize the system in:

```text
universal-ai-kit/
├── apps/
│ ├── gateway/ # Go REST API
│ ├── runtime/ # Python AI Runtime
│ ├── worker/ # Ingestion + background jobs
│ └── console/ # Admin dashboard
│
├── packages/
│ ├── core/ # Runtime interfaces
│ ├── plugin-sdk/ # Plugin abstractions
│ ├── sdk-typescript/
│ ├── sdk-php/
│ ├── sdk-go/
│ ├── chat-widget/
│ └── api-contract/
│
├── plugins/
│ ├── builtin/
│ └── examples/
│
├── configs/
│ ├── assistants/
│ ├── models/
│ └── policies/
│
├── deploy/
│ └── docker/
│
├── tests/
└── docs/
```The structure can be improved if there are concrete architectural reasons.

## Responsibility

### Go Gateway

Manages:

- Public REST APIs.
- Authentication and authorization.
- API keys and temporary tokens.
- Rate limiting.
- Sessions and conversations.
- SSE streaming.
- API versioning.
- Routing to the runtime.
- Audit of sensitive events.
- Application configurations and metadata.

### Python Runtime

Manages:

- Agent lifecycle.
- Directives.
- Hooks.
- Tool calling.
- Plugin execution.
- Model adapters.
- Retrieval.
- Memory.
- Skill loading.
- Agent execution state.
- Streaming of internal events.

The gateway must communicate with the runtime via explicit, versioned contracts.

The runtime should not be exposed directly to the Internet.

---

#4. Core Runtime

Design interfaces and abstract classes for:

```python
Agent
AgentRuntime
Directives
Hook
Tools
Plugins
PluginManager
Skills
MemoryProvider
ModelProvider
EmbeddingProvider
VectorStore
Retrievers
DocumentProcessor
ExecutionContext
RuntimeEvent
```

Clearly define responsibilities, lifecycles, configurations and contracts.

Use strict Python typing, Pydantic for data models, and dependency injection where useful.

## Agent

Each Agent must support:

- Unique identifier.
- Name and description.
- System prompt.
- Model configuration.
- Directives enabled.
- Authorized tools.
- Skills.
- Knowledge base.
- Memory configuration.
- Execution limits.
- Security policy.
- Streaming.
- Optional structured outputs.

Implements an initially single-agent agent loop.

The model can:

1. Respond directly.
2. Request tools.
3. Receive the results of the tools.
4. Continue generation.
5. Finish within limits and policies.

Have a maximum limit on steps, tool calls, tokens and duration.

---

#5. Directive System

Inspired by Cheshire Cat AI's Directive concept.

A Directive is a component applied at one or more points in the agent's lifecycle.

Implements an interface approximately similar to:

```python
class Directive(ABC):
    name: str
    priority: int

    async def before_model(
        self,
        context: ExecutionContext
    ) -> ExecutionContext:
        return context

    async def after_model(
        self,
        context: ExecutionContext
    ) -> ExecutionContext:
        return context
```

Improve this interface if necessary.

The directives must be:

- Dynamically adjustable.
- Modular.
- Sortable by priorities and dependencies.
- Can be enabled for a single assistant.
- Configurable.
- Testable in isolation.
- Observables.
- Subject to timeouts and error handling.

Implement at least:

1. `SystemPromptDirective`
2. `ConversationMemoryDirective`
3. `RAGRetrievalDirective`
4. `ToolPolicyDirective`
5. `OutputValidationDirective`
6. `ObservabilityDirective`

Mandatory security directives must not be able to be removed from plugins.

---

#6. Event and Hook System

Define typical events throughout the lifecycle:

```text
request.received
request.authorized
agent.started
context.building
context.ready
model.before
model.after
tool.requested
tool.authorized
tool.started
tool.completed
tool.failed
memory.read
memory.write
response.delta
response.completed
agent.failed
agent.cancelled
```

Don't limit yourself to a generic event emitter.

Define:

- Typed payloads.
- Event versioning.
- Correlation ID.
- Run ID.
- Subscriber registration.
- Sorting, when necessary.
- Error propagation.
- Asynchronous events.
- Distinction between observational events and middleware capable of modifying the context.

Prevents arbitrary subscribers from directly modifying the internal state of agents.

---

#7. Plugin System

Create a plugin system that allows you to add functionality without changing the core.Each plugin must have a manifest:

```yaml
id: com.example.real-estate
name: Real Estate Integration
version: 1.0.0

runtime: python

compatibility:
  core: ">=0.1.0,<1.0.0"

capabilities:
  - tools
  - directives
  - hooks

permissions:
  networks:
    connectors:
      - real_estate_api
```

The Plugin Manager must support:

- Discovery.
- Manifest validation.
- Version compatibility.
- Dependency resolution.
- Loading.
- Registration.
- Activation/deactivation.
- Configuration.
- Health status.
- Logging.
- Plugin lifecycle.
- Error isolation.

Define two categories:

**Trusted plugins:** Python packages installed and approved by the administrator, running in the same environment as the runtime.

**Isolated plugins:** HTTP/MCP integrations run in separate processes or containers.

Don't consider trusted plugins a sandbox.

Do not implement insecure hot-reload or arbitrary code installation via public endpoint.

---

#8. Tool Registry

Implement a centralized tool registration and execution system.

Each tool must declare:

```text
id
name
description
version
input_schema
output_schema
permissions
risk_level
timeout
retry_policy
executor
```

Types of executors:

- Built-in Python.
- HTTP.
- MCP.
- Plugin-provided.

For MVP it implements built-in and HTTP. Predict the MCP contract and implement it in the next phase.

The Tool Executor must execute:

1. Validation of parameters.
2. Permission control.
3. Limit control.
4. Any request for approval.
5. Execution.
6. Validation of result.
7. Audits.
8. Return to the model.

For operations with side effects, expect idempotence and human approval.

No tool should be able to obtain additional privileges based on the text generated by the model.

---

#9. RAG Engine

Implement RAG as a composable runtime capability.

The RAG engine does not need to be tied directly to Haystack.

Define adapter for:

```python
DocumentLoader
DocumentParser
Chunkers
EmbeddingProvider
VectorStore
Retrievers
Reranker
```

Implement an ingestion pipeline:

```text
Upload
  -> Validate
  -> Parse
  -> Normalize
  -> Chunks
  -> Embed
  -> Index
```

And a retrieval pipeline:

```text
User Queries
  -> Access Filters
  -> Query Processing
  -> Retrieval
  -> Optional Reranking
  -> Context Assembly
  -> LLM
  -> Quotations
```

Initially supports:

- Textual PDFs.
- TXT.
- Markdown.
- HTML.
- DOCX.

Provide interfaces for OCR, SQL connectors, web crawler and Git repository.

Knowledge bases must be:

- Configurable.
- Versionable.
- Associated with one or more assistants.
- Filterable according to authorizations.
- Reindexable.
- Exportable.

Manage document hashing, deduplication, chunk provenance and citations.

Information from retrieval must not be able to modify system prompts, policies or privileges.

---

#10. Memory System

Design three levels of memory:

### Working Memory
Temporary data of the single execution.

### Conversation Memory
Persistent message history.

### Semantic Memory
Semantically retrievable information, optionally activated.

Define a `MemoryProvider` interface with read, write, delete and retention operations.

Do not implement automatic semantic memory before defining user data persistence and deletion policies.

---

#11. Model Provider System

The runtime must not depend on a specific AI provider.

Implement initial adapters for:

- OpenAI-compatible API.
- Ollama.

Expect support for LiteLLM as an additional provider.

Separate capabilities:

```text
chat
streaming
tool_calling
structured_output
embeddings
reranking
vision
```

Don't assume that every model supports all features.

The models must declare the capabilities actually available.Implement:

- Timeout.
- Configurable retries.
- Error normalization.
- Token usage.
- Cost tracking when possible.
- Context window awareness.
- Capability validation.

---

#12. REST API and Streaming

Define OpenAPI 3.1 for:

```text
/v1/assistants
/v1/conversations
/v1/conversations/{id}/messages
/v1/knowledge-bases
/v1/documents
/v1/agent-runs
/v1/tools
/v1/plugins
/v1/models
/v1/approvals
/v1/health
```

Supports typed SSE streaming.

Events must include:

```text
event_id
event_type
event_version
timestamp
run_id
payload
```

Predict idempotency key for message creation and actions with side effects.

Keep the public contract separate from the runtime's internal interfaces.

Generate or validate SDKs against OpenAPI.

---

#13. Databases

Use PostgreSQL to:

- Assistants.
- Assistant versions.
- Model configuration.
- Knowledge bases.
- Documents.
- Conversation sessions.
- Messages.
- Agent runs.
- Tool definitions.
- Tool executions.
- Approvals.
- Plugins.
- API credentials.
- Audit events.
- Ingestion jobs.

Use Qdrant for vector search.

Use Redis for caching, rate limiting and job management where needed.

Define versioned migrations, indexes, foreign keys, retention and consistent deletion.

PostgreSQL must be the authoritative source; vector indices must be reconstructible.

---

#14. Security Architecture

Implement security-by-default:

- Authentication.
- Authorization.
- API scopes.
- Administrative RBAC.
- Session tokens for widgets.
- Rate limiting.
- Secret management.
- Tool authorization.
- Human approval.
- SSRF protection.
- Document access control.
- File upload validation.
- Resource limits.
- Audit log.
- Secure logging.
- Data retention.
- Protection against prompt injection.

Do not directly expose internal services or databases.

Do not allow model-generated code to run in the main process.

API keys must not be persisted in the clear.

HTTP tools must use explicitly authorized connectors and targets.

Action approvals must be tied to immutable topics, authorizing user, and expiration.

---

#15. Docker Deployment

Provide Docker Compose for standalone installations.

Objective:

```bash
git clone <repository>
cd universal-ai-kit

cp .env.example .env

docker compose up -d
```

Define profiles:

- `core`
- `local-ai`
- `full`

The minimum profile must request only the strictly necessary services.

Predict:

- Health check.
- Persistent volumes.
- Network isolation.
- Controlled egress.
- Startup dependencies.
- Database migrations.
- Backup and restore.
- Configuration validation.
- Graceful shutdown.
- Versioned container images.

Documents how to install two completely independent instances on the same host.

---

#16. Admin Console

Create a minimal console that allows you to:

- Create assistants.
- Configure system prompts and templates.
- Enable directives.
- Manage knowledge base.
- Upload documents.
- Register HTTP tools.
- Enable plugins.
- Consult conversations.
- Check executions and logs.
- Test the chatbot.

Don't initially build a complex visual workflow editor.

---

#17. SDK and Chat Widget

Progressively implement:

1. TypeScript SDK.
2. PHP SDK with Laravel integration.
3. Go SDK.
4. Web Component Widgets.

The widget must be framework-agnostic and support:

- Streaming.
- Secure Markdown.
- Quotes.
- Theme customization.
- Session tokens.
- Event callbacks.
- Responsive layout.

Administrative credentials do not need to be entered into client browsers.

---

#18. Testing

Add tests for:

- Agent lifecycle.
- Directive ordering.
- Hook dispatch.
- Plugin discovery.
- Plugin validation.
- Tool authorization.
- Agent execution limits.
- RAG retrieval.
- Citation provenance.
- Knowledge base isolation.
- API authentication.
- SSE streaming.
- Idempotency.
- Error handling.
- Docker startups.Use mock providers and tools in unit tests to avoid calls to external services.

Prepare at least one end-to-end test with a local model or OpenAI-compatible mock.

---

#19. Incremental implementation

Don't try to implement everything at once.

### Milestone 1 — Functional Core

Implement:

- Repositories.
- Docker.
- Go Gateway.
- Python Runtime.
- Basic Agent.
- OpenAI-compatible Model Provider.
- REST API.
- SSE.
- PostgreSQL.
- Tests.

The goal is to get a working conversation via API.

### Milestone 2 — Extensibility

Implement:

- Directives.
- Hook System.
- Tool Registry.
- SDK plugins.
- Plugin Loader.
- Lifecycle tests.

### Milestone 3 — RAG

Implement:

- Document ingestion.
- Qdrant.
- Embeddings.
- Retrieval.
- RAG Directive.
- Quotations.
- Knowledge base configuration.

### Milestone 4 — Agents

Implement:

- Tool calling.
- Agent execution state.
- Limits.
- HTTP Tools.
- Authorization.
- Human approval.
- Audits.

### Milestone 5 — Integration

Implement:

- TypeScript SDK.
- PHP/Laravel SDK.
- Go SDK.
- Chat Widgets.
- Admin Console minimal.

### Milestone 6 — Production Hardening

Implement:

- Backup and restore.
- Observability.
- Security tests.
- Performance tests.
- Deployment documentation.
- Release packaging.

---

#20. Acceptance criteria

The project must allow you to:

1. Launch Universal AI Kit with Docker Compose.
2. Set up an Ollama or OpenAI-compatible model.
3. Create an assistant via API.
4. Send messages and receive streaming replies.
5. Install a sample plugin.
6. Enable a directive on an assistant.
7. Register and use an HTTP tool.
8. Upload documents to a knowledge base.
9. Query documents via RAG.
10. Get verifiable quotes.
11. Integrate the assistant into a Laravel application.
12. Deploy multiple independent Docker instances.
13. Update a component without compromising the API contract.

---

#21. Ways of working

Before starting:

1. Analyze the current repository.
2. Check dependency status and version compatibility.
3. Read any existing `AGENTS.md`, README, and configuration files.
4. Define the boundaries between Go Gateway and Python Runtime.
5. Prepare ADRs (Architecture Decision Records) for major decisions.
6. Identify the core's public interfaces.
7. Define an implementation plan with testable tasks.

During development:

- Implement real code, not just examples.
- Keep components small, typed, and testable.
- Don't introduce abstractions without a concrete use case.
- Prefer stable interfaces to coupled implementations.
- Use compatible and reproducible versions of dependencies.
- Do not enter real credentials in the repository.
- Do not declare services that you have not tested working.
- Run static tests and checks after major changes.
- Document compromises and deferred features.

Don't implement all the milestones in one giant change.

**Get started with Milestone 1 straight away**, creating a working vertical slice:

`HTTP request -> Go Gateway -> Python Agent Runtime -> Model Provider -> SSE response`

Provide for future extensibility without prematurely developing all subsystems.

At the end it shows:

- Files created and edited.
- Architecture actually implemented.
- Commands to start the project.
- Endpoints available.
- Tests performed and related results.
- Existing limitations.
- Upcoming priority tasks.

**Ultimate goal: Build a reusable AI infrastructure, not a one-time demo.**