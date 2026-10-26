# ADR 0001 — Functional Core

Status: Accepted by PROJECT_SPEC.md, sections 3 and 19–21.

## Borders

Go + public API owner, authentication via SHA-256 hash of an API key
operator, PostgreSQL, conversations and idempotence. A single operator credential
it's MVP perimeter: no promises of multitenancy or full RBAC.
Python + FastAPI has Agent and ModelProvider, execution and translation limits
OpenAI-compatible → SSE events. No public access to the runtime or database.
The provider is configured by the operator, never from URLs provided in the request.

## Flow and invariants

1. Authentic gateway, valid body and Idempotency-Key, blocks the conversation.
2. PostgreSQL logs message and run before calling the runtime.
3. Runtime receives pre-authorized prompts and history, uses only one template and
   returns agent.started, response.delta, response.completed, or agent.failed.
4. Gateway persists the output before forwarding the terminal event.
5. Duplicate requests do not have to invoke the model again; conflicts of
   contents on the same key are 409. Aborted runs are not successful responses.

History includes only completed, sorted shifts; only one run per conversation.
No automatic retry after the stream starts. No provider error text,
prompt or credential in public logs or errors.

## Decisions

PostgreSQL authoritative; no Redis/Qdrant in core. ModelProvider interface
real, with OpenAI-compatible implementation; tools, plugins and RAG referred to
milestones indicated. Public and internal SSE only share the v1 envelope.
Versioned SQL migrations, run before accepting traffic.
Events persisted for replays of completed runs. A duplicate active run
returns 409. Disconnect deletes the provider and marks the run failed.

## Deliberate limits

Only one operator, fixed limits and limited history; no widget/browser tokens,
console, RBAC, automatic retention or tool. Default local binding: TLS via
reverse proxy required for publication. Restart recovers pending runs as
failed: single replica gateway deployment in this milestone.