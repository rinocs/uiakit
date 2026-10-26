# Universal AI Kit guide

This guide is the practical, end-to-end path through Universal AI Kit: install it,
configure a model, use the API for chat and RAG, add tools/plugins, integrate an
application, and operate the deployment. It assumes the repository is checked out
locally and Docker is available.

For the documentation map, see [documentation index](documentation-index.md). For every environment
variable, see [configuration.md](configuration.md). For a clean install runbook
and a copy-paste examples page, see [installation.md](installation.md) and
[examples.md](examples.md).

## 1. What the system does

Universal AI Kit is split into a Go gateway and a Python runtime:

- The **gateway** owns the public API, authentication/scopes, assistant versions,
  conversations, run state, SSE delivery, audit and persistence.
- The **runtime** executes one agent turn: it calls the model provider, applies
  directives, retrieves RAG context, runs authorized tools and streams events back.
- The **worker** consumes durable ingestion jobs, parses/chunks documents, builds
  embeddings and activates a Qdrant index version.
- PostgreSQL stores application state; blobs live on the filesystem or an
  S3-compatible bucket; Qdrant is optional and rebuildable.

The supported deployment is **one gateway and one runtime per database**. Two
independent installations are supported; clustering on one database is not.

## 2. Quick start

### 2.1 Create secrets

```bash
cp .env.example .env
python3 - <<'PY'
import hashlib, secrets
from pathlib import Path
path = Path('.env')
text = path.read_text()
key = secrets.token_hex(32)
for name, value in {
    'POSTGRES_PASSWORD': secrets.token_hex(32),
    'INTERNAL_API_KEY': secrets.token_hex(32),
    'UAI_API_KEY_SHA256': hashlib.sha256(key.encode()).hexdigest(),
}.items():
    text = text.replace(name + '=\n', name + '=' + value + '\n')
path.write_text(text)
path.chmod(0o600)
print('Admin API key (store safely):', key)
PY
```

`UAI_API_KEY_SHA256` is a digest; the actual admin key is only printed once. Keep
it in a secret manager. Every secret also accepts a `_FILE` variant.

### 2.2 Select a provider

External OpenAI-compatible endpoint:

```dotenv
MODEL_PROVIDER=openai-compatible
MODEL_BASE_URL=https://api.example.com/v1
MODEL_NAME=your-model
MODEL_API_KEY=<provider-key>
UAI_EGRESS_ALLOW=api.example.com:443
```

Local Ollama:

```dotenv
MODEL_PROVIDER=ollama
MODEL_NAME=llama3.2:3b
OLLAMA_BASE_URL=http://ollama:11434
UAI_EGRESS_ALLOW=ollama:11434
```

For RAG the embedding model must match the index identity (`EMBEDDING_PROVIDER`,
`MODEL`, `VERSION`, `DIMENSION`). The full profile defaults to Ollama
`nomic-embed-text` at 768 dimensions.

### 2.3 Start

```bash
# core: PostgreSQL + runtime + gateway + console
docker compose up -d --build --wait

# full local RAG stack: core + Ollama + Qdrant + worker
docker compose --profile full up -d --build --wait

# local models, after Ollama is healthy
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```

Check readiness:

```bash
curl -fsS http://127.0.0.1:8080/v1/health
```

The gateway waits for PostgreSQL and runtime health, then applies forward-only
migrations before serving. The console is at `http://127.0.0.1:3000` by default.

## 3. Deployment profiles

| Profile | Use |
|---|---|
| default | Core API + console with an external model provider |
| `local-ai` | Core + Ollama; chat only unless Qdrant/worker are also enabled |
| `full` | Core + Ollama + Qdrant + worker; complete local RAG stack |
| `worker` | Add ingestion to an existing core stack |
| `s3` | RustFS fixture for S3-compatible storage |
| `observability` | Separate Compose file with an OTLP collector |

Only publish the gateway (and optionally console) behind a TLS reverse proxy.
Runtime, PostgreSQL and Qdrant must stay on internal networks. See
[deployment.md](deployment.md) for profiles, prerequisites and shutdown.

## 4. API workflow

All authenticated calls use:

