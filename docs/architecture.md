# Architecture

Universal AI Kit separates the public control plane from AI execution and
ingestion. This keeps authorization, persistence and streaming in one place while
allowing the runtime and worker to evolve independently.

## Components

### Gateway (`apps/gateway`, Go)

The gateway is the only public API surface. It owns:

- API key, credential, role, scope and ownership enforcement;
- assistant configuration versions and conditional updates;
- conversations, messages, run state and idempotent replay;
- SSE delivery and cancellation;
- PostgreSQL migrations, retention and audit;
- per-process, per-principal and per-widget rate limits;
- widget CORS and scoped browser tokens.

The gateway waits for PostgreSQL and runtime health before serving traffic and
applies forward-only migrations in a transaction with an advisory lock. A
database schema newer than the binary is refused.

### Runtime (`apps/runtime`, Python)

The runtime executes one agent turn at a time per request. It:

- calls OpenAI-compatible or native Ollama chat/embedding providers;
- applies an ordered directive pipeline (RAG, built-in validation, tools);
- enforces step, token, character, duration and tool-call budgets;
- runs read-only or approved mutating tools through the execution journal;
- streams typed runtime events back to the gateway.

It does not own user identity or public authorization decisions. The gateway sends
the authoritative principal/scopes and allowed tool IDs; the runtime re-checks the
tool policy before an effect.

### Worker (`apps/worker`, Python)

The worker consumes durable PostgreSQL jobs:

1. claim a job with `FOR UPDATE SKIP LOCKED` and a lease;
2. validate/parse the blob;
3. chunk with stable IDs and provenance offsets;
4. embed and publish chunks and/or upsert Qdrant points;
5. activate the new index version atomically;
6. retry transient failures or dead-letter permanent failures.

An expired lease is reclaimable after a worker crash. Chunk IDs and tool
execution keys make retries idempotent.

### Data stores

| Store | Data | Notes |
|---|---|---|
| PostgreSQL | assistants, versions, conversations, runs, messages, jobs, chunks, approvals, audit, tokens | Source of truth; migrations owned by gateway |
| Filesystem/S3 | original document blobs | Content-addressed by upload hash; optional `boto3` |
| Qdrant | embeddings + provenance payload | Optional, per index version, rebuildable |
| OTLP collector | traces/metrics | Optional and fail-open |

## Request flow

```text
Client
  │ POST /v1/conversations/{id}/messages  (Bearer key + Idempotency-Key)
  ▼
Gateway
  ├─ authenticate, scope, ownership, rate limit
  ├─ Start/read idempotent run in PostgreSQL
  ├─ resolve assistant version, KB targets and allowed tools
  └─ POST /internal/v1/runs (internal key + trace context)
        ▼
      Runtime
        ├─ directive pipeline
        ├─ retrieval (ACL + index version)
        ├─ provider streaming
        ├─ tool policy / execution journal
        └─ typed events ───────────────► Gateway ── SSE ──► Client
                                            │
                                            └─ persist terminal events/messages
```

The gateway validates the event sequence (start → deltas → terminal), caps output
and stream size, and persists the terminal state before exposing success. A
disconnect or crash marks the run failed; replay returns the persisted result.

## Trust boundaries

- **Client → gateway:** API key or widget token, scopes, ownership, rate limit,
  request-size and schema validation.
- **Gateway → runtime:** internal bearer key, authoritative principal/scopes and
  allowed tool IDs; runtime never trusts model output for authority.
- **Runtime → provider:** egress allowlist, timeout, response-size limits and
  redacted errors.
- **Runtime → tool/plugin:** connector allowlist, SSRF/DNS pinning, approval
  binding and idempotent execution.
- **Retrieved content → model:** explicitly untrusted context; documents cannot
  change system prompts, scopes, tools or policy.
- **Worker → storage/Qdrant:** host-generated keys, validated paths, bounded
  parsing and atomic index activation.

## Lifecycle and recovery

- **Graceful shutdown:** gateway drains in-flight runs within its grace period;
  worker finishes or releases the current job.
- **Crash recovery:** gateway marks interrupted `running` runs failed with a
  replayable `agent.failed` event; worker reclaims expired leases.
- **Retention/deletion:** conversation/document/KB deletion uses tombstones and
  vector cleanup jobs so deleted content cannot return through reindex.
- **Upgrades:** forward-only migrations; a newer schema is refused by an older
  binary; destructive restore is explicit.

## Deployment constraints

The supported topology is **one gateway and one runtime per database**. There is
no distributed run lease, shared rate limiter or multi-gateway coordination.
Horizontal scaling on one database is not supported. Two independent installations
are supported with separate projects, ports, credentials and volumes.

See [deployment](deployment.md), [capacity](capacity.md) and
[upgrades](upgrades.md).
