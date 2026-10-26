# Data retention and privacy

The authoritative source of the data is PostgreSQL; the vector indices are
rebuildable and are never the only copy. Semantic memory is disabled:
`MemoryConfig.semantic` is `const false` in the contract and there is no store
automatic semantic. Working memory is the history of the conversation
(`messages` + run), cancelable with conversation or retention.

## Data classes

| Class | Where | Cancellation | Default |
|---|---|---|---|
| Conversations, messages, runs, approvals | PostgreSQL | `DELETE /v1/conversations/{id}` or retention | disabled |
| Documents and metadata | PostgreSQL | `DELETE /v1/documents/{id}` | until explicitly deleted |
| Chunk | PostgreSQL | document cascade | until explicitly deleted |
| Vectors | Qdrant | `vector_cleanup_jobs` after delete document/reindex | repeatable garbage collection |
| Document Blobs | local storage/S3 | delete document + cleanup | until explicitly deleted |
| Ingestion Job | PostgreSQL | document cascade; cleanup vector | until explicitly deleted |
| Approvals | PostgreSQL | run cascade; retention by status/expiry | 0 days (disabled) |
| Audits | PostgreSQL | configurable retention; details redacted | 0 days (disabled) |
| Tombstone | PostgreSQL | non-sensitive record (`id`, type, date, author, reason) | preserved |

`0` means **automatic retention disabled**. A real deployment must
explicitly choose values; there are no defaults that delete data
silently.

## Configuration

```dotenv
UAI_RETENTION_CONVERSATION_DAYS=0
UAI_RETENTION_AUDIT_DAYS=0
UAI_RETENTION_APPROVAL_DAYS=0
UAI_RETENTION_CLEANUP_DAYS=0
```

Retention is performed by the gateway process via:

```http
POST /internal/v1/retention/run
Authorization: Bearer <INTERNAL_API_KEY>
```

It is idempotent, protected by an advisory lock, and returns counts per class.
It can be called from an external scheduler (cron/Kubernetes) or from a job
operational. It is not exposed to the browser and does not require a public API key.

## Manual deletion

- Conversation: requires `conversations:write`, ownership and no run
  `running`. Delete linked messages, runs, approvals and tool execution;
  writes a `conversation` tombstone and a `conversation.deleted` audit.
- Document: requires ownership and `documents:write`. Delete metadata, chunks,
  jobs and blobs; Append vector removal with chunk IDs. The tombstone
  `document` prevents the same ID from returning from a reindex.
- Knowledge base: requires ownership, no documents and no assistants
  the reference. Delete versions and chunks and write a tombstone.

Tombstones do not contain prompts, text, URLs, headers, or secrets. They are used to
make the deletion traceable and avoid the reappearance of identifiers.

## Garbage collection of vectors

The delete document inserts a `vector_cleanup_jobs` with known chunk IDs. The
workers:

1. try to delete points from Qdrant;
2. on error retry with lease and backoff (up to `max_attempts`);
3. mark the job `completed` only after deletion, otherwise `failed`.

`UAI_RETENTION_CLEANUP_DAYS` retention deletes `completed`/`failed` jobs
old; does not delete pending jobs. A reindex does not reinsert deleted documents
because the `documents`/`document_chunks` lines no longer exist.

## Audits

The audit is already minified and redacted: no prompts, messages, headers, tokens or
secrets. The retention audit eliminates events older than the threshold
configured; the `retention.applied` event only retains the counts. To use
real data, the retention audit must be compatible with the obligations
contractual and with backup retention.

## Backups

Deleting the database does not delete copies in already created backups. First
to use real data:- set a backup expiry (`backup expiry`) not exceeding the policy
  of declared retention;
- document the restore procedure and its expiration date;
- verify that a restore does not reactivate deleted conversations/documents
  without a reconciliation procedure.

Operational backup/restore verification is in [backup-restore.md](backup-restore.md).
Retention defaults remain disabled until a deployment configures them
explicitly.

## Roles

- `reader`: no deletion.
- `operator`/`admin`: delete resources they own or administer.
- `admin`: internal retention only via `INTERNAL_API_KEY`, not via token
  browser.
- `widget`: no access to delete, retention, audit or credentials.

## Test

- `tests/e2e/check_deletion.py`: delete conversation, tombstone, audit,
  disappearance of messages/runs, idempotent retention.
- `tests/e2e/check_ingest.py`: delete document during flow
  ingestion/reindex, chunk and vector removal, export without deleted source.
- `make e2e`: also checks `015_retention.sql` migration, tombstones and
  retention for conversations, approvals, audits and cleanup jobs.