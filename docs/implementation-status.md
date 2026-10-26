# Milestone 1 — task status

> Current update (2026-10-24): M1 and M2 are completed and verified with
> Docker/PostgreSQL/E2E; M3 and M4 are completed; M4-01…M4-10 verified.
> The following sections are historical; the most recent evidence is at the bottom of the document
> and in [progress.md](progress.md).

## Implementation

- [x] Task 1: architectural boundaries, ADR, plan, public and internal OpenAPI 3.1.
- [x] Task 2: HTTP-independent BasicAgent, OpenAI-compatible adapter,
  Validated SSE events and payloads, internal authentication, limits and timeouts.
- [x] Task 3: chi gateway, hashed operator credential, rate limit,
  PostgreSQL with versioned migration, history, run, idempotence and replay.
- [x] Task 4: Dockerfile, Compose, profiles, network isolation, mock providers,
  E2E scripts, startup documentation, and two independent instances.

## Verification gate

- [x] Python Suite: 16 tests passed, including OpenAPI snapshots and streaming limits.
- [x] Suite Go: 7 tests passed with race detector; go vet and successful build.
- [x] Compose config core and E2E valid; shell syntax and compileall succeeded.
- [ ] Docker build/startup, migration to PostgreSQL and E2E after reboot:
  blocked by the sandbox (Docker socket not accessible). Do not declare the
  milestone verified end-to-end before running `make e2e`.

## Decisions and deviations

- No commit/worktree: `.git` is empty and read-only in the provided workspace.
- Local execution of tasks: deepseek-4.1-flash requested by the user is not included
  in the available agent models; no other model used as a replacement.
- Current code limited to Milestone 1: no abstraction for RAG, plugins,
  code, semantic memory, tool or console before the corresponding milestone.
- Only one gateway and only one operator. Multiple tenants/replicas require auth,
  ownership and recovery with lease, to be designed before enabling them.

CI set up in `.github/workflows/test.yaml`: unit tests and E2E Docker.
It has not been run on GitHub since this session.

## Overall planning

Get ready [56 mandatory tasks and 10 conditional evolutions](TASKS.md), with six
separate plans, owners, dependencies, expected files, contracts and acceptance tests.
Coverage includes all 21 sections and final 13 criteria of PROJECT_SPEC.md.
The [ADR](adr/README.md) includes the existing core and 11 proposed choices
future. No tasks M2–M6 are declared implemented by this planning activity.

User will check Docker next: M1-06 remains open, without impeding
preparing Milestone 2 contracts and unit tests.

## M2 implementation update

Current log: [progress.md](progress.md).

- M2-01 verified locally: installable uai-core, immutable context, working
  memory per run, consolidated runtimes/providers without duplication of contracts.
- M2-02 implemented: roles/scopes, revocable credentials and rotation, migration
  ownership and audit; Real PostgreSQL verification gate still open.
- Current suite: 33 Python, 14 Go with race detector and vet; build gateway,
  compileall, shell and Compose config passed. Detailed checks in the register.
- M2-04…M2-10 not yet implemented; M2-03 update below. M1-06 continues to wait for Docker test.

## Update M2-03

Assistant, conditional PATCH and template catalog versions implemented; snapshot
immobile in runs and capability/limits control in runtime. Current suite: 43 Python
and 19 Go with race detector/vet. Updated OpenAPI, examples and E2E scenarios. Migration
003 and PostgreSQL concurrency testing remain open for Docker. State on time and
sequence of tasks in [registry](progress.md); next task M2-04.

## Update M2-04 (partial)

Runtime-integrated core pipeline: trusted registry, version selection
private assistant, order dependencies/priority/name, timeout, fail/continue e
protected context. Suite updated: 63 Python and 19 Go with race/vet.
Validation shared with the gateway for public authorization remains open.
Agreement and Limitations in [directives.md](directives.md); M2-05 and following not started.## M2-04 — deployment completed, Docker testing opened

Gateway integration also completed: POST/PATCH selections validated with Bearer
internal from the runtime before persistence. Configuration errors give 422;
unavailability/redirect gives 503 without saving versions. Names and graphs have a
Only authoritative validator in core, no duplicate catalogs in Go.

Final local check: 65 Python, 22 Go with race/vet, build gateway, wheel core
isolated, compileall, shell and Compose config passed. Directives scenario included
in make e2e, yet to run with Docker/PostgreSQL available.
Next task: M2-05; built-in and loader plugins not yet implemented.

## M2-05 — implemented and tested locally

