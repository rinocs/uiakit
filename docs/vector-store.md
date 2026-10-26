# Vector store and filters
Qdrant contract and adapter for derived vector index. PostgreSQL remains there
authoritative source of documents, chunks and provenance; Qdrant is rebuildable and non-rebuildable
he can decide for himself what knowledge is accessible.

## Contract

`packages/core/src/uai_core/vector_store.py`:

- `VectorPoint`: `chunk_id`, vector, KB, document, hash/version, page,
  offset and text.
- `VectorHit`: result with score and verified payload.
- `VectorStore`: `ensure_collection`, `upsert`, `search`, `delete`,
  `delete_collection`.
- `collection_for(kb_id, index_version)`: deterministic name
  `uai_<kbhex>_<index_version[:16]>`.
- `validate_authorized_kbs`: an empty set is **not** a wildcard; the research
  fails with `missing_authorized_filter`.
- `validate_vector`, `validate_points`, `validate_delete_ids`,
  `validate_collection_name`, batch/search limits.

The size is set by the `EmbeddingModel` M3-07. Each collection has only one
size; a different model/version/size requires a new one
`index_version` is a new collection. The name of the collection makes it clear
explicit.

## Qdrant adapter

`apps/runtime/uai_runtime/rag/qdrant_store.py` uses the REST API with `httpx` (no
Qdrant client required):

- `ensure_collection`: GET; if absent, create `Cosine` with the expected size; if
  exists with different size → error.
- `upsert`: validate points, create the collection and send points with stable UUIDv5 ID
  derived from the chunk ID. The payload contains chunk, KB, document/hash/version,
  page, offset and text.
- `search`: take a non-empty KB filter and send server-side
  `must: [{key: knowledge_base_id, match: {any: [...]}}]`. Collection absent →
  `index_not_ready` (fail closed), not empty results.
- `delete`: UUIDv5 of the same chunk IDs; collection absent/repetition are
  idempotent.
- `delete_collection`: used by reindex; 404 is idempotent.
- Optional API key, 30s timeout, no redirect, payload/response bounded,
  sanitized errors.

## Filters and isolation

The search never accepts an empty or absent filter. The caller must get through
only authorized KBs (owner/admin or future ACL). The adapter also verifies that
each hit belongs to a requested KB; a malformed or out-of-filter payload is a
error, not a result to be silently ignored.

The index contains no authority: a result is allowed only if the document/chunk
is still present in PostgreSQL and the KB is authorized. Reindex, atomic switch e
Vector cleanups are implemented in [ingestion.md](ingestion.md).

## Deployment

`compose.yaml` starts Qdrant only with `rag` or `full` profiles:

- pinned image `qdrant/qdrant:v1.15.0`;
- volume `qdrant-data`, network `backend`, **no published port**;
- TCP healthcheck;
- not part of the core stack nor of `make e2e`.

For the local fixture:

```bash
make vector-store-qdrant
```

Start Qdrant on a free loopback port, test with two KB and remove the
container. The collection is temporary; the test checks insulation, filter
mandatory, repeatable delete and fail-closed on absent collection.

## Limits

- Qdrant is a derived index: loss/corruption requires reindexing from PostgreSQL.
- No results without ACL filter; no implicit global search.
- Pagination/scroll and multi-collection merging are delegated to M3-10.
- Qdrant is not exposed on the public network; access occurs from the runtime/worker.

## Evidence

- `apps/runtime/tests/test_vector_store.py`: validation, mandatory filter,
  `any` request, collection creation, stable UUID, size, payload
  invalid, fail-closed and delete idempotent.
- Opt-in test `test_qdrant_two_knowledge_bases_are_isolated`: two KB, search
  filtered isolated, delete repeatable, collection removed and index not ready.
- Evidence: `make test` 221 runtime + 8 workers + 3 skipped (S3/Ollama/Qdrant
  real absent); `make vector-store-qdrant` 6/6 with Qdrant 1.15.0.