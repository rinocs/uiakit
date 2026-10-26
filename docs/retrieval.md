# Composable Retrieval
Retrieval pipeline with mandatory ACLs, explicit index version, reranker
optional and deterministic context budget. The core does not depend on Haystack or
a specific vector DB.

## Contract

`packages/core/src/uai_core/retrieval.py`:

- `AccessFilter(knowledge_base_ids)`: non-empty set of authorized KBs.
- `IndexTarget`: collection, `index_version` and `EmbeddingModel`; the version must
  match the embedding (`index_version_mismatch`).
- `Retriever.retrieve(query, access, target)`:
  1. normalize the query;
  2. validate the non-empty ACL filter;
  3. check embedding/version/size;
  4. query embedding;
  5. `VectorStore.search` with server-side KB filter;
  6. verify that each hit is in the ACL;
  7. optional reranker;
  8. context assembler.
- `RetrievedChunk`: chunk, score, KB, document/hash/version, page, offset,
  text.
- `ContextAssembler(max_chars, max_chunks)`: deterministic order, dedup for
  chunk ID, character budget; a chunk that exceeds the budget is skipped,
  never silently cut off.
- `RetrievalResult`: selected chunks, context text and used characters.

## ACL and version

There is no implicit global search: `AccessFilter` empty →
`missing_authorized_filter`. The filter is passed to the vector store and each hit
outside ACL is an error (`unauthorized_result`), not a result to ignore.

`IndexTarget` binds collection and `index_version`; an embedding with version o
different size fails with `embedding_index_mismatch`. This prevents
query an index built with another model.

## Ranking and budget

Without reranker the results are sorted by decreasing score and, in the event of a tie, by
`chunk_id`. With a reranker, the order is the one returned by the reranker, but:
- cannot add unrecovered chunks;
- cannot duplicate ID;
- the chunks remain the original ones (ACL/provenance not modifiable);
- score must be finished.

The context budget is deterministic: max chunk, max characters, dedup and skip dei
chunks that don't fit. No text or offset is invented.

## Optional Haystack Adapter

`HaystackRetrieverAdapter` accepts an object already instantiated by the host with method
`run`; **doesn't mind Haystack** in core. Pass filters `knowledge_base_id in` and
`index_version ==`, read documents with `content`/`text` and `meta` containing
chunk/KB/document/hash/version/page/offset. Documents out of ACL or version
they fail closed. The backend is therefore replaceable with Haystack or another
retriever, without changing the context contract.

## Runtime configuration

`retriever_from_env()` uses `EMBEDDING_*`/`QDRANT_URL` (M3-07/M3-08) and:

| Variable | Default | Notes |
| --- | --- | --- |
| `RETRIEVAL_SEARCH_LIMIT` | 20 | candidates before budget/rerank |
| `RETRIEVAL_CONTEXT_CHARS` | 8000 | context budget |
| `RETRIEVAL_CONTEXT_CHUNKS` | 10 | maximum chunk in context |

The reranker remains optional and is injected by the caller; no reranker
default.

## Limits

- The budget is for characters, not tokens; the token-aware budget is M4-07.
- Retrieval does not decide access: it trusts the built `AccessFilter`
  by the host authority; the vector store applies server-side filtering.
- The RAG directive, quotes and run integration are M3-11.
- Haystack is not a required dependency; without adapter the retriever is used
  core with Qdrant.

## Evidence

`apps/runtime/tests/test_retrieval.py` covers:

- mandatory ACL filter, hits outside ACL and version/embedding mismatch;
- deterministic sorting, tie-break, dedup and budget;
- reranker absent/present, rejection of added/duplicated hits;
- Haystack adapter, filters, provenance and fail-closed;
- factory runtime with configured limits.

Evidence: `make test` 221 runtime + 8 workers + 3 skipped; Go race/vet.