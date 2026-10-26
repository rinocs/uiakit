# Milestone 3 — RAG Implementation Plan

> **For agentic workers:** use superpowers:executing-plans; superpowers:subagent-driven-development only with authorized model and delegation. Each task has a responsible owner and a verifiable gate.

**Goal:** Complete RAG per PROJECT_SPEC.md, with verified incremental deliverables.
**Architecture:** Go has public API, permissions, and authoritative persistence; Python has AI execution and adapters. Plugins register via contracts, they do not bypass the gateway authority.
**Tech Stack:** Go + chi/pgx, Python >=3.12 + FastAPI/Pydantic; optional components and SDKs introduced by the task that requires their use.
**Spec:** [PROJECT_SPEC.md](../../project-spec.md); index and dependencies in [TASKS.md](../../TASKS.md).

**Relevant ADRs:** [0003](../../adr/0003-authorization-and-secrets.md), [0007](../../adr/0007-rag-data-and-provenance.md), [0008](../../adr/0008-durable-jobs-and-optional-redis.md), [0009](../../adr/0009-providers-and-model-capabilities.md), [0010](../../adr/0010-memory-and-data-lifecycle.md). States and scope in [ADR index](../../adr/README.md).

## Global Constraints

- “Don't try to implement everything at once.” A milestone remains open until its gate passes.
- “PostgreSQL must be the authoritative source; vector indexes must be reconstructible.”
- “API keys must not be persisted in the clear.” Runtime, database and internal services not exposed.
- “Mandatory security directives must not be able to be removed from plugins.”
- “Use providers and mock tools in unit tests to avoid calls to external services.”
- No automatic semantic memory without data policies; no arbitrary code installation via API.
- Redis, Qdrant, LiteLLM and collectors only when required; no duplicate abstractions or upfront scaffolding.

## Review Focus

- Authority boundaries: model/plugin/retrieval input cannot broaden scopes or accessible resources.
- Concurrent effects: retry and crash must not duplicate mutations; unknown outcomes remain explicit.
- Derived data: index/cache/citations respect versions, ownership and deletion.
- Incomplete streams: EOF without terminal does not equal success; deletion closes the resources.
- Compatibility: Stable public API, verifiable migrations and ever-green core tests.

## Execution mode

Future tasks are verifiable backlog, not already implemented code. The routes are
the intended destination: before editing look for the real owner in the repository e
reuse it; record any necessary consolidation in the task. The commands
involving new packages become executable in the task that introduces them;
they are not presented as having already passed checks. For large tasks, specify signatures and
fixture in the local operational plane before writing code, maintaining the IDs.
Each new package must expose reproducible tests and checks; extend Makefile e
CI in the same task to include them in the suite. Dependencies indicate contract availability: unit-test/docs tasks can
continue while M1-06 is waiting. The closure of a milestone however depends
from the real tests of the previous ones. Don't mark a task complete just because it exists
his plan. Commit/worktree only if the Git metadata becomes usable again.

### M3-01 — Knowledge base, versions and access

**Status:** Completed; verified with `make test-go` and `make e2e` on PostgreSQL. **Owner:** Go.
**Depends on:** M2-02, M2-03.
**Expected files:** apps/gateway/knowledge_bases.go; apps/gateway/migrations/005_knowledge_bases.sql; apps/gateway/knowledge_bases_test.go; packages/api-contract/public.openapi.json.
**Produces / contract:** /v1/knowledge-bases: create/read/update/delete, associations to assistants and versions; authorization on KB/documents before upload or retrieval.
**Acceptance:** An unauthorized KB does not fit into runtime filters; server-side verified associations; active version distinct from ongoing reindexing; FK and consistent indices.
**Testing scenarios:** make test-go; two KB cross access test.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-02 — Local and S3-compatible storage

