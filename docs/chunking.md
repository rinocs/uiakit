# Chunking and provenance
Deterministic chunking of normalized text, with verifiable offsets and IDs
stable. The chunker does not index or call embeddings: it prepares the data
authoritative that the worker will use in M3-06/M3-09.

## Contract

`packages/core/src/uai_core/chunks.py`:

- `Chunker(chunk_size, overlap).split(document, document_hash=..., document_version=1)`.
- `Chunk`: `document_hash`, `document_version`, `page`, `index`, `start`, `end`,
  `text`, `chunk_size`, `overlap`.
- `Chunk.id`: SHA-256 stable document identity, page, indexes, offset,
  configuration and text.
- `chunk_document(...)`: convenience function.
- `ChunkingError`: invalid configuration or provenance.

`apps/runtime/uai_runtime/rag/chunking.py` re-exports the same contract for the
workers; the algorithm remains in the core.

## Algorithm

The normalized text is divided **per page**; a chunk never crosses the
page border. The `start`/`end` offsets are code points in normalized text
of the document and satisfy:

```text
document.text[start:end] == chunk.text
```

For each page:

1. we start from `cursor = 0`;
2. `end = min(cursor + chunk_size, len(page.text))`;
3. the `page.text[cursor:end]` chunk is issued;
4. if `end` is the end of the page it ends;
5. otherwise `cursor = end - overlap`.

The last fragment can be shorter than `chunk_size`. With `overlap = 0` i
chunks are adjacent; with positive overlap they share code points. The characters
Unicodes are counted as Python code points, not as UTF-8 bytes.

`chunk_size` is 1…8000 and `overlap` is `0 ≤ overlap < chunk_size`. The configuration
KB uses 100…8000 (M3-01); the core chunker also accepts smaller values for
testing and reuse.

## Stable ID and reingestion

`chunk.id` is calculated from:

```text
document_hash, document_version, page, chunk_index, start, end,
chunk_size, overlap, chunk_text
```

The same document, hash, version and configuration produce the same IDs a
any reingestion. The `chunk_id` PK and an idempotent upsert prevent duplicates.
A hash/configuration change produces different IDs; the M3-09 reindex will have to
remove the previous generation before/after the switch.

## PostgreSQL schema

Migration `007_chunks.sql`:

- `document_chunks`: PK `chunk_id`, FK `document_id` with `ON DELETE CASCADE`,
  `document_hash`, `document_version`, `chunk_index`, `page`, `start_offset`,
  `end_offset`, `text`, `chunk_size`, `overlap`, timestamp.
- Check: hex hashes/IDs, consistent offsets, `length(text)=end-start`,
  valid configuration.
- Indexes: `(document_id, document_version, chunk_index)` and
  `(document_id, page, start_offset)`.
- Provenance is present in PostgreSQL before any writing
  in the vector index. The M3-06 worker populates the table, with upsert
  idempotent; the job is in [jobs.md](jobs.md), the index in
  [vector-store.md](vector-store.md).

## Evidence

`apps/runtime/tests/test_chunking.py` covers empty/short/long document, overlap,
last fragment, Unicode, page boundaries, stable IDs, negative cases and a
property on lengths 0…39, dimensions 1…11 and all valid overlaps: every
chunk is an exact slice, the coverage goes to the end and the overlaps are
respected. Evidence: `make test` 221 runtime + 8 workers + 3 skipped; `make e2e` applies the
migration 007 and check the presence of the table.