Typed metadata events for 18 phases and built-in observational async hooks
BasicAgent. Detached and immutable snapshots, deterministic order/filters, timeouts,
budget for isolated runs and errors with redacted diagnostics. Mandatory guards
they remain in the editing pipeline. Also fixed immediate cleanup of the provider
when the close comes after a delta.

Public SSE v1 unchanged; separate internal lifecycle in lifecycle.schema.json.
Tool/memory have ready contracts, no dummy events before capabilities.
Suite: 77 Python and 23 Go with race/vet; build, compileall, wheel, shell and Compose
config passed. E2E with metadata sink set up, Docker/PostgreSQL to run.
Next task: M2-06. Full contract at [events-hooks.md](events-hooks.md).

## M2-06 — five built-ins implemented

Prompt guards, conversational memory, output, observability and tool policy
always installed in the BasicAgent. The registry orders readonly guards after i
middleware and the pipeline protects the initial history. Omit built-in names or
using empty directives does not disable them. Output whitespace ends in error;
telemetry without content; tool still deny-by-default.

Implementations in the wheel core; conversation persistence remains in the gateway.
Mutant/retention Python adapter realigned to M6-01 with updated ADR 0010.
Suite: 91 Python and 23 Go with race/vet; build, wheel isolated, compileall, shell e
Compose config passed. Built-in E2E scenario ready; Docker/PostgreSQL to run.
Next task: M2-07. Details in [builtin-directives.md](builtin-directives.md).

## M2-07 — built-in registry and executor implemented

ToolDefinition core, single registry with consistent Pydantic templates/schemas, executor
trusted standalone and builtin.text_stats read-only. Authorization with scope,
permissions and explicit grant, limits before/after normalization, timeout,
metadata-only deletion and audit. No retries or side effects authorized.

GET /v1/tools protected by tools:read; authenticated/bounded runtime catalog without
callables or secrets. The factory uses the same register for catalog and executor.
BasicAgent remains textual and the gateway does not yet grant tool IDs to the model.

Suite: 112 Python and 26 Go with race/vet; build, wheel isolated, compileall, shell e
Compose config passed. Fixture SDK runs locally; Docker/PostgreSQL from
execute. Follow-up task M2-08. Contract and Limits in [tools.md](tools.md).

## M2-08 — SDK plugins and skills implemented

installable uai-plugin-sdk: manifest with versions/compatibilities/dependencies,
Plugin/registrar contracts and bounded local skills. Root approved host, reading
POSIX descriptor-relative without symlink/traversal, frozen snapshots and contents
JSON delimited without implicit privileges. Metadata resolution doesn't matter either
activate plugins. Shared HookSubscriber in the core, with no SDK dependency on the runtime.

Suite: 140 Python and 26 Go with race/vet; build/check SDK, wheel core+SDK isolated,
compileall, shell and Compose config passed. Updated Docker/CI installation;
SDK fixture passed locally. Docker/PostgreSQL and GitHub CI to run.
Next task M2-09: manager/discovery/activation/administrative API.
Agreement and Limitations in [plugin-sdk.md](plugin-sdk.md).## M2-09 — ongoing: manager foundation

Added trusted PluginManager with atomic staging of contributions, snapshots of
logs, namespace/capability, active dependencies, Pydantic host configuration,
cleanup and health bound. The manager is not yet connected to the application.
Remaining discovery/build hello, persistence and reconciliation, administrative API,
run coordination and E2E verification. M2-09 is not completed.

### Progress M2-09 — runtime and hello

Manager connected to the runs, directive validation and catalog/executor tool.
Authenticated private routes for catalog/activation/deactivation/health, OpenAPI
updated. Hello statically approved in from_env and installed in the build;
part inactive and is selected for assistant. Lifecycle protected by run leases.

Local verification: 154 Python tests, Go race/vet suite, wheel hello and import from wheel,
compileall, shell syntax and Compose config passed. Prepared Docker smoke runtime,
not executed. Choices and limitations in [plugins.md](plugins.md) and ADR 0005.

That leaves public API, SQL/configure/persistence, and reconciliation: enable
still volatile. Docker/PostgreSQL gate open. M2-09 still underway.

## M2-09 — implemented locally, real gate open

Publish plugin API with explicit admin/scope and global If-Match revision;
desired state PostgreSQL and audit in migration 004. Validation before
commit, runtime application after commit; 202 indicates desired saved but
pending. Reconciliation at boot and on request, recovery after restart runtime,
configuration of dependencies and protection of implemented active runs.