```http
Authorization: Bearer <api-key>
Content-Type: application/json
```

`GET /v1/health` is public. `GET /v1/me` returns the effective role and scopes.

### 4.1 Create an assistant

```bash
export UAI_BASE_URL=http://127.0.0.1:8080
export UAI_API_KEY='...'

curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Support assistant",
    "model": "llama3.2:3b",
    "system_prompt": "Answer from the provided context and cite sources."
  }'
```

Assistant updates create immutable versions and require `If-Match` with the
current `ETag`/revision. `GET /v1/assistants/{id}/versions` lists them.

Useful assistant fields include `knowledge_base_ids`, `directives` (for example
`builtin.rag`), `tools`, `limits`, `memory` and `structured_output`. Model
capabilities must support what is requested.

### 4.2 Create a conversation and stream a reply

```bash
curl -s "$UAI_BASE_URL/v1/conversations" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"assistant_id":"<assistant-id>"}'

curl -N "$UAI_BASE_URL/v1/conversations/<conversation-id>/messages" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: first-message' \
  -d '{"content":"Hello"}'
```

SSE frames use `id:`, `event:` and `data:`. Terminal types are
`response.completed`, `agent.failed` and `agent.cancelled`. An EOF without a
terminal event is **not** success. Replaying the same key/content returns the
persisted events; a different body or an active run returns `409`. Failed runs do
not enter the model history.

Cancellation:

```bash
curl -X POST "$UAI_BASE_URL/v1/agent-runs/<run-id>/cancel" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

### 4.3 API groups

| Group | Examples |
|---|---|
| Auth/identity | `/v1/me`, `/v1/credentials` (admin) |
| Assistants/models | `/v1/assistants`, `/v1/assistants/{id}/versions`, `/v1/models` |
| Conversations/runs | `/v1/conversations`, messages, `/v1/agent-runs` |
| Knowledge/document ingestion | `/v1/knowledge-bases`, versions, `/v1/documents`, jobs, export |
| Tools/approvals | `/v1/tools`, `/v1/approvals`, tool executions |
| Plugins/audit/widgets | `/v1/plugins`, `/v1/audit-events`, `/v1/widget/tokens` |

The authoritative contract is
the public OpenAPI contract at `packages/api-contract/public.openapi.json`.
The TypeScript, Go and PHP SDKs are generated/checked against it.

## 5. Authentication, roles and credentials

- The bootstrap admin key is configured through `UAI_API_KEY_SHA256`.
- Persistent credentials can have admin/operator/reader roles and explicit
  scopes, expiry and revocation.
- Resources are owner-scoped; admin access is explicit.
- Widget tokens are short-lived, browser-scoped, bound to assistant/conversation/
  origin, rate-limited and revocable. They never expose admin credentials.
- Admin keys must stay server-side. The console stores only a server-side session;
  the browser never receives the API key.

Create a scoped credential as admin:

```bash
curl -s "$UAI_BASE_URL/v1/credentials" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"principal_id":"ci-reader","role":"reader","scopes":["assistants:read","messages:read"]}'
```

The new key is returned once. Rotate or revoke with the corresponding
`/rotate` and `/revoke` endpoints. See [auth.md](auth.md) for the full scope table.

## 6. RAG workflow

### 6.1 Create a knowledge base

```bash
curl -s "$UAI_BASE_URL/v1/knowledge-bases" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Product docs",
    "config": {"chunk_size": 1000, "chunk_overlap": 200},
    "embedding": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "version": "nomic-embed-text-v1.5",
      "dimension": 768
    }
  }'
```

### 6.2 Upload a document

```bash
curl -s "$UAI_BASE_URL/v1/documents" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -F "knowledge_base_id=<kb-id>" \
  -F "title=Guide" \
  -F "file=@guide.txt"
```

Accepted formats are TXT, Markdown, HTML, PDF and DOCX. The server validates the
real MIME type, hashes the content, stores the blob and creates a durable job.
Poll the job:

```bash
curl -s "$UAI_BASE_URL/v1/documents/<document-id>/job" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

States are `queued`, `running`, `completed`, `failed` and `cancelled`. A failed
job has a stable error code and may be dead-lettered after the retry limit.
The worker recovers expired leases after a crash.

