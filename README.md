# Universal AI Kit

**Self-hosted, Docker-first AI platform for chat, RAG, tools and agents.**

Universal AI Kit exposes a versioned HTTP API and SSE streaming on top of a Go
gateway and a Python runtime. It is designed for teams that want to add an AI
assistant to an application without giving up control of data, credentials,
models, retrieval or deployment.

> Status: **0.1.0 release candidate (local, unpublished)**. Milestones 1–6 are
> complete: functional core, extensibility, RAG, agents, integrations and
> production hardening. Publishing images/SDKs and public deployment are
> separate, explicitly authorized actions.

## Why Universal AI Kit

- **Self-hosted by default** — PostgreSQL, filesystem/S3-compatible blob storage
  and optional Qdrant; no cloud service is mandatory.
- **Provider-neutral** — OpenAI-compatible chat/embeddings or native Ollama.
- **RAG with provenance** — versioned knowledge bases, document jobs, chunk
  offsets, filtered retrieval and verifiable citations.
- **Agent-safe tools** — scoped tool registry, HTTP connectors with SSRF
  protection, human approvals, idempotent effects and transactional audit.
- **Operable** — graceful shutdown, durable jobs and recovery, bounded rate
  limits, retention, backups, observability and upgrade/rollback runbooks.
- **Integration-ready** — TypeScript, Go and PHP SDKs, a Web Component widget,
  a SvelteKit console, Laravel integration and a FastAPI widget adapter.

## Architecture

```text
Browser / SDK / Laravel
        |
        v
  Go gateway :8080  ──────────────┐
  auth, scopes, runs, SSE,        │
  persistence, rate limit         │
        |                         │
        v                         v
  Python runtime :8000       PostgreSQL
  agent loop, providers,     runs, messages,
  retrieval, tools, plugins  KBs, jobs, audit
        |                         ^
        v                         |
  OpenAI-compatible / Ollama      |
  chat + embeddings               |
                                  |
  Worker ── ingestion ── chunks ──┘
        |
        v
  Qdrant (optional)
```

| Component | Role |
|---|---|
| `apps/gateway` | Public API, authentication/scopes, assistant versions, conversations, SSE, runs, audit, rate limits |
| `apps/runtime` | Agent execution, provider adapters, directives, retrieval, tool calls and structured output |
| `apps/worker` | Durable document ingestion, chunking, embedding, Qdrant index build and vector cleanup |
| `packages/core` | Shared Python contracts for execution, RAG, budgets and providers |
| `apps/console` | Server-side authenticated SvelteKit admin console |
| `packages/chat-widget` | Framework-agnostic Web Component chat UI |
| `packages/sdk-*` | TypeScript, Go and PHP clients for the public OpenAPI contract |

## Quick start

### Requirements

- Docker Engine 29+ and Docker Compose v2
- 2 vCPU / 4 GB RAM for the core profile; more for local models and Qdrant
- An OpenAI-compatible chat endpoint, or the local Ollama profile

### 1. Create local secrets

```bash
python3 scripts/bootstrap.py
```

The admin key is returned only here; the `.env` file stores its SHA-256 digest.
Every secret also supports a `_FILE` variant (for example
`INTERNAL_API_KEY_FILE=/run/secrets/internal_api_key`). Never set both.

### 2. Choose a model

**External OpenAI-compatible provider**

```dotenv
MODEL_PROVIDER=openai-compatible
MODEL_BASE_URL=https://api.example.com/v1
MODEL_NAME=your-model
MODEL_API_KEY=<provider-key>
UAI_EGRESS_ALLOW=api.example.com:443
```

**Local Ollama (full profile)**

```dotenv
MODEL_PROVIDER=ollama
MODEL_NAME=llama3.2:3b
OLLAMA_BASE_URL=http://ollama:11434
UAI_EGRESS_ALLOW=ollama:11434
```

### 3. Start the stack

```bash
# Core: PostgreSQL + runtime + gateway + console
docker compose up -d --build --wait

# Full local stack: core + Ollama + Qdrant + worker
docker compose --profile full up -d --build --wait

# Pull the local models after Ollama is healthy
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```

The gateway waits for PostgreSQL and runtime health before serving traffic and
applies forward-only migrations on startup. The default console is bound to
`127.0.0.1:3000`; the API is bound to `127.0.0.1:8080`.

```bash
curl -fsS http://127.0.0.1:8080/v1/health
```

### 4. Create an assistant and send a message

```bash
export UAI_API_KEY='the key printed above'
export UAI_BASE_URL='http://127.0.0.1:8080'

curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Guide assistant","model":"llama3.2:3b","system_prompt":"Answer clearly."}'

# Copy the returned id
export ASSISTANT_ID='UUID'

curl -s "$UAI_BASE_URL/v1/conversations" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"assistant_id\":\"$ASSISTANT_ID\"}"

# Copy the returned id
export CONVERSATION_ID='UUID'

curl -N "$UAI_BASE_URL/v1/conversations/$CONVERSATION_ID/messages" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: first-message' \
  -d '{"content":"Hello!"}'
```

The stream ends with `response.completed`, `agent.failed` or `agent.cancelled`.
An EOF without a terminal event is not success. Reusing the same idempotency key
and content replays the persisted events; a different body or an active run
returns `409`. Failed runs are not added to the model history.

