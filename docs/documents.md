# Documents and uploads
Validated upload and authoritative metadata for the RAG pipeline. The blob is preserved
from the storage runtime ([storage.md](storage.md)); PostgreSQL preserves document,
hash, minimal provenance and job. Parsing is implemented in M3-04
([parsing.md](parsing.md)); chunking with stable offsets/IDs in M3-05
([chunking.md](chunking.md)); index/worker are M3-06/M3-09.

## API

Scope: `documents:read` for reading, `documents:write` for upload/delete. Existing credentials do not acquire scopes automatically. Owner of KB
or admin can operate; someone else's KB returns 404.

| Method | Path | Effect |
| --- | --- | --- |
| GET | `/v1/documents` | Lists accessible documents; optional filter `knowledge_base_id` |
| POST | `/v1/documents` | Multipart upload and atomic creation of document + job |
| GET | `/v1/documents/{id}` | Metadata and `ingestion_state` |
| DELETE | `/v1/documents/{id}` | Delete metadata, jobs and blobs |

Multipart upload:

```http
POST /v1/documents
Authorization: Bearer <operator-key>
Content-Type: multipart/form-data; boundary=...

knowledge_base_id=<uuid>
title=Manual # optional, default filename
file=@manuale.pdf;type=application/pdf
```

Response `201` with `Document`. A second upload with the same SHA-256 in the
**same KB** returns `200` and `X-Deduplicated: true`, no new blob or job.
The same hash in another KB creates a separate document and does not reveal its existence
elsewhere.

## Validation

- Maximum size: 20 MiB per file (the multipart body has a margin of 1 MiB).
- MIME declared in multipart, normalized and compared to sniff
  server-side (`http.DetectContentType`/magic header).
- Allowlist: `text/plain` (TXT), `text/markdown` (MD), `text/html` (HTML),
  `application/pdf` (PDF), DOCX (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`).
- MIME inconsistent or not in allowlist → `415`.
- DOCX is a ZIP container: `[Content_Types].xml` and must exist
  `word/document.xml`; macro `vbaProject.bin`, encrypt entries, path traversal,
  more than 1000 entries, single entry >32 MiB or total decompressed >64 MiB come
  rejected. A non-DOCX archive is rejected.
- The filename is just metadata: it is reduced to the basename, not used as a path or
  key storage. Title maximum 200 characters.
- SHA-256 hash calculated by the server on the bytes received.

## Persistence and jobs

Migration `006_documents_jobs.sql`:

- `documents`: KB FK, uploader, filename, title, MIME, size, SHA-256, blob key,
  timestamp; `UNIQUE(knowledge_base_id,sha256)` for dedup; index KB/created.
- `document_jobs`: FK `ON DELETE CASCADE`, status `queued/running/completed/failed/cancelled`,
  attempts, error_code, timestamp; index `(state,created_at)`.
- Document and job are inserted in the same transaction: there is no job without it
  valid document. The job starts `queued`; the M3-06 worker processes it and publishes it
  chunks (see [jobs.md](jobs.md)).
- Upload: PUT storage → transactional insert. If the insert fails, the blob comes
  deleted best-effort. If a dedup race returns an existing document,
  the blob just written is deleted.
- Delete: removes document/job and then the best-effort blob; if chunks exist,
  inserts a vector cleanup for the worker. Reindex/cleanup in
  [ingestion.md](ingestion.md); no secrets are recorded in the logs.
- A KB with documents cannot be deleted (409); the documents must be removed
  before. The FK DB is the final barrier.

## Limits

- The gateway reads the file in memory up to 20 MiB; the rate limiter e
  `MaxBytesReader` limit the body. Concurrent uploads are limited by
  deployment; Multi-GB streaming is not supported.
- MIME is verified on the initial content; complete structural validation
  of PDF/HTML/DOCX and parser protection are in [parsing.md](parsing.md).
- There is no public blob download in M3-03; the storage runtime exposes only
  Authenticated internal PUT/GET/DELETE.
- The dedup is per KB; does not share blobs between different KBs. This avoids leaks
  existence but can duplicate bytes across distinct KB.
- The job is not yet executed; `queued` is the initial visible state.## Evidence

- `apps/gateway/documents_test.go`: upload TXT/PDF/DOCX, inconsistent MIME,
  Hostile DOCX, oversize, dedup per KB, cross-owner, scope, storage failure,
  list/get/delete.
- `apps/runtime/tests/test_storage_api.py`: internal endpoint PUT/GET/DELETE,
  auth, invalid keys, adapter missing.
- `tests/e2e/check_documents.py`: real upload gateway→runtime→PostgreSQL,
  dedup, PDF/DOCX, MIME/hostile archive, ownership, job queued, delete and KB guard;
  included in `make e2e`.
- `make test` 221 runtime + 8 workers + 3 skipped; `make e2e` complete. The 006 migration and the
  document/job tables are verified by the runner.