### 6.3 Build/activate the vector index

Creating a new knowledge-base version triggers a reindex. It requires the current
`If-Match` revision and a full config/embedding body:

```bash
curl -s "$UAI_BASE_URL/v1/knowledge-bases/<kb-id>/versions" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "<revision>"' \
  -d '{
    "config": {"chunk_size": 1000, "chunk_overlap": 200},
    "embedding": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "version": "nomic-embed-text-v1.5",
      "dimension": 768
    }
  }'
```

Wait until `GET /v1/knowledge-bases/{id}/versions` shows an `active` version with
`chunk_count > 0` and a `collection_name`. The previous version remains active
until the new index is complete.

### 6.4 Query with citations

Create an assistant with the KB and `builtin.rag`:

```bash
curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "RAG assistant",
    "model": "llama3.2:3b",
    "system_prompt": "Answer from context.",
    "knowledge_base_ids": ["<kb-id>"],
    "directives": ["builtin.rag"]
  }'
```

The completed event contains `payload.citations[]` with citation id, chunk id,
document id/hash/version, page and offsets. Retrieval is filtered by authorized
KB and index version; an empty/invalid ACL fails closed. Objects deleted from a KB
do not come back on reindex.

## 7. Tools, approvals and plugins

- Tools are registered by the host from the trusted registry. There is no public
  "install arbitrary code" endpoint.
- Built-in tools are read-only by default. HTTP tools use operator-defined
  connectors (`base_url`, exact path, method, timeout, secret headers) and are
  subject to SSRF/DNS/redirect controls.
- Mutating tools require a human approval bound to the run, tool, version,
  arguments digest and policy snapshot. Approvals expire and are consumed once.
- Tool executions are reserved with idempotency keys; retries cannot duplicate a
  mutating effect. Unknown outcomes remain explicit and require reconciliation.
- Trusted plugins are installed in the build/environment. Isolated HTTP plugins
  run in a separate container and are activated through the admin API.
- Audit events are transactional, redacted and readable by admins.

See [tools.md](tools.md), [http-tools.md](http-tools.md),
[approvals.md](approvals.md), [tool-executions.md](tool-executions.md),
[plugins.md](plugins.md) and [audit.md](audit.md).

## 8. SDKs, widget and Laravel

- TypeScript: `packages/sdk-typescript` — typed operations, SSE decoder, abort and
  typed errors.
- Go: `packages/sdk-go` — context-aware client and streaming decoder.
- PHP: `packages/sdk-php` — server-side client, SSE stream and Laravel provider.
- Widget: `packages/chat-widget` — Web Component with safe Markdown, citations,
  cancel and accessible keyboard behavior.
- Console: `apps/console` — server-side authenticated SvelteKit UI.

The SDK operation maps are checked against the 45 public OpenAPI operations. See
[integrations.md](integrations.md) and the package READMEs.

Minimal TypeScript flow:

```ts
import { UniversalAIKit } from '@universal-ai-kit/sdk'

const client = new UniversalAIKit({
  baseUrl: 'http://127.0.0.1:8080',
  apiKey: process.env.UAI_API_KEY!,
})
const assistant = await client.assistants.create({
  name: 'App assistant',
  model: 'llama3.2:3b',
  system_prompt: 'Be concise.',
})
const conversation = await client.conversations.create({
  assistant_id: assistant.id,
})
const stream = await client.conversations.sendMessage(
  conversation.id,
  { content: 'Hello' },
  { idempotencyKey: crypto.randomUUID() },
)
for await (const event of stream) {
  if (event.event_type === 'response.completed') {
    console.log(event.payload.text)
  }
}
```

Check the package README for the exact generated method names of the current SDK
version; the public contract is authoritative.

## 9. Operations

### Health and logs

```bash
curl -fsS http://127.0.0.1:8080/v1/health
docker compose ps
docker compose logs -f gateway runtime worker
```

`/v1/health` checks the gateway and PostgreSQL. It does not prove the external
model is reachable; a smoke chat does.

### Graceful shutdown

```bash
docker compose stop gateway
docker compose start gateway
```