## Documentation

Start with:

- **[Installation guide](docs/installation.md)** — clean install, secrets, providers,
  profiles, verification and production checklist.
- **[Documentation index](docs/documentation-index.md)** — reading paths by audience.
- **[Complete guide](docs/guide.md)** — usage, RAG, tools, SDKs, operations and
  troubleshooting.
- **[Examples](docs/examples.md)** — copy-paste API, RAG, tools, widget, SDK and
  operations examples.
- **[Configuration reference](docs/configuration.md)** — environment variables,
  profiles and secret handling.

The documentation site uses MkDocs Material, matching the dark Slate/Indigo
layout, search, navigation tabs and code-copy controls. Run it locally:

```bash
python3 -m pip install -r requirements-docs.txt
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict # static output in site/
```

The GitHub Pages workflow builds and deploys the site from `main`; the built
`site/` directory is not committed.

Operational references:

- [Deployment](docs/deployment.md) · [Upgrades and rollback](docs/upgrades.md)
- [Capacity and recovery](docs/capacity.md) · [Releases](docs/releases.md)
- [Acceptance report](docs/acceptance-report.md) · [Release notes](RELEASE_NOTES.md)
- Public API contract: `packages/api-contract/public.openapi.json`

## Common commands

```bash
make test                 # unit, contract, security, capacity and release checks
make build-packages       # SDKs, widget, console, plugin
make e2e                  # real Docker/PostgreSQL E2E
make e2e-upgrade          # schema upgrade, graceful shutdown, refusal of newer schema
make e2e-two-instances    # two independent stacks
make e2e-restore          # backup + isolated restore + reindex
make test-console-browser # Playwright browser/accessibility suite
make release-dry-run      # SBOM, packages, versioned image archives, manifest, checksums
```

Python tests use `apps/runtime/.venv`:

```bash
python3 -m venv apps/runtime/.venv
apps/runtime/.venv/bin/pip install -r apps/runtime/requirements-dev.txt \
  packages/core packages/plugin-sdk plugins/examples/hello
PATH="$PWD/apps/runtime/.venv/bin:$PATH" make test
```

The unit suites require no network or database. The Docker E2E uses local
`mock-provider`/`mock-tool` fixtures and does not call external models.

## Security and current limits

- Admin/operator/reader roles and scopes with per-principal ownership. Admin keys
  must never reach browser code; widget tokens are scoped, expiring and revocable.
- Only loopback ports are published by default. For remote exposure use the TLS
  reverse-proxy example in `deploy/reverse-proxy/nginx.conf.example`; never expose
  runtime, PostgreSQL or Qdrant directly.
- `UAI_EGRESS_ALLOW` constrains chat, embedding and isolated-plugin egress.
  HTTP tools validate connector base URLs, paths, pinned DNS and private networks.
- Rate limits are bounded per process, per principal and per widget token.
- Default limits: 120 requests/min per process and per principal, 128 KiB JSON
  body, 32,000-byte message, 64,000-byte context/output, 100 history messages,
  120 s run duration, 30 s provider timeout. Limits are not implicit truncation:
  start a new conversation or raise the appropriate limit deliberately.
- The supported deployment is **one gateway and one runtime per database**.
  There is no distributed rate limiter or run lease. Two independent
  installations are supported; HA on one database is not.
- Data remains in PostgreSQL/blob volumes until retention or an explicit delete.
  Configure retention and backups before using real data.
- Three opt-in tests are skipped without real Ollama/S3/Qdrant endpoints; they
  are listed in the acceptance report and are not counted as passes.

## Repository layout

```text
apps/gateway      Go public API and gateway
apps/runtime      Python execution runtime
apps/worker       durable ingestion worker
apps/console      SvelteKit admin console
packages/         core contracts, SDKs, widget
plugins/          trusted and isolated plugin examples
deploy/           Dockerfiles, backup/restore, reverse proxy, observability
docs/             guides, reference, ADRs, plans and acceptance report
tests/            unit, contract, security, performance and E2E suites
```

## Supported feature limits

The model-driven agent loop currently executes read-only builtin/HTTP tools.
Approvals and durable write execution exist separately; automatic approval/resume
is not a complete agent workflow. Skills and semantic memory are not selectable;
MCP is not implemented. Plugins require host approval and installation at build
time; there is no ZIP marketplace or hot reload. Only one gateway/runtime pair
per database is supported. These limits also apply to the release candidate.

## License and release status

First-party code, SDKs and examples are licensed under **[GPL-3.0-only](LICENSE)**.
Commercial use is allowed; redistribution of covered derivatives must satisfy the
GPL, including corresponding source. Calling the HTTP API from an independent
application does not automatically license that application under GPL; incorporating
our SDK code can create different obligations. See [licensing](docs/licensing.md).
Dependencies and model weights retain their own licenses. Hosting, inference and
managed support may cost money even though the source is free.

Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). Private vulnerability reports:
[SECURITY.md](SECURITY.md).

The 0.1.0 release candidate is prepared locally in `release/` and is **not
published**. Registry pushes, npm/Composer publishing, signing and public
deployment require separate authorization.
