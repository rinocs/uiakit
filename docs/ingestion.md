# Ingestion, reindex and export pipeline
Complete pipeline from already uploaded documents to a Qdrant index version
complete, with atomic switch, authorized export and vector cleanup. PostgreSQL
remains the authoritative source; Qdrant is a derived and reconstructible index.

## Flow

1. Validated upload (M3-03) → document + job `queued`.
2. Document worker (M3-06): parse (M3-04), chunk (M3-05), persistence
   `document_chunks`; job `completed`.
3. `reindexing` index version with config chunk + embedding (M3-07/M3-08):
   `POST /v1/knowledge-bases/{id}/versions`.
4. Index builder worker:
   - version claims (`reindexing`/`building` expired), lease and retry;
   - new Qdrant collection for `index_version`, never the active one;
   - for each completed document: blob → parse → chunk → embed a batch →
     upsert points with provenance;
   - chunks upsert idempotent in PostgreSQL.
5. Only when the build is complete: `superseded` of the active version, `active` of the
   new, `knowledge_bases.active_version`, `ready_at`, `chunk_count` and audit.
6. Export `/v1/knowledge-bases/{id}/export` from PostgreSQL.
7. Delete document: vector cleanup job on all collections in the KB.

## Index versions

`knowledge_base_versions` (migration 009) adds:

- `embedding_provider/model/version/dimension`;
- `collection_name` deterministic from `index_version`;
- `chunk_count`, `ready_at`, `attempts`, `error_code`;
- lease `lease_owner/lease_until`;
- `building`, `ready`, `superseded` states in addition to existing ones.

A version can arise with explicit `embedding`; if omitted, it is copied
from the embedding of the active version. Creation requires `If-Match`. Only one
`reindexing`/`building` version for KB; only one `active`.

## Atomicity and retry

- The new collection is deleted and recreated at the beginning of the build: a
  old partial attempt cannot be activated.
- An error deletes the new collection and marks the version `failed` (or
  `reindexing` for transient errors, with limited retry). The active index
  previous one remains intact.
- The build uses the same chunk/point IDs as M3-05/M3-08: retry and reingestion not
  they duplicate.
- The lease is rechecked in the final commit; a worker who has lost his lease
  does not activate the version.
- completed `document_jobs` are the source of documents to be indexed;
  documents with job failed/cancelled do not enter.

## Export

`GET /v1/knowledge-bases/{id}/export` (scope `knowledge-bases:read`, owner/admin)
returns:

- knowledge base and versions (status, embedding, collection, chunk count);
- documents without `blob_key` or secrets;
- chunk with hash document/version, page, offset, text and configuration;
- `exported_at`.

Limits: 2,000 chunks and 8 MiB per response → `413 export_too_large`. Export not
contains blobs, path storage, credentials, or vectors. It can be reconstructed from the data
PostgreSQL.

## Document deletion

`DELETE /v1/documents/{id}` collects the chunk IDs and inserts a
`vector_cleanup_jobs` in the same transaction as delete. The worker deletes i
points from all the KB collections (active and historical), with retry and idempotency.
Removing it from PostgreSQL still invalidates the source; M3-10 also applies the
authorization/existence check in retrieval.

## Deployment

Worker: env `QDRANT_URL`, `EMBEDDING_*` (M3-07). Qdrant `rag`/`full` profiles only,
not published. In E2E the worker uses the `/api/embed` dimension 8 e mock provider
Qdrant 1.15.0; the Qdrant port is only published by the test override.

## Evidence

- `apps/worker/tests/test_ingestion.py`: build complete, chunk/point count,
  activation, wrong size, missing embedding, permanent/transient error,
  cleanup.
- `apps/gateway/export_test.go`: embedding/version copy, export without blob key,
  cross-owner access, embedding validation.
- E2E `tests/e2e/check_ingestion.py`: reindex on PDF/DOCX, atomic switch,
  Complete Qdrant collection, export, delete document and vector removal.
- Evidence: `make test` 221 runtime + 8 workers + 3 skipped; `make e2e` 22 checks
  passed with Qdrant 1.15.0, mock embedding, PostgreSQL and real workers.