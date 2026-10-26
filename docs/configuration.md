# Configuration reference

Configuration is environment-driven. The defaults below match `.env.example` and
`compose.yaml`. Secrets should come from a secret manager or mounted files, not
from source control.

## Compose and network

| Variable | Default | Purpose |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `uai` | Prefix for containers, networks and volumes; change it for a second installation |
| `UAI_BIND_ADDRESS` | `127.0.0.1` | Gateway bind address; keep loopback unless a TLS proxy is in front |
| `UAI_PORT` | `8080` | Public gateway port |
| `CONSOLE_BIND_ADDRESS` | `127.0.0.1` | Console bind address |
| `CONSOLE_PORT` | `3000` | Console port |
| `CONSOLE_ORIGIN` | `http://localhost:3000` | SvelteKit origin |
| `POSTGRES_PASSWORD` | required | PostgreSQL password; hex avoids URL-encoding issues |
| `INTERNAL_API_KEY` | required, ≥32 chars | Gateway↔runtime internal authentication |
| `UAI_API_KEY_SHA256` | required for bootstrap | SHA-256 hex of the initial admin API key; may be removed after creating a persistent admin credential |
| `ISOLATED_PLUGIN_TOKEN` | required if isolated plugin profile is used | Bearer token for the isolated plugin protocol |

Every secret supports a mounted-file variant: `POSTGRES_PASSWORD_FILE`,
`INTERNAL_API_KEY_FILE`, `MODEL_API_KEY_FILE`, `EMBEDDING_API_KEY_FILE`,
`UAI_S3_ACCESS_KEY_FILE`, and so on. Set exactly one of the value and the
`_FILE` variant. A file must be absolute, UTF-8, at most 64 KiB and contain one
optional trailing newline.

## Chat model

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_PROVIDER` | `openai-compatible` | `openai-compatible` or `ollama` |
| `MODEL_BASE_URL` | `http://ollama:11434/v1` | OpenAI-compatible base URL (must include the API version prefix expected by the provider) |
| `MODEL_NAME` | `llama3.2:3b` | Model identifier sent to the provider |
| `MODEL_API_KEY` | empty | Provider key; not required for Ollama |
| `MODEL_MAX_TOKENS` | `1024` | Requested completion token limit |
| `MODEL_CONTEXT_WINDOW` | empty | Optional context window used by budgets; empty means unknown |
| `MODEL_TOOL_CALLING` | `false` | Enable only when the model supports OpenAI-compatible tool calls |
| `MODEL_STRUCTURED_OUTPUT` | `false` | Enable only for JSON-schema structured output support |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Native Ollama endpoint used when `MODEL_PROVIDER=ollama` |

Capabilities are declared, not guessed: an unsupported tool-calling, structured
output or streaming request fails with a normalized error instead of being
silently downgraded.

## Embeddings and retrieval

These values are consumed by the worker and by retrieval-capable runtime paths.

| Variable | Default | Purpose |
|---|---|---|
| `EMBEDDING_PROVIDER` | `ollama` | `ollama` or `openai-compatible` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model id |
| `EMBEDDING_VERSION` | `nomic-embed-text-v1.5` | Index version; changing it creates a new vector index |
| `EMBEDDING_DIMENSION` | `768` | Must match the model output |
| `EMBEDDING_BATCH_SIZE` | `32` | Batch size within provider limits |
| `EMBEDDING_BASE_URL` | `http://ollama:11434` | Embedding endpoint |
| `EMBEDDING_API_KEY` | empty | Key for hosted embedding providers |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint used by the worker |
| `UAI_STORAGE_BACKEND` | `filesystem` | `filesystem` or `s3` |
| `UAI_STORAGE_DIR` | `/var/lib/uai/blobs` | Filesystem blob root inside the runtime/worker |
| `UAI_S3_BUCKET` | required for S3 | Operator-provisioned bucket |
| `UAI_S3_ENDPOINT` | empty for AWS | S3-compatible endpoint |
| `UAI_S3_REGION` | `us-east-1` | S3 region |
| `UAI_S3_ACCESS_KEY` / `UAI_S3_SECRET_KEY` | pair for S3 | Credentials |
| `UAI_S3_PREFIX` | empty | Validated key prefix |
| `UAI_WORKER_MAX_ATTEMPTS` | `3` | Retry limit before dead-letter |
| `UAI_WORKER_LEASE_SECONDS` | `300` | Job lease duration |
| `UAI_WORKER_POLL_SECONDS` | `2` | Idle poll interval |