**Status:** Completed; checked with `make test-python` and `make storage-s3` on RustFS. **Owner:** Go / Python.
**Depends on:** M3-01.
**Expected files:** packages/core/src/uai_core/storage.py; apps/runtime/uai_runtime/storage/{filesystem,s3}.py; apps/runtime/tests/test_storage.py; compose.yaml.
**Produce / contract:** Blob store with put/get/delete and server-generated keys; Default persistent filesystem, optional S3-compatible adapter and secret references.
**Acceptance:** Absolute traversal and path denied; partial upload does not appear complete; idempotent cancellation; Optional S3 tested with compatible service; no arbitrary URLs from the template.
**Testing scenarios:** make test-python; integration storage filesystem and S3 fixture.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-03 — Upload documents and metadata

**Status:** Completed; verified with `make test-go` and `make e2e` (real upload gateway→runtime→PostgreSQL). **Owner:** Go.
**Depends on:** M3-01, M3-02.
**Expected files:** apps/gateway/documents.go; apps/gateway/migrations/006_documents_jobs.sql; apps/gateway/documents_test.go; packages/api-contract/public.openapi.json.
**Produces / contract:** /v1/documents upload/list/get/delete, byte limits, verified MIME, allowlist formats, server-side hashing, and per-KB/access deduplication; job created atomically in the metadata.
**Acceptance:** Oversized file, inconsistent MIME, and dangerous archive rejected; identical hash in different KB does not reveal existence; no visible job without valid document.
**Testing scenarios:** make test-go; Valid and hostile TXT/PDF/DOCX upload test.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-04 — Parsers and normalization