Updated OpenAPI contracts and documentation. Local tests: 162 Python and 32 Go
with race/vet, build gateway, compileall, shell and Compose config passed. Scenarios
E2E public/SQL/restart prepared in runner, not executed. PostgreSQL migration
and Docker gates M1/M2 remain open. No multiple replication supported.
Next task M2-10; [plugins.md](plugins.md) describes API, recovery and limitations.

## Update 2026-10-23 — M1/M2 gates verified

Docker/PostgreSQL/E2E tests were performed with Docker 29.8.2 and Compose
v5.6.0. `make test` passes with 165 Python tests and Go suite with race detector/vet;
`make e2e` completes all scenarios, including authentication, versions, directives,
built-ins, tools, SDK, hello plugins, hooks, public administration, SQL audit, migrations 1–4 and
separate restart of runtime and gateway.

The real test exposed and corrected defects not visible in local tests:

- Compose v5.6.0 interpreted `UAI_PORT=0` as published port `:0`; the runner
  now chooses a free port on `127.0.0.1`.
- Docker 29 does not publish ports for containers connected to `internal` networks only.
  The gateway is now on the non-internal `frontend` network, maintaining backend and
  isolated databases.
- `up --wait` started the gateway before PostgreSQL was healthy; the runner
  start the dependencies first and then the gateway.
- Provider sent `Authorization: Bearer ` with empty key, rejected by
  httpx/h11; the header is omitted when the key is not configured. Added
  `apps/runtime/tests/test_provider.py`.
- Migration 004 did not register version 4 and was re-executed upon restart;
  it is now idempotent and registers the version. `OpenStore` rolls back first
  to close the pool, avoiding deadlock on the error path.
- Directives pipeline compared JSON dumps with `frozenset` (scopes,
  capabilities): the serialization order is not stable and caused
  Intermittent `directive_failed`. The comparison now uses Pydantic data, with
  regression tests in `test_directives.py`.
- E2E runner used stale cache images because `up --build` didn't rebuild
  the changed context; now runs an explicit build before booting.Documentation: [runtime-lifecycle.md](runtime-lifecycle.md) describes diagrams,
invariants and verification matrix. The GitHub pipeline runs `make test` and
`make e2e`, but it was not run on GitHub in this session.

## Update M3-01 — knowledge base and access

Implement `/v1/knowledge-bases` and `/v1/knowledge-bases/{id}/versions` with
scopes `knowledge-bases:read/write`, ownership owner/admin, ETag on revision
and `If-Match` on mutations. Migration 005 introduces KB, versions, config
bounded, deferred FK `(id, active_version)`, unique indexes for active version e
reindexing, and auditing. The active version remains distinct from the new version
`reindexing`; the switch is delegated to M3-09.

Server `knowledge_base_ids` is now allowed (max 64, unique UUIDs) e
revalidated in the creation/version transaction with shared lock of the KB.
An unknown or unauthorized KB produces 422 and does not fit into the snapshot; the
Python runtime accepts the snapshot and ignores the KB until M3-10/11 retrieval.
DELETE is stuck with 409 if a current version of the server references it
KB; historical versions do not block.

Tests: `make test` with 167 Python tests and Go race/vet suite; `make e2e` with
`tests/e2e/check_knowledge_bases.py` on two real principals, versioning,
association, run with KB in snapshot, deny cross-owner, delete guard and cascade;
the runner checks `schema_migrations` 1–5 and KB tables. Documentation in
[knowledge-bases.md](knowledge-bases.md). Next task: M3-02.

## Update M3-02 — blob storage

Implemented the `uai_core.storage` contract (`BlobStore`, `BlobNotFound`,
`new_blob_key`, `validate_blob_key`) with server-owned keys. Filesystem adapter
atomic: temporary file `O_EXCL|O_NOFOLLOW`, `fsync`, `os.replace`; refusal of
absolute paths, traversals, hidden names, backslash/NUL and trailing symlinks; delete
idempotent and temporary cleanup. Partial writing is not visible as
complete file.

Optional S3 adapter with boto3 lazy, endpoint/bucket/region/credentials from
env/secret manager, prefix validated, errors sanitized and `__repr__` without
secrets. `boto3` is pinned to `apps/runtime/requirements-s3.txt` and installed in
dev/CI; the base runtime image remains without S3 dependency and fails with
`BlobStoreUnavailable` if requested without package.

Compose: volume `blob-data` mounted in `/var/lib/uai/blobs` with ownership
of the runtime user; test-only profile `s3` with RustFS (pinned image), local port and
dedicated volume. `make storage-s3` starts the fixture on a free port and executes the
real roundtrip. Checks: `make test` 174 passed + 1 skip; `make storage-s3`
8/8; `make e2e` complete after Compose changes. Documentation:
[storage.md](storage.md). Next task: M3-03.

