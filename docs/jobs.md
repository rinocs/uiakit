# Durable workers and jobs
The worker transforms the uploaded documents into persistent chunks, using PostgreSQL
as an authoritative source of status, lease and retry. It doesn't use Redis or an in queue
memory: a crash does not lose the job and multiple workers can share the database.

## States

```text
queued ──claim──> running ──success──> completed
  ^ │
  └──retryable───────┤
                     └──permanent/limite──> failed (dead-letter)
queued/running ──cancel──> cancelled
```

- `document_jobs` holds `state`, `attempts`, `error_code`, `lease_owner`,
  `lease_until`, `dead_lettered_at` (migration 008).
- `failed` after the maximum number of attempts is the inspectable dead-letter
  API; is not automatically retried.
- `cancelled` is terminal and the worker does not publish chunks.

## Claim, lease and crash recovery

The claim is a single transactional query:

```sql
WITH candidate AS (
  SELECT id FROM document_jobs
  WHERE state='queued'
     OR (state='running' AND (lease_until IS NULL OR lease_until < now()))
  ORDER BY created_at,id
  FOR UPDATE SKIP LOCKED LIMIT 1
)
UPDATE document_jobs ... RETURNING ...
```

- Two workers do not receive the same job: `SKIP LOCKED` and lease owner.
- A crashed worker leaves `running` with an expired lease; another worker does
  claims and increments `attempts`.
- The final write (chunk + `completed`) rechecks `state='running'` and
  `lease_owner`: if the lease was lost or the job canceled, do not publish
  nothing.
- The lease is not renewed during parsing; the default is 300 seconds.
  Very slow documents can be claimed after the deadline; protection
  final prevents duplicate publications.

## Retry, dead-letter and chunk

- Permanent errors (`CorruptDocument`, `UnsupportedDocument`, `DocumentLimit`,
  `UnsupportedBackend`, `ChunkingError`, blob missing) → immediate `failed` with
  Stable `error_code`.
- Transient errors (storage/DB/worker) → `queued` until `attempts <
  UAI_WORKER_MAX_ATTEMPTS` (default 3), then `failed` + `dead_lettered_at`.
- Chunks are inserted with `ON CONFLICT (chunk_id) DO NOTHING`: a retry or a
  crash after insert does not duplicate chunk. The IDs are the stable ones of M3-05.
- The worker reads the `chunk_size`/`chunk_overlap` config from the active version
  of the KB (M3-01) and the blob from the shared storage.

## Status and cancellation API

They use existing scope documents; no new scope.

| Method | Path | Roles | Effect |
| --- | --- | --- | --- |
| GET | `/v1/documents/{id}/job` | documents:read | Status, attempts, error and dead-letter for owner/admin |
| POST | `/v1/documents/{id}/job/cancel` | documents:write | Delete a queued/running job; 409 if terminal |

A resource from another principal returns 404. The deletion is repeatable
on an already `cancelled` job; a `completed`/`failed` job returns 409.

## Worker

`apps/worker/uai_worker`:

- `JobStore`: claim/load/insert+complete/fail on PostgreSQL.
- `JobWorker`: parse (M3-04), chunk (M3-05), idempotent insert and transition
  state.
- `main`: loop with SIGTERM/SIGINT, `UAI_WORKER_ONCE=1` for a single loop.

Variables:

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | mandatory | Authoritative PostgreSQL |
| `UAI_WORKER_MAX_ATTEMPTS` | 3 | maximum retry before dead-letter |
| `UAI_WORKER_LEASE_SECONDS` | 300 | claim lease |
| `UAI_WORKER_POLL_SECONDS` | 2 | pause when there are no jobs |
| `UAI_STORAGE_BACKEND` / `UAI_STORAGE_DIR` | filesystem | same storage as the runtime |
| `UAI_WORKER_ID` | hostname:pid | lease identity |

Starting in Compose: `docker compose --profile worker up -d worker`. The volume
`blob-data` is shared with the runtime; the worker does not expose ports.

## Limits

- Single authoritative database/Postgres; no Redis required.
- Fixed lease without heartbeat; the default covers normal documents.
- The embedding/Qdrant pipeline and atomic switch of the index version are
  M3-07…M3-09.
- No contents of the document are logged; only ID, status and error code.
- Cancellation does not interrupt a parse already in progress: it prevents the
  publishing chunks on final commit.## Evidence

- `apps/gateway/jobs_test.go`: status, cross-owner access, idempotent cancel and
  409 on terminal.
- `apps/worker/tests/test_jobs.py`: published chunks, permanent error,
  transient storage, cancellation/lease lost, empty claim.
- `make e2e`: real worker on PostgreSQL/runtime/storage with:
  PDF/DOCX completion, deletion honored, job `running` with lease
  expired recovered, retry of a completed job without duplicating chunk.
- Evidence: `make test` 221 Python runtime + 8 workers + 3 skipped, Go race/vet;
  `make e2e` complete.