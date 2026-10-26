# Universal AI Kit

**Self-hosted AI platform for chat, RAG, tools and agents.**

Universal AI Kit gives your application a versioned HTTP API and SSE streaming for
assistants, retrieval-augmented answers with citations, human-approved tool calls
and durable ingestion — with your own PostgreSQL, blobs and optional Qdrant.

<div class="grid cards" markdown>

-   :material-rocket-launch-outline:{ .lg .middle } **Install in minutes**

    ---

    Start the core stack with Docker Compose, create an admin key and send your
    first streamed message.

    [:octicons-arrow-right-24: Installation guide](installation.md)

-   :material-book-open-variant:{ .lg .middle } **Follow the guide**

    ---

    A complete path from model configuration to RAG, tools, SDKs and operations.

    [:octicons-arrow-right-24: Complete guide](guide.md)

-   :material-code-json:{ .lg .middle } **Copy working examples**

    ---

    Curl, TypeScript, Go and PHP examples for chat, RAG, approvals, widgets and
    deployment.

    [:octicons-arrow-right-24: Examples](examples.md)

-   :material-server-network:{ .lg .middle } **Operate with confidence**

    ---

    Health, graceful shutdown, backups, upgrades, capacity, security and release
    process.

    [:octicons-arrow-right-24: Operations](deployment.md)

</div>

## Why Universal AI Kit

- **Own your stack** — PostgreSQL, filesystem or S3-compatible blobs, optional
  Qdrant; no cloud service is mandatory.
- **Provider-neutral** — OpenAI-compatible chat/embeddings or native Ollama.
- **RAG with provenance** — versioned knowledge bases, durable ingestion, chunk
  offsets, filtered retrieval and verifiable citations.
- **Agent-safe tools** — scoped registry, SSRF-protected HTTP connectors, human
  approvals, idempotent effects and transactional audit.
- **Integration-ready** — TypeScript, Go and PHP SDKs, a Web Component widget, a
  SvelteKit console and a Laravel provider.
- **Production-minded** — bounded limits, recovery, retention, backups,
  observability and upgrade/rollback runbooks.

## Architecture at a glance

```text
Browser / SDK / Laravel
          │
          ▼
    Go gateway :8080 ──────────────┐
    auth, scopes, runs, SSE,       │
    persistence, rate limit        │
          │                        │
          ▼                        ▼
    Python runtime :8000      PostgreSQL
    agent loop, providers,    runs, messages,
    retrieval, tools, plugins KBs, jobs, audit
          │                        ▲
          ▼                        │
  OpenAI-compatible / Ollama       │
  chat + embeddings                │
                                   │
    Worker ── ingestion ── chunks ─┘
          │
          ▼
    Qdrant (optional)
```

| Component | Responsibility |
|---|---|
| **Gateway** (`apps/gateway`) | Public API, auth/scopes, assistant versions, conversations, SSE, runs, audit and rate limits |
| **Runtime** (`apps/runtime`) | Agent execution, providers, directives, retrieval, tools and structured output |
| **Worker** (`apps/worker`) | Durable parsing, chunking, embedding, Qdrant index build and cleanup |
| **Core** (`packages/core`) | Shared Python contracts for execution, RAG, budgets and providers |
| **Console** (`apps/console`) | Server-side authenticated SvelteKit administration UI |
| **SDKs** (`packages/sdk-*`) | TypeScript, Go and PHP clients for the public OpenAPI contract |

## Start here

<div class="grid cards" markdown>

-   **New to the project?**

    Read [What Universal AI Kit does](guide.md), then run the
    [installation guide](installation.md).

-   **Building an integration?**

    Use the [API overview](api.md), the public OpenAPI contract at
    `packages/api-contract/public.openapi.json` and the
    [SDK examples](examples.md#sdk-examples).

-   **Adding RAG?**

    Follow the [knowledge base](knowledge-bases.md), [ingestion](ingestion.md) and
    [RAG](rag.md) pages, then check [retrieval](retrieval.md) and
    [citations](rag.md).

-   **Operating the deployment?**

    Start with [deployment](deployment.md), then
    [security](security-operations.md), [capacity](capacity.md) and
    [upgrades](upgrades.md).

</div>

## Status

**0.1.0 release candidate (local, unpublished).** Milestones 1–6 are complete:
functional core, extensibility, RAG, agents, integrations and production
hardening. See the [acceptance report](acceptance-report.md) for the 13 criteria
and final gate evidence.

Publishing registry images, npm/Composer packages and public deployments are
separate, explicitly authorized actions.

## Documentation map

- [Installation](installation.md) · [Configuration](configuration.md) ·
  [Examples](examples.md)
- [Architecture](architecture.md) · [API overview](api.md) ·
  [ADRs](adr/README.md)
- [RAG](rag.md) · [Tools](tools.md) · [Plugins](plugins.md) ·
  [SDKs](integrations.md)
- [Deployment](deployment.md) · [Upgrades](upgrades.md) ·
  [Security](security-operations.md) · [Observability](observability.md)
- [Capacity](capacity.md) · [Releases](releases.md) ·
  [Acceptance report](acceptance-report.md)