## Update M3-03 — upload documents and jobs

Implemented `/v1/documents` (list/upload/get/delete) with scope
`documents:read/write`, ownership via KB and multipart upload. 20 MiB limit,
Declared MIME compared with server-side sniff; allowlist TXT/Markdown/HTML/
PDF/DOCX. The DOCX is validated as a ZIP container: entries required, absence of
macros, no encryption/path traversal, limits on number of entries and expansion.
Server-side SHA-256 hash; dedup for KB (`UNIQUE(knowledge_base_id,sha256)`), with
200 + `X-Deduplicated` in the same KB and no leaks between different KBs.

Migration 006 introduces `documents` and `document_jobs`; `queued` document and job
they are created in the same transaction. The blob is written to runtime storage
(`PUT /internal/v1/storage/{key}`) before insert; on dedup error or race
best-effort is deleted. Delete removes document/job and then the blob; one KB
with documents cannot be deleted (409). The limiter is now configurable with
`UAI_RATE_LIMIT` (default 120; E2E uses a high value to avoid biasing tests).Tests: `make test` 177 Python passed + 1 skip, Go race/vet; `make e2e`
complete with `check_documents.py` on PostgreSQL/real runtimes (TXT/PDF/DOCX,
MIME/hostile archive, dedup, ownership, job, delete, KB guard). Contract
public and internal snapshot updated. Documentation:
[documents.md](documents.md). Next task: M3-04.

## Update M3-04 — parsing and normalization

Added `DocumentLoader`, `DocumentParser`, `DocumentProcessor` contracts,
`ParsedDocument`/`DocumentPage` and optional OCR/SQL/web/Git backends like
protocol, without simulated implementations. Runtime parsers:

- TXT/Markdown: UTF-8 with BOM, trailing lines/NUL/space normalization.
- HTML: stdlib parser, `script`/`style` exclusion, decoded entities, none
  fetch or execute.
- PDF: pypdf, pages preserved with offset; encrypted not supported; PDF without
  text → `ocr_required`.
- DOCX: ZIP + `word/document.xml` with defusedxml; entry/byte limits, rejection of
  macros, encryption and path traversal.

Limits: 20 MiB input, 2,000,000 characters, 2,000 PDF pages, 1,000 entries/32 MiB
per entry/64 MiB decompressed DOCX. Deterministic fixtures in
`tests/fixtures/documents/`; tests in `apps/runtime/tests/test_parsers.py`.
Verification: `make test` 184 passed + 1 skip. Documentation:
[parsing.md](parsing.md). Next task: M3-05.

## Update M3-05 — chunking and provenance

Implemented deterministic `Chunker` for page size/overlap in queues
point, no crossing of page boundaries, last fragment correct e
verifiable offsets (`document.text[start:end] == chunk.text`). `Chunk.id` is one
SHA-256 stable on document/hash/version/page/index/offset/configuration/
text: identical reingestion produces the same IDs and does not duplicate with upsert.

Migration 007 `document_chunks`: PK `chunk_id`, FK document with cascade, hash,
version, page, offset, normalized text, chunk_size/overlap, check by
consistency and indexes per document/page. Provenance persisted before
of the vector index; the worker execution is M3-06.

Checks: `make test` 191 passed + 1 skip; property test on lengths 0…39,
dimensions 1…11 and all overlaps; `make e2e` applies migration 007 e
check `document_chunks`. Documentation: [chunking.md](chunking.md). Next
tasks: M3-06.

## Update M3-06 — durable workers and jobs

Implemented Python worker with authoritative PostgreSQL: claim
`FOR UPDATE SKIP LOCKED`, lease, recovery of expired `running` jobs, retry
limited, dead-letter (`failed` + `dead_lettered_at`), and deletion
cooperative. The worker reads the config chunk from the active KB version, reads the
blob from storage, parse/chunk and publish the chunks with `ON CONFLICT DO NOTHING`
in the same transaction that completes the job; lease lost/cancel don't post.

Migration 008 adds lease/dead-letter and claim index. APIs
`GET /v1/documents/{id}/job` and `POST /v1/documents/{id}/job/cancel` with scope
documents and owner/admin access. Compose offers the `worker` profile; image
dedicated with shared storage. Tests: `make test` 192 runtimes + 5 workers +
1 skip, Go race/vet; `make e2e` with real worker on PostgreSQL, completion,
cancel, crash/lease recovery and retry without duplicates. Documentation:
[jobs.md](jobs.md). Next task: M3-07.

## Update M3-07 — embedding and Ollama