**Status:** Completed; verified with `make test-python` and deterministic fixtures. **Owner:** Python.
**Depends on:** M3-03.
**Expected files:** packages/core/src/uai_core/documents.py; apps/runtime/uai_runtime/rag/parsers.py; apps/runtime/tests/test_parsers.py; tests/fixtures/documents/*.
**Produce / contract:** DocumentLoader, DocumentParser, DocumentProcessor; TXT/Markdown/HTML/PDF text/DOCX parsing with limits. OCR/SQL/web/Git contracts defined, with unsupported errors for backends not installed.
**Acceptance:** Corrupted document fails without indexing; HTML does not script or fetch; PDF preserves pages; DOCX without unlimited zip expansion; No OCR declared, not simulated.
**Testing scenarios:** make test-python; deterministic fixtures of the five formats.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-05 — Chunking and provenance

**Status:** Completed; checked with `make test-python` and migrated 007 to E2E. **Owner:** Python.
**Depends on:** M3-04.
**Expected files:** packages/core/src/uai_core/chunks.py; apps/runtime/uai_runtime/rag/chunking.py; apps/runtime/tests/test_chunking.py; apps/gateway/migrations/007_chunks.sql.
**Produce / contract:** Chunker with size/overlap configured per KB; Stable chunk_id, document hash/version, offsets/page, authoritative original source and normalized text in PostgreSQL.
**Acceptance:** Offsets lead back to the original text; Unicode chunk and last fragment correct; identical reingestion does not duplicate; provenance present before indexing.
**Testing scenarios:** make test-python; property/fixture test chunk empty, long, Unicode and page boundaries.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-06 — Durable workers and jobs

**Status:** Completed; verified with `make test` and real worker on PostgreSQL/E2E. **Owner:** Python / Go.
**Depends on:** M3-03, M3-05.
**Expected files:** apps/worker/pyproject.toml; apps/worker/uai_worker/{main,jobs}.py; apps/gateway/jobs.go; apps/runtime/tests/test_jobs.py; compose.yaml.
**Produce / contract:** Worker ingestion with authoritative PostgreSQL status/job, concurrent claim, lease, limited retry and inspectable dead-letter. Redis only if necessary as an optional transport/cache, never sole source of the job.
**Acceptance:** Recoverable worker crash; two workers do not publish two versions; retry does not duplicate chunks; cancellation respected; job status visible to authorized persons.
**Testing scenarios:** make test; integration worker crash/retry/cancel with PostgreSQL.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-07 — Embedding providers and Ollama

**Status:** Completed; checked with `make test-python` and test adapter/retry/dimensions. **Owner:** Python.
**Depends on:** M2-03, M3-05.
**Expected files:** packages/core/src/uai_core/embeddings.py; apps/runtime/uai_runtime/providers/{ollama,openai_embeddings}.py; configs/models/*; apps/runtime/tests/test_embeddings.py.
**Produce / contract:** EmbeddingProvider.embed(texts) with size/model/version; Explicit Ollama adapter for chat and embeddings, OpenAI-compatible embeddings and effective capabilities. LiteLLM retains same boundary as an optional backend.
**Acceptance:** Batch limit, safe timeout/retry, wrong size and missing capability handled; model change requires new index version; no cloud key needed with Ollama.
**Testing scenarios:** make test-python; integration Ollama opt-in with declared model.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-08 — Qdrants and mandatory filters

**Status:** Completed; checked with `make test-python` and Qdrant 1.15.0 on two KB. **Owner:** Python / DevOps.
**Depends on:** M3-01, M3-05, M3-07.
**Expected files:** packages/core/src/uai_core/vector_store.py; apps/runtime/uai_runtime/rag/qdrant_store.py; apps/runtime/tests/test_vector_store.py; compose.yaml.
**Produce / contract:** VectorStore.upsert/search/delete with collection/version and server-side filters on authorized KB; Qdrant started only from RAG/full profile.
**Acceptance:** Search without authorized filter denied; consistent dimensions; delete repeatable; Unpublished Qdrant; index entirely reconstructable from authoritative data.
**Testing scenarios:** make test-python; Qdrant integration with two KB and isolated results.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-09 — Ingestion, reindex and export pipeline

**Status:** Completed; verified with real `make test` and E2E Qdrant/workers. **Owner:** Worker / Go.
**Depends on:** M3-06, M3-07, M3-08.
**Expected files:** apps/worker/uai_worker/ingestion.py; apps/gateway/knowledge_export.go; apps/runtime/tests/test_ingestion.py; tests/e2e/check_ingest.py.
**Produce / contract:** Upload→validate→parse→normalize→chunk→embed→index; separate prepared version and atomic switch; reindex/export authorized metadata, sources and provenance.
**Acceptance:** Partial index never active; deduplicated retry; export without secrets; new complete index before switch; Document deletion subsequently deletes all vectors and invalidates retrieval.
**Testing Scenarios:** E2E ingestion/reindex/export/cancel with PostgreSQL and Qdrant.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-10 — Composable retrieval and Haystack adapter

**Status:** Completed; checked with `make test-python` and test ACL/version/budget. **Owner:** Python.
**Depends on:** M3-01, M3-08, M3-09.
**Expected files:** packages/core/src/uai_core/retrieval.py; apps/runtime/uai_runtime/rag/{retriever,haystack_adapter,context}.py; apps/runtime/tests/test_retrieval.py.
**Produce / contract:** Retriever.retrieve(query, access, version) returns chunk with provenance; access filters→query processing→search→optional Reranker→context budget. Haystack as optional adapter, core without mandatory import.
**Acceptance:** No results out of ACL/version; deterministic budget and ranking with fixtures; replaceable backend; Absent Reranker works; non-silent embedding mismatch.
**Testing scenarios:** make test-python; test adapter contract and KB isolation.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M3-11 — RAG Directive, citations and gates

**Status:** Completed; RAG gate checked with `make test` and `make e2e` (Qdrant/worker/citations). **Owner:** Python / Go / QA.
**Depends on:** M2-06, M3-10.
**Expected files:** plugins/builtin/directives/rag_retrieval.py; apps/runtime/uai_runtime/rag/citations.py; packages/api-contract/*; tests/e2e/check_rag.py; docs/rag.md.
**Produce / contract:** RAGRetrievalDirective enabled for assistant; retrieval as non-authoritative content; events/responses with verifiable citation_id, document_id/version, chunk_id and page/offset.
**Acceptance:** Citations point only to chunks actually recovered; source accessible only if authorized; prompt injection in the document does not change prompt/policy/tool; E2E upload→query→citation pass.
**Testing scenarios:** make test; E2E RAG offline with embedding/model fixture and Qdrant; real M1 gate before closing.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.