# Installation guide

This guide installs Universal AI Kit 0.1.0 with Docker Compose. It covers a clean
local installation, an external OpenAI-compatible provider, the local Ollama/RAG
stack, verification and the first conversation.

## 1. Prerequisites

- Docker Engine 29+ with Compose v2.
- 2 vCPU and 4 GB RAM for the core stack; more for local models and Qdrant.
- Free loopback ports for the gateway (`8080`) and console (`3000`).
- An OpenAI-compatible chat endpoint, or Docker access to pull the Ollama image
  and model weights.
- An embedding model if you want RAG; the full profile defaults to Ollama
  `nomic-embed-text`, 768 dimensions.
- A secret manager or protected host filesystem for `.env`.

Verify Docker:

```bash
docker version
docker compose version
```

Keep runtime, PostgreSQL and Qdrant on internal networks. Publish only the
gateway (and console) behind a TLS reverse proxy in production.

## 2. Get the project

```bash
git clone <repository-url> universal-ai-kit
cd universal-ai-kit
```

If you received a release bundle, unpack it and use the source archive or the
checked-out repository. The version is in `VERSION` and must match the image tags
in `compose.yaml` (`0.1.0` by default).

## 3. Create `.env`

```bash
cp .env.example .env
```

Generate the required secrets and the bootstrap admin key:

```bash
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
print('Admin API key (store it now; it is shown once):', key)
PY
```

Rules:

- `POSTGRES_PASSWORD` and `INTERNAL_API_KEY` are hex secrets; the PostgreSQL URL
  is built from them.
- `UAI_API_KEY_SHA256` is the SHA-256 of the admin key. The plaintext key is only
  printed by the command above.
- Every secret supports a mounted-file variant: `POSTGRES_PASSWORD_FILE`,
  `INTERNAL_API_KEY_FILE`, `MODEL_API_KEY_FILE`, `EMBEDDING_API_KEY_FILE`,
  `UAI_S3_ACCESS_KEY_FILE`, and so on. Set either the value or the `_FILE`
  variant, never both.
- Never commit `.env`.

## 4. Configure the model

### OpenAI-compatible provider

```dotenv
MODEL_PROVIDER=openai-compatible
MODEL_BASE_URL=https://api.example.com/v1
MODEL_NAME=your-model
MODEL_API_KEY=<provider-key>
UAI_EGRESS_ALLOW=api.example.com:443
```

`MODEL_BASE_URL` must include the version prefix expected by the provider
(usually `/v1`). `UAI_EGRESS_ALLOW` is an exact `host:port` allowlist; an empty
value denies all outbound provider endpoints, while unset disables the check. Set
it explicitly in production.

### Local Ollama

```dotenv
MODEL_PROVIDER=ollama
MODEL_NAME=llama3.2:3b
OLLAMA_BASE_URL=http://ollama:11434
UAI_EGRESS_ALLOW=ollama:11434
```

The environment configuration bootstraps the runtime. After logging in, an
administrator can change the provider kind, base URL, max output tokens and the
model catalog from `/provider`. Secret values stay in the runtime environment or
mounted files (`MODEL_API_KEY` or `PROVIDER_API_KEY_*`) and are referenced by name;
the runtime egress allowlist still applies.

The `full` profile also runs the worker and Qdrant. For RAG, keep the embedding
identity consistent with the model actually pulled:

```dotenv
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_VERSION=nomic-embed-text-v1.5
EMBEDDING_DIMENSION=768
EMBEDDING_BASE_URL=http://ollama:11434
```

### Capabilities

Enable only what the model actually supports:

```dotenv
MODEL_TOOL_CALLING=false
MODEL_STRUCTURED_OUTPUT=false
MODEL_CONTEXT_WINDOW=
MODEL_MAX_TOKENS=1024
```

Universal AI Kit does not silently downgrade an unsupported capability; the
request fails with a normalized error.

## 5. Choose a profile

| Profile | Command | Services |
|---|---|---|
| Core | `docker compose up -d --build --wait` | PostgreSQL, runtime, gateway, console |
| Local chat | `docker compose --profile local-ai up -d --build --wait` | Core + Ollama |
| Full local RAG | `docker compose --profile full up -d --build --wait` | Core + Ollama + Qdrant + worker |
| Add worker | `docker compose --profile worker up -d --wait` | Core + ingestion worker |
| S3 fixture | `docker compose --profile s3 up -d --wait` | Core + RustFS |
| Observability | `docker compose -f compose.yaml -f deploy/observability/compose.observability.yaml --profile observability up -d` | Core + OTLP collector |

`core` is the default service set, not a separate Compose profile. The gateway
waits for PostgreSQL and runtime health and applies forward-only migrations before
serving.