Implemented `EmbeddingModel`/`EmbeddingProvider` with Ollama provider or
OpenAI-compatible, explicit size/version/batch and stable `index_version`;
a model/version/size change requires a new index version.
Ollama Adapter `/api/embed` without key, OpenAI-compatible `/embeddings` with
Optional bearer (also LiteLLM), retry only on timeout/429/5xx, timeout 30s,
no redirects, validation of finite vectors/dimensions/values. Added
`OllamaProvider` native chat `/api/chat` selectable with `MODEL_PROVIDER=ollama`.Example config `configs/models/embedding-ollama.json` e
`embedding-openai.json`; factory `embedding_provider_from_env` for worker M3-09.
Tests: `make test` 200 runtime + 5 workers + 2 skipped (real S3/Ollama),
Go race/vet; Ollama opt-in test 0.6.8 + passed nomic-embed-text (768 sizes). Documentation: [embeddings.md](embeddings.md). Next task:
M3-08.

## Update M3-08 — Qdrant and filters

`VectorStore`/`VectorPoint`/`VectorHit` contract with collection for
`index_version`, explicit size, stable UUIDv5 for chunks, delete
idempotent and mandatory KB filter search. An empty filter is rejected:
there is no implicit global search. The Qdrant REST adapter verifies payloads
and membership of authorized KBs; collection absent → `index_not_ready`.

Qdrant 1.15.0 is in Compose only in `rag`/`full` profiles, with no published ports,
dedicated volume and TCP healthcheck. Unit testing with MockTransport and opt-in testing
real `make vector-store-qdrant` with two isolated KB, repeatable delete and
fail-closed. Evidence: `make test` 205 runtime + 5 workers + 3 skipped;
`make vector-store-qdrant` 6/6. Documentation: [vector-store.md](vector-store.md).
Next task: M3-09.

## Update M3-09 — ingestion, reindex and export

Migration 009 extends KB versions with embedding, collection, chunk_count,
ready_at, lease/attempts/error, and states building/ready/superseded; he adds
`vector_cleanup_jobs`. The Versioning API accepts explicit embedding or copies it
from the active. Worker `IndexBuilder` builds a new Qdrant collection, embed
in batch, it persists idempotent chunks and activates the version only when the build is complete
(superseded→active, active_version). Errors delete the new collection; retry
transients with lease.

API `GET /v1/knowledge-bases/{id}/export` (owner/admin, limits 2,000 chunks/8 MiB)
returns KB, versions, documents without blob key, chunk with provenance, without
secrets. Delete document append vector cleanup from all collections;
worker deletes points with retry/idempotence.

Tests: `make test` 206 runtime + 8 workers + 3 skipped, Go race/vet; `make e2e`
20 checks passed with PDF/DOCX reindex, atomic switch, Qdrant 1.15.0, export,
delete document and remove vectors. Documentation: [ingestion.md](ingestion.md).
Next task: M3-10.

## M3-10 update — composable retrieval

Implemented `Retriever` with non-empty `AccessFilter`, `IndexTarget` bound to
collection/version/embedding, server-side filtering, checking each hit,
deterministic reordering, optional reranker and per-character context budget.
Hits out of ACL, different embedding/version, invalid queries and reranker adding
chunks fail closed. `ContextAssembler` deduplicates and skips chunks over budget,
without cutting off the provenance.

Optional `HaystackRetrieverAdapter` adapter for injected object: no import
Haystack in core, KB/version filters and document validation. Factory
`retriever_from_env` with limits `RETRIEVAL_*`; reranker injected by the caller.

Tests: `make test` 211 runtime + 8 workers + 3 skipped, Go race/vet. ACL test,
version/embedding, ranking, budget, reranker, Haystack and factory. Documentation:
[retrieval.md](retrieval.md). Next task: M3-11.

## Update M3-11 — RAG directive, citations and gates

Added `builtin.rag`: Gateway sends authorized retrieval targets in the
internal request; directive fetch per KB, insert untrusted block,
maintains system prompt/policy/authority and saves the citation map. The guards
built-ins remain mandatory. `after_model` outputs only referenced citations
(`[C1]`…) and `response.completed` includes `citations[]` with chunk/document/
version/page/offset.

Updated public contract `Citation` and `RuntimeEvent`; SSE and replays
they retain citations. Unit tests cover directive, injection without
change authority, target/ACL error and payload. E2E `check_rag.py` checks
upload→Qdrant→query→anti-export quotes. Evidence: `make test` 216 runtime
+ 8 workers + 3 skipped, Go race/vet; `make e2e` 21 checks passed. Documentation:
[rag.md](rag.md). M3 closed; next M4-01.## Update M4-01 — run status and deletion

