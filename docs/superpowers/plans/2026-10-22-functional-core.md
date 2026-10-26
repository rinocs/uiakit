# Functional Core Implementation Plan

> **For agentic workers:** implement task-by-task using superpowers:executing-plans. User requested immediate implementation; task ownership below supports parallel work when the requested model is available.

**Goal:** Persistent conversation through Go Gateway → Python Runtime → OpenAI-compatible provider → SSE.
**Architecture:** gateway owns authentication, PostgreSQL and public API; runtime owns bounded model execution. Internal bearer authentication and versioned contract.
**Tech Stack:** Go + chi + pgx; Python >=3.12 + FastAPI + httpx + Pydantic; PostgreSQL 17; Docker Compose.
**Spec:** PROJECT_SPEC.md, Milestone 1; docs/adr/0001-functional-core.md.

## Global Constraints

- No cloud required; provider configured by the operator.
- Runtime and database not exposed; API keys never persisted in the clear.
- Don't implement all milestones in one change.
- Mock providers in tests; no real credentials.

## Review Focus

- Missing credentials and invalid bodies: 401/422 before calling the model.
- Duplicate and concurrent retry: one call and 409 on conflicts.
- Disconnect and timeout: upstream deletion and run failed persisted.
- Provider malformed or in error: normalized error, never empty success.
- Restart or storage failure: no terminal response before persistence.

### Task 1: Contracts and plan — owner coordinator
- [x] Review repository, toolchain and specification; document boundaries and invariants.
- [x] Define public OpenAPI and internal contract with SSE v1.

### Task 2: Runtime — owner Python
Files: apps/runtime/pyproject.toml, requirements*.txt, uai_runtime/{models,provider,app}.py, tests/.
Interface: POST /internal/v1/runs, Bearer INTERNAL_API_KEY.
Input: {run_id: UUID, correlation_id: UUID, model: str, system_prompt: str,
messages: [{role: user|assistant, content: str}]}.
SSE output: event_type, event_version=1, event_id UUID, UTC timestamp, run_id,
correlation_id, payload. delta payload {text}; completed {text, usage}; failed {code}.
- [x] Write tests for auth, streaming, provider malformed/error, timeout and limits; observe red.
- [x] Implement typed provider protocol, models, streaming bounded agent and internal API.
- [x] Run pytest and compile checks, resolve failures.

### Task 3: Gateway and storage — owner Go
Files: apps/gateway/{go.mod,go.sum,main.go,server.go,store.go,server_test.go,migrations/001_core.sql}.
Endpoints: GET /v1/health; POST/GET /v1/assistants; POST /v1/conversations;
GET /v1/conversations/{id}/messages; POST same URL (SSE, Idempotency-Key required).
- [x] Write auth, validation, SSE, replay/conflict tests; observe red.
- [x] Implement PostgreSQL persistence and migration, operator auth, rate limiting,
  durable idempotency, bounded upstream streaming with cancellation.
- [x] Run go test ./... and go vet ./....

### Task 4: Deployment and E2E — owner coordinator
Files: compose.yaml, .env.example, deploy/docker/*, tests/e2e/*, README.md, Makefile.
- [x] Create mock OpenAI SSE provider and E2E assertions: auth, create, stream,
  history, duplicate replay, conflicting replay, restart persistence.
- [x] Pin dependencies and images, configure internal networks and health checks.
- [x] Run complete test suites, contract validation and Compose config; attempt E2E (blocked by Docker socket permissions).
- [x] Review source, report verified behavior and environmental limitations.

## Execution record

- Repository contains only PROJECT_SPEC.md; .git is empty/read-only, so commits
  and worktrees unavailable. Work proceeds in authorized workspace.
- Docker socket access denied; report startup/E2E checks separately if unavailable.
- User requested deepseek-4.1-flash for subagents; model unavailable, no substitution.Results: 16 Python tests, 7 Go tests (-race), vet and gateway build pass.
Compose config and shell syntax pass. Current Docker startup/E2E remains blocked
by sandbox socket permissions; see docs/implementation-status.md.