## 6. Start and verify

```bash
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:8080/v1/health
docker compose ps
```

For the full local stack:

```bash
docker compose --profile full up -d --build --wait
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
curl -fsS http://127.0.0.1:8080/v1/health
```

Health checks the gateway and PostgreSQL, not the external model. Send a real
smoke message to verify the provider.

Check the migration version:

```bash
docker compose exec -T postgres psql -U uai -d uai -tAc \
  'SELECT max(version) FROM schema_migrations'
```

## 7. First assistant and message

```bash
export UAI_BASE_URL=http://127.0.0.1:8080
export UAI_API_KEY='the key printed in step 3'

curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Install test","model":"llama3.2:3b","system_prompt":"Answer briefly."}'
```

Copy the returned assistant id, create a conversation, then stream:

```bash
export ASSISTANT_ID='UUID'

curl -s "$UAI_BASE_URL/v1/conversations" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"assistant_id\":\"$ASSISTANT_ID\"}"

export CONVERSATION_ID='UUID'

curl -N "$UAI_BASE_URL/v1/conversations/$CONVERSATION_ID/messages" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: install-smoke-1' \
  -d '{"content":"Hello from the installation guide"}'
```

The stream ends with `response.completed`. An EOF without a terminal event is not
success. See [examples.md](examples.md) for replay, cancel, RAG and SDK examples.

## 8. Console

Open `http://127.0.0.1:3000` and log in with the admin API key. The console keeps
the key server-side in an opaque session; it never sends the key to the browser.
A reader credential can inspect data without mutation rights.

If the console is exposed remotely, set `CONSOLE_ORIGIN` and put it behind the
same TLS reverse proxy as the gateway.

## 9. Production checklist

- [ ] `.env` is mode `0600`, outside version control and backed by a secret manager.
- [ ] Admin bootstrap hash is removed after creating a persistent admin credential.
- [ ] `UAI_EGRESS_ALLOW` explicitly lists only the required provider hosts.
- [ ] Only gateway/console ports are published; runtime/PostgreSQL/Qdrant are internal.
- [ ] TLS reverse proxy and HSTS are configured (`deploy/reverse-proxy/nginx.conf.example`).
- [ ] Retention (`UAI_RETENTION_*`) is decided before loading real data.
- [ ] Backup schedule and restore test are in place (`deploy/backup.sh`).
- [ ] Rate limits match expected traffic; no distributed limiter is assumed.
- [ ] Model, embedding and tooling licenses are reviewed.
- [ ] `make e2e`, `make e2e-upgrade`, `make e2e-restore` pass on the deployment host.
- [ ] The deployment remains single-gateway/single-runtime per database.

## 10. Operate

```bash
docker compose logs -f gateway runtime worker
docker compose stop gateway       # graceful shutdown
docker compose start gateway
docker compose down               # keeps volumes
docker compose down -v            # DESTRUCTIVE: deletes database and blobs
```

Backup and upgrade:

```bash
deploy/backup.sh --output backups/$(date -u +%Y%m%dT%H%M%SZ)
deploy/restore.sh --backup backups/<timestamp> --reset-target --start
```

See [deployment.md](deployment.md), [upgrades.md](upgrades.md) and
[backup-restore.md](backup-restore.md).

## 11. Two independent installations

Use separate project names, ports, credentials and volumes:

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

Never share PostgreSQL, blob volumes or Qdrant between installations.
`make e2e-two-instances` verifies the isolation boundary.

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| `docker compose up` fails interpolation | required variables in `.env`; missing `POSTGRES_PASSWORD`, `INTERNAL_API_KEY`, `RUSTFS_*` |
| Gateway restarts/unhealthy | `docker compose logs gateway`; PostgreSQL health; schema version |
| `/v1/health` is 503 | PostgreSQL readiness and credentials |
| 401 | key/digest mismatch, revoked credential or missing scope |
| 429 | rate limit; wait for the window or raise the intended limit |
| Model errors | `MODEL_BASE_URL`, `MODEL_NAME`, provider key, `UAI_EGRESS_ALLOW`, capability flags |
| RAG has no citations | worker/Qdrant profile, active KB version with `chunk_count > 0`, embedding match |
| Console login fails | API key, `CONSOLE_ORIGIN`, browser cookies, gateway health |

For deeper diagnosis see [guide.md](guide.md#10-troubleshooting) and
[observability.md](observability.md).

## 13. Uninstall

```bash
docker compose down       # stop containers, keep data
docker compose down -v    # stop and delete volumes (irreversible)
rm -f .env
```

Create a verified backup before any destructive action.