Migration 010 adds `queued`/`waiting_approval`/`cancelled` and
`updated_at`/`cancel_requested_at`. API owner/admin
`GET /v1/agent-runs`, `GET /v1/agent-runs/{id}`, `POST /v1/agent-runs/{id}/cancel`
scoped `agent-runs:*` and CAS on state. Migration/Finish accept
`agent.cancelled` and the events persist even after cancel.

Runtime `RunStateRegistry` and cancel-aware wrapper cancel provider/tool, issue
`agent.cancelled`; the gateway cancels the active HTTP request as a fallback e
maintains SSE/replay. Runs interrupted by restart remain `failed` with event
replayable; no automatic repeat. Tests: `make test` 221 runtime +
8 workers + 3 skipped, Go race/vet; `make e2e` 22 checks passed with real cancel e
replay. Documentation: [agent-runs.md](agent-runs.md). Next task: M4-02.

## Update M4-02 — tool authorization cannot be bypassed

`ToolPolicyDirective` is the sole owner of the permission: intersects
`authority.allowed_tool_ids`, scope of principal, tools selected in
assistant version, registered definition and allowlist connector
(`connector:<id>`). The executor applies it before execution and re-evaluates it
after validation of the arguments, immediately before the effect; a grant
revoked during a wait does not start the handler. Prompts, recovered documents,
tool output and plugins cannot add permissions. BasicAgent remains
without tool calling: `assistant.tools` gate opens in M4-06.

Tests: `make test-python` 229 runtime + 8 workers, 3 skipped (S3/Ollama
real absent); `make test-go` race/vet. Documentation: [tools.md](tools.md),
[builtin-directives.md](builtin-directives.md). Next task: M4-03.

## Update M4-03 — Secure HTTP executor and connector

`ConnectorDefinition` and `HTTPToolExecutor` introduce targets, methods
GET/HEAD, exact paths, headers as env references, timeout, response limit and
retry `never`. The model provides only tool_id and arguments; the topics
they become scalar queries, never URLs or headers. The registry requires permission
`connector:<id>` and reject HTTP mutants up to M4-05; the gateway validates the same
contract and the catalog accepts `builtin`/`http`/`mcp`.

SSRF: All DNS addresses are validated, loopback/link-local/metadata and networks
do not allowlistate are denied, the socket is pinned to the validated address and
redirect/proxy/Unix sockets are disabled. Secrets don't add up to results,
exceptions or logs; an echo in the body is rejected. The response limits are
applied in streaming.

Tests: `make test` 255 runtime + 8 workers, 3 skipped (real S3/Ollama
absent); Go race/vet. Documentation: [http-tools.md](http-tools.md).
Public and console logging/CRUD remain M5-08; MCP is contracted. Next
tasks: M4-04.

## Update M4-04 — human approvals constrained

`uai_runtime.approvals` binds a request to run, tool/version, canonical digest
of topics, principal/scopes/grant, assistant version and policy snapshot,
with a maximum expiration of 24 hours. The full arguments did not persist. The
pending/approved/rejected/expired/invalidated/consumed states prevent doubles
decisions, reuse and binding changed.

Migration 011 and API `/v1/approvals` list/get/approve/reject with scope
`approvals:read/write` for operator/admin. The transactional decision blocks
approval and run: only a competing decision wins, an expired one becomes
`expired`, a run no longer `waiting_approval` invalidates the approval. `approve`
returns run to `running`, `reject` to `failed`; dedicated audit.

Tests: `make test` 262 runtimes + 8 workers, 3 skipped (real S3/Ollama
absent); Go race/vet; `make e2e` complete with concurrent approval, deadline,
reject, scope and resume on real PostgreSQL. Documentation:
[approvals.md](approvals.md), auth, tools. Next task: M4-05.## Update M4-05 — idempotent and retry executions of effects

Migration 012 and `tool_executions` table with unique idempotent key per run,
tool/version, digest arguments, approval, risk, attempts and result bounded.
Internal API reserve/get/start/complete/fail/unknown/reconcile, protected by
internal key and not public. The reservation atomically consumes the approval
and check the binding; `completed` plays with no new effect.

`DurableToolRunner` retry only read-only on timeout/connector unavailable,
marks mutants with unknown outcome as `unknown` and does not retry them; lease stale e
crashes produce `unknown`, explicitly reconcilable. The internal client uses
timeout, no redirects and no environmental proxy.