The gateway waits for in-flight runs within its grace period. SIGKILL recovery
marks interrupted runs failed with a replayable event. See [capacity.md](capacity.md).

### Backup and restore

```bash
deploy/backup.sh --output backups/$(date -u +%Y%m%dT%H%M%SZ)
deploy/restore.sh --backup backups/<timestamp> --reset-target --start
```

Backups include PostgreSQL and blobs, exclude secrets and Qdrant, and are verified
with checksums. Restore is destructive only with `--reset-target`; Qdrant must be
reindexed. See [backup-restore.md](backup-restore.md).

### Upgrade and rollback

Back up first. Migrations are forward-only. Start PostgreSQL, then the new
gateway (it applies migrations), then runtime/worker. A database schema newer than
the binary is refused. If a rollback needs the old schema, restore the verified
backup with `--reset-target`; there is no automatic down migration. See
[upgrades.md](upgrades.md).

### Two installations

Use distinct `COMPOSE_PROJECT_NAME`, `.env`, ports, credentials and volumes.
`make e2e-two-instances` verifies isolation. Do not share PostgreSQL, blobs or
Qdrant between installations.

### Capacity, observability and security

- Measured baseline and limits: [capacity.md](capacity.md).
- OTLP traces/metrics and redaction: [observability.md](observability.md).
- TLS, secrets, egress, rate limits and hardening:
  [security-operations.md](security-operations.md).
- Release/SBOM/licenses: [releases.md](releases.md) and
  [acceptance-report.md](acceptance-report.md).

## 10. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `/v1/health` 503 | PostgreSQL not ready or unavailable | `docker compose ps`, check postgres logs, wait for health |
| 401 on every call | wrong/revoked admin key or missing scope | verify `UAI_API_KEY_SHA256`, use `/v1/me`, check scopes |
| 409 on a message | different body under same idempotency key, or active run | reuse the original body/key or wait/cancel the run |
| 429 | installation/principal/widget rate limit | wait for the window or raise the intended limit |
| SSE ends without terminal | provider/runtime disconnect or client timeout | replay the idempotency key; inspect gateway/runtime logs |
| `agent.failed` with provider error | model unreachable, bad capability or egress denied | check `MODEL_BASE_URL`, `UAI_EGRESS_ALLOW`, model capability flags |
| RAG returns no citations | index not active, wrong KB/version, ACL or empty retrieval | check active version `chunk_count`, reindex, inspect retrieval logs |
| Job stays queued | worker not running/profile missing | start `--profile full` or `--profile worker` |
| Job failed `document_too_large` | document exceeds 20 MiB or 2M characters | split the document before upload |
| RAG answers without context | assistant has no `knowledge_base_ids`/`builtin.rag` | update the assistant version |
| Upgrade fails at startup | database schema newer than binary or migration error | use the matching binary or restore the backup; inspect gateway logs |
| `docker compose up` starts no worker/Qdrant | optional profile not selected | use `--profile full` |

## 11. Development and tests

```bash
python3 -m venv apps/runtime/.venv
apps/runtime/.venv/bin/pip install -r apps/runtime/requirements-dev.txt \
  packages/core packages/plugin-sdk plugins/examples/hello
PATH="$PWD/apps/runtime/.venv/bin:$PATH" make test
make e2e
```

Useful targets:

```bash
make build-packages
make e2e-upgrade
make e2e-two-instances
make e2e-restore
make test-console-browser
make test-security
make release-dry-run
```

Unit tests require no network or database. Docker E2E uses local mock provider and
tool fixtures, not cloud services. The three opt-in runtime tests for real
Ollama/S3/Qdrant endpoints are skipped when those services are not configured and
are explicitly listed in the acceptance report.

## 12. Current limits

- One gateway + one runtime per database; no HA, distributed run lease or Redis
  rate limiter.
- No automatic down migrations; rollback with a changed schema requires restore.
- Two installations are independent; they cannot share volumes/database.
- Tool/plugin installation is operator-owned; there is no arbitrary code install
  API.
- Model weights, external S3/Ollama services and registry signing/publishing are
  outside this release candidate.
- The release candidate is local; publishing and public deployment require
  separate authorization.