The S3 backend requires the optional `boto3` dependency
(`apps/runtime/requirements-s3.txt`); the default runtime image is
filesystem-only. The bucket, policy and credentials remain operator-owned.

The embedding provider/model/version/dimension form the index identity. Never
change one without creating a new knowledge-base version and reindexing.

## Security and limits

| Variable | Default | Purpose |
|---|---|---|
| `UAI_RATE_LIMIT` | `120` | Installation-wide requests/minute per process |
| `UAI_RATE_LIMIT_PER_PRINCIPAL` | `120` | Requests/minute per principal |
| `UAI_WIDGET_ORIGINS` | empty | Comma-separated exact browser origins allowed for widget SSE; empty disables CORS |
| `UAI_WIDGET_RATE_LIMIT` | `60` | Requests/minute per widget token |
| `UAI_EGRESS_ALLOW` | `ollama:11434` in Compose | Comma-separated `host:port` allowlist for chat, embeddings and isolated plugins; empty denies all, unset disables the check |
| `TOOL_ALLOWED_CONNECTORS` | empty | Comma-separated connector IDs permitted for HTTP tools; empty denies all connector-bound tools |
| `ISOLATED_PLUGIN_URL` | empty | Isolated HTTP plugin base URL |
| `ISOLATED_PLUGIN_TOKEN` | empty | Isolated plugin bearer token |
| `ISOLATED_PLUGIN_MANIFEST` | empty | Approved isolated plugin manifest path |

Rate limits are fixed windows with bounded storage. Going over a limit returns
HTTP 429. There is no shared Redis limiter in the supported single-gateway
deployment.

## Retention and privacy

| Variable | Default | Purpose |
|---|---|---|
| `UAI_RETENTION_CONVERSATION_DAYS` | `0` | Delete old conversations/messages; `0` disables |
| `UAI_RETENTION_AUDIT_DAYS` | `0` | Audit retention; `0` disables |
| `UAI_RETENTION_APPROVAL_DAYS` | `0` | Approval retention; `0` disables |
| `UAI_RETENTION_CLEANUP_DAYS` | `0` | Vector cleanup job retention; `0` disables |

Retention deletes are audited and use tombstones. Backups expire independently;
see the data policy and backup runbook before enabling retention on real data.

## Observability and cost

| Variable | Default | Purpose |
|---|---|---|
| `UAI_OTEL_ENDPOINT` | empty | OTLP/HTTP collector base URL; empty means no-op telemetry |
| `UAI_MODEL_COST_INPUT_PER_MILLION` | empty | Optional USD input price for the cost metric |
| `UAI_MODEL_COST_OUTPUT_PER_MILLION` | empty | Optional USD output price for the cost metric |

Telemetry is fail-open and redacts prompts, messages, tool arguments, headers and
secrets. Cost is emitted only when prices are explicitly configured; no price is
invented.

## Profiles

| Command | Services |
|---|---|
| `docker compose up -d --wait` | postgres, runtime, gateway, console |
| `docker compose --profile local-ai up -d --wait` | core + Ollama |
| `docker compose --profile full up -d --wait` | core + Ollama + Qdrant + worker |
| `docker compose --profile worker up -d --wait` | core + worker |
| `docker compose --profile s3 up -d --wait` | core + RustFS fixture |
| `docker compose -f compose.yaml -f deploy/observability/compose.observability.yaml --profile observability up -d` | core + OTLP collector |

`core` is the default service set, not a separate Compose profile. The `full`
profile is the supported local RAG stack; `local-ai` alone provides chat without
Qdrant/ingestion. The console is always part of the default set.

## Two installations

Use two project names, `.env` files, ports and credentials:

```dotenv
# installation A
COMPOSE_PROJECT_NAME=uai-a
UAI_PORT=8080
CONSOLE_PORT=3000

# installation B
COMPOSE_PROJECT_NAME=uai-b
UAI_PORT=8081
CONSOLE_PORT=3001
```

Compose creates separate networks and volumes from the project name. Never share
PostgreSQL, blob storage or Qdrant between installations. `docker compose down`
keeps volumes; `down -v` destroys them.