Tests: `make test` 270 runtime + 8 workers, 3 skipped (real S3/Ollama
absent); Go race/vet; `make e2e` complete with reserve/replay/retry/unknown/
reconcile on real PostgreSQL. Documentation: [tool-executions.md](tool-executions.md).

## Update M4-06 — agent loop with tool calling

OpenAI-compatible providers with accumulated delta `tool_calls` per index;
`ToolCallingAgent` runs up to 4 generations and 8 tool calls, adds results
with `tool` role (never system) and requires the `tool_calling` capability. JSON
partial/malformed, unknown or unauthorized tool fails without executing
the executor. The gateway sends `allowed_tool_ids` only with `tools:execute`; the
runtime intersects assistant version, grant, scope, registry and connector policy.
Only read-only builtin/http tools are offered at this stage.

With `GATEWAY_URL` each tool goes through the M4-05 durable journal; BasicAgent remains
text-only. `MODEL_TOOL_CALLING=true` enables the capability in factory.

Tests: `make test` 278 runtime + 8 workers, 3 skipped (real S3/Ollama
absent); Go race/vet. Documentation: [agent-loop.md](agent-loop.md).

## Update M4-07 — budget, context window and structured output

`ExecutionLimits` adds max_steps/max_tool_calls/max_tokens with fallback for
legacy assistants. `RunBudget` stops loops, tool storms, tokens and context windows
beyond limits; the duration remains in the timeout. `UsageAccumulator` distinguishes usage
unknown from scratch, aggregates only reported values and calculates costs only with tariffs
notes; the budget uses an estimate only when the total is not known.

`structured_output` requires the dedicated capability, JSON Draft 2020-12 schema
bounded and validated on creation and on the final text (`jsonschema==4.26.0`).
Incorrect schema/output fails; no retry after a delta provider.

Tests: `make test` 288 runtime + 8 workers, 3 skipped (real S3/Ollama
absent); Go race/vet. Documentation: [budgets.md](budgets.md).

## Update M4-08 — audit of sensitive operations

Migration 013 extends `audit_events` with actor/run/correlation/digest/outcome,
details drawn up and retention class; `agent_runs.correlation_id` persisted.
Run, configuration, credentials, approvals and every transition tool write
in the same transaction as the mutation, so an audit error blocks
the effect. The `/v1/audit-events` read is admin-only (`audit:read`), filtered and
re-drafted; the runtime registers the binding before the effect and fails closed.

Tests: `make test` 292 runtime + 8 workers, 3 skipped (real S3/Ollama
absent); Go race/vet; `make e2e` exit 0 with SQL assertions about auditing and redaction.
Documentation: [audit.md](audit.md).

## Update M4-09 — HTTP isolated plugins

Manifest `isolated_http` and client host without remote code import; protocol
`X-UAI-Plugin-Protocol: 1` authenticated, catalog validated, tool read-only
namespaced with connector permission. Crashes/timeouts remain confined; container
non-root, read-only, cap-drop and backend network. The trusted Python remains one
distinct category, without promise of sandbox. Tests: `make test` 298
runtime + 8 workers, 3 skipped; Go race/vet; `make e2e` exit 0 with container
isolated. Documentation: [plugins.md](plugins.md).## Update M4-10 — gate Agents with mock real HTTP tool

Read-only agent tool loop reaches `mock_tool` and returns to SSE; tools not
selected and tool storm are stopped before the effect. The mutant gate uses
a real HTTP POST with immutable approval, consumption and idempotent replay without
second effect; SQL audit run/tool/approval/audit. Cancellation and resumption
remain covered by existing gates. Assistant Limits (`max_steps`,
`max_tool_calls`, `max_tokens`) now propagated to the factory.

Tests: `make test` 299 runtime + 8 workers, 3 skipped; Go race/vet;
`make e2e` exit 0. Documentation: [agents.md](agents.md). Milestone 4 complete;
next task M5-01.

## Update M6-04 — secrets, rate limits and operational egress

Secrets resolved by `_FILE` variable or file in gateway/runtime/worker, with
rejecting ambiguous sources, invalid files, and empty values; `SecretRef(file=...)`
in the connectors it is reread upon request. Rate limit bounded for installation,
principal and token widget, with full capacity sweep and deny. `UAI_EGRESS_ALLOW`
apply a host allowlist: leads to chat providers, embedding, isolated plugin and
(opt-in) `HTTPToolExecutor`; Compose separates internal `backend` and `model-egress`.
Added sample TLS reverse proxy, static security scan and
[security-operations.md](security-operations.md). Checks: runtime 341 passed
+ 3 skipped, worker 8, Go race/vet/build, contract 45 ops, `make test-security`,
`make e2e` exit 0. Limits: single instance, no distributed Redis limiter;
rotation of startup secrets with coordinated restart. Next task: M6-05.

