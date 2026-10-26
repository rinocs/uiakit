# ADR 0007 — RAG data, isolation and citations

**Status:** adopted in M3-01…M3-11 for knowledge base, versions, ownership,
associations, blob storage, upload, parsing, chunking, durable jobs, embedding,
Qdrant index, reindex, export, cleanup, retrieval, RAG directive and citations.
 The explicit constraints of PROJECT_SPEC.md remain
mandatory.
**Date:** 2026-10-22.
**Related tasks:** M3-01…M3-11, M6-01, M6-02. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

Vector search must be reconstructable and cannot decide on its own which documents are accessible. Citations must refer to verifiable sources/versions.

## Alternatives considered

Using the vector DB as the sole source simplifies ingestion but loses transactions and provenance. PostgreSQL plus authoritative blob storage and derived Qdrant separate data and indexes.

## Proposed decision

PostgreSQL maintains KB/document versions, hashes, access, chunk/provenance and job status. Original blobs on default or optional S3-compatible persistent filesystem. Qdrant contains reconstructable vectors and metadata. Upload validated before parse; dedup per KB/access scope, no leaks between resources. Parser/chunker/embedding/retriever pipeline with separate contracts; Haystack is an optional adapter, not a mandatory core import. Index version built separately and activated only complete. Access filters applied before and during retrieval; verified result. Citations include source/version/chunk/page or offset, only from actually used chunks. Retrieval is non-authoritative content.

## Consequences and limits

Storage, metadata, and index require coordinated deletion and reconciliation. Exports are authorized and do not include secrets. Load adapters serve their respective processes without moving ownership of public APIs away from the gateway. OCR, SQL/web/Git have initial contracts but opt-in implementations.

## Verification required

Two KB with distinct accesses, deduplicated upload, partial index, embedding/size change, reindex, delete and restore. Quotation test reconstructs the source's tract; document with prompt injection does not alter prompt/policy/tool.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Implementation M3-01

Implemented `knowledge_bases` and `knowledge_base_versions` in PostgreSQL with
owner, revision, active version separated from `reindexing`, deferred FK and indexes
unique per active/reindexing version. The associations to assistants are
validated in the transaction that creates the immutable version, with shared lock
of the KB; an unauthorized KB cannot enter the snapshot. APIs, scopes and
limits are in [knowledge-bases.md](../knowledge-bases.md). Upload, chunks,
embedding, Qdrant and retrieval are not yet implemented.

## Implementation M3-02

Blob store with host-generated keys, `put/get/delete` and `BlobNotFound`.
Atomic filesystem with temporary file and rename, traversal/absolute rejection and
final symlinks, dedicated volume `blob-data`; Optional S3 adapter with boto3
lazy, credentials from secret/env and RustFS fixtures in the `s3` profile. Details in
[storage.md](../storage.md). HTTP upload, hash/dedup and document metadata are M3-03.

## Implementation M3-03

Multipart upload with 20 MiB limit, MIME verified for TXT/Markdown/HTML/PDF/DOCX,
DOCX container control (macros, encryption, path, expansion limits), hashing
SHA-256 server-side and dedup per KB. `queued` document and job are created in the
same transaction; the blob is written to the storage runtime before the insert e
cleaned up if the insert fails or loses a dedup race. API, guards and limits in
[documents.md](../documents.md). Parser, chunk and index are M3-04/M3-05.## Implementation M3-04

Contracts `DocumentLoader`, `DocumentParser`, `DocumentProcessor`, `ParsedDocument`
and `DocumentPage` with verifiable offsets; TXT/Markdown/HTML/PDF/DOCX parser e
byte/character/page/zip limits. HTML uses only the stdlib parser (script/style
excluded, no fetch), PDF uses pypdf and declares `ocr_required` if there is no text,
DOCX uses defusedxml and rejects macros/encryption/traversal/expansions beyond bounds.
OCR/SQL/web/Git contracts remain protocols without fake implementations. Details
in [parsing.md](../parsing.md). Chunking and index are M3-05/M3-06.

## Implementation M3-05

Deterministic chunker per page, with code points, overlap and last fragment;
`Chunk.id` SHA-256 stable on document/hash/version/page/offset/config/text.
Migration 007 `document_chunks` preserves normalized text, hash, version,
page, offset and configuration with FK cascade and consistency check. The provenance
it is written before the index; the idempotent worker/upsert is M3-06. Details in
[chunking.md](../chunking.md).

## Implementation M3-06

Python worker with PostgreSQL claim `FOR UPDATE SKIP LOCKED`, lease, limited retry,
dead-letter and cooperative cancellation. The worker reads blob/config KB, parse and
chunk, publish chunks with stable IDs and `ON CONFLICT DO NOTHING`, then complete the
job in the same transaction; a lost lease or canceled job does not publish.
Migration 008 adds lease/dead-letter and claim index. Status/cancel API for
owner/admin. Details in [jobs.md](../jobs.md). Embedding/index are M3-07…M3-09.

## Implementation M3-07

`EmbeddingModel`/`EmbeddingProvider` contract with Ollama provider or
OpenAI-compatible, size/version/batch and stable `index_version`; adapter
Ollama `/api/embed` and OpenAI-compatible `/embeddings`, transient retry only,
timeout, size/value checks. Ollama native chat selectable, without
cloud key. Changing model/version/size requires a new version
index. Details in [embeddings.md](../embeddings.md). Qdrant/retrieval are
M3-08…M3-10.

## Implementation M3-08

`VectorStore` contract with collection for `index_version`, explicit size,
dots with provenance, delete idempotent and mandatory KB filter search
server-side. Qdrant REST Adapter (Stable UUIDv5, verified payload, fail-closed
on absent index); Qdrant started only in `rag`/`full` profiles, no ports
public. Details in [vector-store.md](../vector-store.md). Pipeline/reindex
they are M3-09; retrieval M3-10.

## Implementation M3-09

Document→parse→chunk→embed→Qdrant pipeline with separate index versions,
collection for `index_version`, build complete then transactional switch
(superseded→active) and lease/retry. PostgreSQL export without blobs/secrets; delete
document appends vector cleanup on all KB collections. Details in
[ingestion.md](../ingestion.md). Retrieval/citations are M3-10/M3-11.

## M3-10 implementation

Composable retriever with non-empty ACL, explicit index/embedding version,
server-side filtering, optional reranker, deterministic sorting and context
budget. Optional Haystack Adapter for injected object, without import into core;
documents out of ACL/version fail closed. Details in
[retrieval.md](../retrieval.md). RAG Directive/Citations are M3-11.

## Implementation M3-11

`builtin.rag` directive with gateway-sent targets, untrusted context,
guards built-in mandatory, citations issued only for recovered chunks e
referenced. `response.completed` includes verifiable `citations[]`; exports and
E2E gates compare chunk/document/version/page/offset. Details in
[rag.md](../rag.md). The RAG milestone is closed.