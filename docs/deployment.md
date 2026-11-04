# Deployment

Universal AI Kit installs with Docker Compose. The supported deployment is
**one gateway instance + one database runtime**; two independent installations
are supported, clustering with multiple gateways on the same database is not.

## Prerequisites

- Docker Engine 29+ and Docker Compose v2.
- 2 vCPU and 4 GB RAM for the core profile; increase for local models, Qdrant and
  workers. The measured baseline is in [capacity.md](capacity.md).
- An OpenAI-compatible model endpoint with `chat` and `streaming` (optional
  `tool_calling`, `structured_output`, embeddings). For Ollama use profile
  `local-ai` or `full`.
- An embedding model with known size/version if using RAG. The weights of
  model have a separate license from the software: check it before
  distribution.
- Free loopback ports for gateway (default 8080) and console (default 3000).
- Disk space for PostgreSQL, blob and, if active, Qdrant. Backups and retention
  They are in [backup-restore.md](backup-restore.md) and [data-policy.md](data-policy.md).

## Clean installation

```bash
python3 scripts/bootstrap.py # new installations only
# generate at least POSTGRES_PASSWORD and INTERNAL_API_KEY
# set UAI_API_KEY_SHA256 = sha256 of the admin API key, or use the
# bootstrap credential expected from auth.md
```

Fill in the provider values in the `.env` (`MODEL_BASE_URL`, `MODEL_NAME`,
`MODEL_API_KEY`, `UAI_EGRESS_ALLOW`) and launch the chosen profile:

```bash
# core: PostgreSQL + runtime + gateway (+ console if needed)
docker compose up -d --wait postgres runtime gateway

# core with console
docker compose up -d --wait postgres runtime gateway console

# Ollama local model (chat; RAG also requires Qdrant/worker)
docker compose --profile local-ai up -d --wait

# full: Ollama + Qdrant + worker + basic services
docker compose --profile full up -d --wait

# S3-compatible storage
docker compose --profile s3 up -d --wait

# observability (separate Compose file)
docker compose -f compose.yaml \
  -f deploy/observability/compose.observability.yaml \
  --profile observability up -d
```

`gateway` waits for PostgreSQL and the sane runtime before starting; the runtime waits
the fixtures/providers declared by the profile. The `--wait` command is the way
supported to check availability.

```bash
curl -fsS http://127.0.0.1:8080/v1/health
```

Then create an assistant and conversation via API/console. The console uses
the same API key only on the server side: do not insert it into browser code.

## Profiles

| Profile | Services | Usage |
|---|---|---|
| core (default) | postgres, runtime, gateway, console | API/chat with external provider |
| `local-ai` | core + ollama | local chat model; RAG not complete |
| `full` | core + ollama + qdrant + worker | full local stack, including ingestion/RAG |
| `worker` | workers | ingestion separated from the core profile |
| `s3` | rustfs | fixture/storage S3-compatible |
| `observability` | OTLP collector (separate compose) | optional trace/metrics |

`core` is not a separate Compose profile: it is the set of services without profiles
optional. Don't start Qdrant, worker or Ollama if you don't need them: they reduce surface area
and consumption.

## Graceful shutdown

Gateway, runtime and worker have `stop_grace_period` and handle SIGTERM:

- the gateway waits up to 140 s for the completion of the runs in progress, then closes;
- the runtime waits for the connections/providers to close;
- the worker completes the current job or lets the lease expire.

```bash
docker compose stop gateway # wait for grace period
docker compose start gateway
```

A run interrupted by a crash (SIGKILL) is marked `failed` upon restart with event
`agent.failed` code `gateway_restarted`, replayable; an orderly arrest
retains the completed terminal. The `tests/e2e/check_upgrade.py` test checks
both.

`docker compose down` preserves volumes. **`docker compose down -v` is destructive**
and delete databases, blobs and Qdrant: only use it after an explicit backup.## Two installations

Two independent instances require:

- `COMPOSE_PROJECT_NAME` different;
- different `.env` with separate credentials and `UAI_API_KEY_SHA256`;
- `UAI_PORT` (and `CONSOLE_PORT`) different;
- separate volumes/network, which Compose creates from the project name.

Do not share your database, blob volume, or Qdrant between the two. The suite
`make e2e-two-instances` starts two concurrent stacks and checks for isolation
credentials, assistants, volumes and network. The operational detail is in
[upgrades.md](upgrades.md).

## Limits declared

- A database gateway and runtime; no distributed leases per run.
- Rate limit per process, not distributed Redis.
- No installation of plugins or code via API.
- The console is a server-side client, not a multi-tenant panel.