## Update M6-05 — security regression suite

Added `tests/security/` with versioned array of 15 trust boundaries and 73
References to existing Go/Python/TypeScript tests, more control than scripts
Associated E2Es remain scheduled. `check_matrix.py --run` runs the deny and deny cases
allow referenced; `make test-security` also includes static scanning of
Compose/secrets/egress/proxy. Evidence: `make test-security` exit 0, 8 tests
widget, 73 valid references; no duplication of suites. Next task:
M6-06.

## M6-06 update — performance, capacity and recovery

Added `tests/performance/run.py` and `check_baseline.py` with workloads
reproducible chat/SSE, ingestion and retrieval (8 documents, 12 chats, 6 RAG,
concurrency 4, slow provider/erase) and CPU/RAM sampling. The
versioned baseline is `tests/performance/baseline.json`; `make test-capacity`
revalidation and `UAI_PERF_COMPARE` enables the comparison. `docs/capacity.md`
documents baseline, existing limits and sizing; no new threshold is
been introduced. Added Go test on SSE write deadline for slow clients.
`tests/e2e/check_recovery.py`, run by `make e2e`, kills gateway and worker:
run stopped marked `failed` with event `gateway_restarted` and same
`correlation_id` (idempotent replay); job with expired lease resumed without
duplicate chunk. Fixed recovery gateway to preserve correlation ID.
Highlights: `make e2e` exit 0 with recovery and performance; baseline chat p95 78 ms,
retrieval p95 183 ms, ingestion p95 1353 ms; `make test` and `make test-security`
green. Next task: M6-07.

## Update M6-07 — dependencies, licenses and release packaging

Added `VERSION` (0.1.0) and `make test-release` gate: consistent versions across
manifest and in Compose tags, exact Python pins, npm/Go/Composer lockfiles present,
Dockerfile without floating base images, contract and release workflow
declared. `scripts/release.py` generates CycloneDX 1.5 SBOM and notice transitive,
prepare npm pack/wheel/Composer archive/Go source, build 5 images with
version tags and OCI labels, records image IDs and tar hashes, and writes
`manifest.json` + `SHA256SUMS` without publishing anything. `tests/release/contract_diff.py`
block breaking changes against the previous tag; `check_licenses.py` applies
the SPDX allowlist; `check_release.py` checks checksums and absence of secrets in files
artifacts. Added `.github/workflows/release.yaml` pipeline with Syft, Grype,
contract diff, attestation of provenance and upload artifact; no `npm
publish`, `composer publish` or `docker push`. Evidence: `make test-release` exit 0
(8 tests), `make release-dry-run` exit 0 (SBOM 329 components, 5 images, 7
packages, artifact check green), `composer validate` green. Next task: M6-08.## Update M6-08 — upgrade, rollback and two instances

Added `docs/deployment.md` (clean install, core/local-ai/full profiles,
prerequisites template, shutdown, two installations) and `docs/upgrades.md` (backup
pre-upgrade, forward-only migrations, application rollback vs restore
destructive, rejected future pattern). `compose.yaml` now depends on the gateway
from PostgreSQL and sane runtimes and includes the worker in the `full` profile, eliminating
the non-deterministic startup observed by the tests. `tests/e2e/check_upgrade.py`
check pattern 14→15, data/replay, orderly shutdown during a run, reject
of scheme 16 and recovery; `tests/e2e/check_two_instances.py` checks two stacks
concurrent with separate projects/ports/credentials/volumes/network. Evidence:
`make e2e-upgrade` exit 0, `make e2e-two-instances` exit 0, `make e2e` exit 0.
Next task: M6-09.

## Update M6-09 — final gate and release candidate

Executed all mandatory gates on version 0.1.0: `make test`,
`make build-packages`, `make e2e`, `make e2e-upgrade`, `make e2e-two-instances`,
`make e2e-restore`, `make test-console-browser` (13/13), `make test-security`,
`make release-dry-run`/`release-check`; all exit 0. Fixed fixture restore
which did not set the `RUSTFS_*` required by Compose interpolation. Added
`docs/acceptance-report.md` with the 13 criteria and evidence, and `RELEASE_NOTES.md`
with the local release candidate. The `release/` bundle includes acceptance report,
release notes, SBOM, 5 versioned images, SDK/plugin packages, manifest and
checksum; no publication. The 3 skipped runtime tests (Ollama/S3/Qdrant
real) are explicitly declared and not counted as successes. Milestone 6
completed.