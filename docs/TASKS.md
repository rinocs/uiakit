# Universal AI Kit — full backlog

Source: [PROJECT_SPEC.md](project-spec.md), sections 1–21. Plan prepared on
2026-10-22 and updated on 2026-10-23 with real tests of M1 and M2.

Continuous log: [progress.md](progress.md).

## Status and reading

- **Implemented:** Code present, initial session local checks logged.
- **To check:** code present; built-in testing on real Docker is missing.
- **To do:** deliverable not yet implemented.
- **Conditional:** explicitly optional/future evolution, outside the MVP gate.

Each tab in the linked plans contains owners, dependencies, expected files,
contract, acceptance criteria and checks. Owners are job roles,
not already started agents. User requested deepseek-4.1-flash for agents;
not available in the session: do not replace it without user indication.

Docker tests of M1 and M2 were performed on 2026-10-23 with Docker 29.8.2 and
Compose v5.6.0: `make test` and `make e2e` pass. The current suite is 165 tests
Python, the Go suite with race/vet and E2E authentication scenarios, versions,
directives, built-ins, tools, SDK, plugins, hooks and restart.

## Milestone and sequence

| Milestones | Objective | Tasks | Status |
|---|---|---:|---|
| [M1 — Functional Core](superpowers/plans/2026-10-22-milestone-1-functional-core-closeout.md) | Functional Core | 6 | Completed; Docker/PostgreSQL/E2E verified |
| [M2 — Extensibility](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Extensibility | 10 | Completed; Docker/PostgreSQL/E2E gates verified |
| [M3 — RAG](superpowers/plans/2026-10-22-milestone-3-rag.md) | RAG | 11 | Completed; gate RAG/E2E verified |
| [M4 — Agents](superpowers/plans/2026-10-22-milestone-4-agents.md) | Agents | 10 | Milestone 4 completed |
| [M5 — Integration](superpowers/plans/2026-10-22-milestone-5-integration.md) | Integration | 10 | Completed; gate contracts/browser/E2E verified |
| [M6 — Production Hardening](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Production Hardening | 9 | Completed; final gate and release candidate 0.1.0 locale |

The M1 already implemented remains described in the [original plan](superpowers/plans/2026-10-22-functional-core.md)
and in the [audit log](implementation-status.md); M1-01…M1-06 are the stable IDs
of the backlog and do not require reimplementing the four historical tasks.

## ADRs connected

The [ADR index](adr/README.md) collects the 13 architectural decisions: ADR 0001
for existing core, proposed ADR 0002–0012 for contracts, security, lifecycle,
plugins, effects tools, RAG, jobs, providers, memory and deployment; ADR 0013 documents
assistant and snapshot versions adopted in the code. Every ADR postpones
to the tasks involved; each plan links the relevant ADRs.

## Tasks

| ID | Tasks | Owner | Addictions | Status |
|---|---|---|---|---|
| [M1-01](superpowers/plans/2026-10-22-milestone-1-functional-core-closeout.md) | Boundaries and initial contracts | Architecture | — | Implemented |
| [M1-02](superpowers/plans/2026-10-22-milestone-1-functional-core-closeout.md) | Gateway and initial persistence | Go | M1-01 | Implemented |
| [M1-03](superpowers/plans/2026-10-22-milestone-1-functional-core-closeout.md) | Streaming agent and provider | Python | M1-01 | Implemented |
| [M1-04](superpowers/plans/2026-10-22-milestone-1-functional-core-closeout.md) | Persistent SSE and idempotence | Go | M1-02, M1-03 | Implemented |
| [M1-05](superpowers/plans/2026-10-22-milestone-1-functional-core-closeout.md) | Initial Deployment and Automated Testing | DevOps | M1-02, M1-03 | Implemented |
| [M1-06](superpowers/plans/2026-10-22-milestone-1-functional-core-closeout.md) | Real Docker and PostgreSQL Verification | QA / user | M1-04, M1-05 | Verified with `make e2e` |
| [M2-01](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Public core and execution context | Python | M1-01, M1-03 | Completed |
| [M2-02](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Credentials, scopes and ownership | Go / Security | M1-02 | Completed; PostgreSQL verified |
| [M2-03](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Assistant and model catalog versions | Go / Python | M2-01, M2-02 | Completed; PostgreSQL verified |
| [M2-04](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Orderly and secure directive pipeline | Python/Go | M2-01, M2-03 | Completed; Docker/E2E verified |
| [M2-05](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Typical events and observational hooks | Python/Go | M2-01, M2-04 | Completed; Docker/E2E verified |
| [M2-06](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Initial built-in directives | Python | M2-04, M2-05 | Completed; Docker/E2E verified |
| [M2-07](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Tool registry and executor built-in | Python/Go | M2-01, M2-02, M2-05 | Completed; Docker/E2E verified |
| [M2-08](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | SDK plugins, manifests and local skills | Python | M2-01, M2-04, M2-05, M2-07 | Completed; Docker/E2E verified |
| [M2-09](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Loader plugin and administrative integration | Python/Go | M2-02, M2-03, M2-08 | Completed; Docker/PostgreSQL/E2E verified |
| [M2-10](superpowers/plans/2026-10-22-milestone-2-extensibility.md) | Gate Extensibility and plugin SDK guide | QA / Docs | M2-06, M2-07, M2-09 | Completed; gate Extensibility verified |
| [M3-01](superpowers/plans/2026-10-22-milestone-3-rag.md) | Knowledge base, versions and access | Go | M2-02, M2-03 | Completed; PostgreSQL/E2E verified |
| [M3-02](superpowers/plans/2026-10-22-milestone-3-rag.md) | Local storage and S3-compatible | Go / Python | M3-01 | Completed; S3 fixture verified |
| [M3-03](superpowers/plans/2026-10-22-milestone-3-rag.md) | Upload documents and metadata | Go | M3-01, M3-02 | Completed; E2E verified uploads/jobs |
| [M3-04](superpowers/plans/2026-10-22-milestone-3-rag.md) | Parser and normalization | Python | M3-03 | Completed; verified fixtures/tests |
| [M3-05](superpowers/plans/2026-10-22-milestone-3-rag.md) | Chunking and provenance | Python | M3-04 | Completed; test/pattern 007 verified |
| [M3-06](superpowers/plans/2026-10-22-milestone-3-rag.md) | Durable workers and jobs | Python/Go | M3-03, M3-05 | Completed; worker/retry/cancel E2E |
| [M3-07](superpowers/plans/2026-10-22-milestone-3-rag.md) | Embedding providers and Ollama | Python | M2-03, M3-05 | Completed; adapter/limits/size verified |
| [M3-08](superpowers/plans/2026-10-22-milestone-3-rag.md) | Qdrant and mandatory filters | Python / DevOps | M3-01, M3-05, M3-07 | Completed; Qdrant two KB isolated |
| [M3-09](superpowers/plans/2026-10-22-milestone-3-rag.md) | Ingestion, reindex and export pipeline | Worker / Go | M3-06, M3-07, M3-08 | Completed; E2E Qdrant/export/cleanup |
| [M3-10](superpowers/plans/2026-10-22-milestone-3-rag.md) | Haystack composable retrieval and adapter | Python | M3-01, M3-08, M3-09 | Completed; Checked ACLs/version/budgets |
| [M3-11](superpowers/plans/2026-10-22-milestone-3-rag.md) | RAG Directive, citations and gates | Python / Go / QA | M2-06, M3-10 | Completed; verified quotes/E2E |
| [M4-01](superpowers/plans/2026-10-22-milestone-4-agents.md) | Persistent run state and deletion | Go / Python | M2-02, M2-03, M2-05 | Completed; cancel/replay E2E |
| [M4-02](superpowers/plans/2026-10-22-milestone-4-agents.md) | Tool authorization cannot be bypassed | Python/Go | M2-02, M2-06, M2-07, M4-01 | Completed; policy/recheck and test escalation |
| [M4-03](superpowers/plans/2026-10-22-milestone-4-agents.md) | Secure HTTP executor and connector | Python/Go | M2-07, M4-02 | Completed; SSRF/DNS pinning and HTTP testing |
| [M4-04](superpowers/plans/2026-10-22-milestone-4-agents.md) | Constrained human approvals | Go / Python | M2-02, M4-01, M4-02 | Completed; binding/concurrent decision/E2E |
| [M4-05](superpowers/plans/2026-10-22-milestone-4-agents.md) | Idempotent and retry executions of effects | Go / Python | M4-03, M4-04 | Completed; reserve/retry/unknown/E2E |
| [M4-06](superpowers/plans/2026-10-22-milestone-4-agents.md) | Agent loop with tool calling | Python | M4-01, M4-02, M4-05 | Completed; provider/tool ​​loop/read-only |
| [M4-07](superpowers/plans/2026-10-22-milestone-4-agents.md) | Budget, context window and structured output | Python | M2-03, M2-06, M4-06 | Completed; budget/usage/structured output |
| [M4-08](superpowers/plans/2026-10-22-milestone-4-agents.md) | Audit of sensitive operations | Go / Python | M2-02, M2-05, M4-05, M4-07 | Completed; transactional audit and admin reading |
| [M4-09](superpowers/plans/2026-10-22-milestone-4-agents.md) | HTTP Isolated Plugins | Python / DevOps | M2-09, M4-02, M4-03, M4-08 | Completed; protocol/container/policy |
| [M4-10](superpowers/plans/2026-10-22-milestone-4-agents.md) | Gate Agents with real HTTP tool mock | QA | M4-06, M4-07, M4-08, M4-09 | Completed; E2E read-only/mutant |
| [M5-01](superpowers/plans/2026-10-22-milestone-5-integration.md) | TypeScript SDK from Contract | TypeScript | M2-10, M3-11, M4-10 | Completed; contract check/typecheck/17 test |
| [M5-02](superpowers/plans/2026-10-22-milestone-5-integration.md) | PHP SDK and Laravel integration | PHP | M5-01 | Completed; 13 tests, Laravel providers and mock gateways |
| [M5-03](superpowers/plans/2026-10-22-milestone-5-integration.md) | Go SDK from contract | Go | M5-01 | Completed; race/vet and contract tests |
| [M5-04](superpowers/plans/2026-10-22-milestone-5-integration.md) | Widget session token and CORS | Go / Security | M2-02, M4-01 | Completed; bindings/origin/revoke/rate/CORS tested |
| [M5-05](superpowers/plans/2026-10-22-milestone-5-integration.md) | Web Component chatbot | Frontend | M5-01, M5-04 | Completed; sanitizer/SSE/a11y/8 test |
| [M5-06](superpowers/plans/2026-10-22-milestone-5-integration.md) | Console: Access, Assistants and Templates | Frontend | M2-10, M5-01, M5-04 | Completed; server-side session, roles, browser tests |
| [M5-07](superpowers/plans/2026-10-22-milestone-5-integration.md) | Console: KB and documents | Frontend | M3-11, M5-06 | Completed; upload/job/reindex/export/source and access denied |
| [M5-08](superpowers/plans/2026-10-22-milestone-5-integration.md) | Console: tools, plugins and approvals | Frontend | M4-10, M5-06 | Completed; read-only catalog, plugin health/activation, approval binding |
| [M5-09](superpowers/plans/2026-10-22-milestone-5-integration.md) | Console: conversations, runs and playgrounds | Frontend | M5-05, M5-06, M5-08 | Completed; SSE/replay/cancel/citations/audit, Playwright 12/12 |
| [M5-10](superpowers/plans/2026-10-22-milestone-5-integration.md) | Gate integrations and SDK compatibility | QA / Docs | M5-02, M5-03, M5-07, M5-09 | Completed; 45 ops matrix, E2E widgets, Playwright 13/13, package builds |
| [M6-01](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Retention, cancellation and privacy | Go / Python / Security | M2-01, M3-11, M4-08 | Completed; tombstone, retention and delete E2E |
| [M6-02](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Verified backup and restore | DevOps | M6-01 | Completed; backup/restore/query/replay/reindex E2E |
| [M6-03](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | OpenTelemetry and observability | Go / Python | M2-05, M4-08 | Completed; fail-open and E2E traces/metrics/logs |
| [M6-04](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Secrets, rate limits and operational egress | Security / DevOps | M2-02, M4-03, M5-04 | Completed; secret file/rotation, rate limit for principal, egress and config scan |
| [M6-05](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Security Regression Suite | QA / Security | M6-01, M6-04, M5-10 | Completed; 15 boundary matrix, 73 referenced tests, config scan |
| [M6-06](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Performance, capacity and recovery | QA / Backend | M3-06, M4-10, M6-03 | Completed; baseline/perf/recovery E2E |
| [M6-07](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Dependencies, licenses and release packaging | DevOps | M5-10, M6-05 | Completed; SBOM/license, dry-run packages/images and contract diff |
| [M6-08](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Upgrade, rollback and two instances | DevOps / Docs | M6-02, M6-04, M6-07 | Completed; upgrade 14→15, graceful shutdown, future pattern rejected, two isolated stacks |
| [M6-09](superpowers/plans/2026-10-22-milestone-6-production-hardening.md) | Final gate and release candidate | QA / Maintainer | M6-05, M6-06, M6-08 | Completed; acceptance report, release candidate 0.1.0, green gates |## Parallel work and boundaries

- After M1: **Python M2-01** and **Go M2-02** are independent. M2-03 integrates the two contracts.
- M2: registry tools and directive pipelines can advance after the shared core;
  Assign changes to ExecutionContext, events, and OpenAPI to a single owner.
- M3: parser/chunking, storage and embedding can have distinct owners once
  fixed metadata/ACL. Worker and retrieval integrate contracts, not redefine them.
- M4: Go approvals and Python HTTP executors can advance after policy and run state;
  no mutant tools are enabled before approvals and idempotence.
- M5: PHP/Go SDK can advance on fixed contract; widgets and console remain
  separated. OpenAPI files and migrations have only one owner at a time.
- M6: backup, observability and security tests can be delegated separately;
  final gate and contract review are sequential.

Do not assign two agents the same file or migration. Every task passes
its own proof and delivers the contract before unlocking the consumers. None
agent was initiated only to prepare these documents.

## Specification coverage

| Sections PROJECT_SPEC | Responsible tasks |
|---|---|
| 1–3 vision, stack, boundaries | M1-01…M1-06; M6-08 |
| 4 cores, Agent/AgentRuntime/ExecutionContext | M2-01, M2-03, M4-01, M4-06, M4-07 |
| 5 six directives required | M2-04, M2-06, M3-11, M4-02 |
| 6 lifecycle/hooks/typed events | M2-05, M4-01, M4-08 |
| 7 Plugins/PluginManager/SDK | M2-08, M2-09, M4-09; P-01 |
| 8 Tool/registry/executor/approval | M2-07, M4-02…M4-05; P-01 |
| 9 RAG and adapter | M3-01…M3-11; P-04…P-07, P-09 |
| 10 MemoryProviders and Memory Levels | M2-01, M2-06, M6-01; P-02 |
| 11 ModelProvider/capability/embedding/usage | M1-03, M2-03, M3-07, M4-07; P-03, P-08, P-09 |
| 12 OpenAPI, SSE, SDK | M1-01, M1-04, M2-03, M2-07, M2-09, M3-01, M3-03, M4-01, M4-04, M5-01…M5-04 |
| 13 schema, indices, FK, authoritative data | M1-02, M2-02, M2-03, M2-09, M3-01…M3-06, M4-01, M4-04, M4-05, M4-08, M6-01 |
| 14 security and trust boundaries | M2-02, M2-04, M3-01, M3-03, M3-11, M4-02…M4-05, M4-08, M5-04, M6-01, M6-04, M6-05 |
| 15 Docker/deployment | M1-05, M1-06, M3-06, M3-08, M4-09, M6-02, M6-04, M6-08 |
| 16 Admin Console | M5-06…M5-09 |
| 17 SDK/Widgets | M5-01…M5-05, M5-10 |
| 18 testing | Test each task; M1-06, M2-10, M3-11, M4-10, M5-10, M6-05, M6-06, M6-09 |
| 19 incrementality | A plan for milestones, dependencies and gates listed here |
| 20 product acceptance | Following matrix; final report M6-09 |
| 21 working modes | Original plan, ADR, tests and records of each task |

## The 13 acceptance criteria

| # | Result to be demonstrated | Task and test |
|---|---|---|
| 1 | Starting Docker Compose | M1-06, M6-08: Clean Stack and Profiles |
| 2 | Configure Ollama or OpenAI-compatible | M1-03, M3-07: smoke provider + capability |
| 3 | Create assistant via API | M1-02, M2-03: versions and auth |
| 4 | Message with streaming reply | M1-04, M1-06: immediate delta and persistent terminal |
| 5 | Install plugin example | M2-09, M2-10: trusted package in build, API activation |
| 6 | Activate assistant directive | M2-06, M2-10: Isolated configuration per version |
| 7 | Register/use HTTP tools | M4-03, M4-10: connector, auth, approval and effect |
| 8 | Upload to knowledge base | M3-03, M3-09: upload→job→index |
| 9 | Query documents with RAG | M3-10, M3-11: filtered retrieval |
| 10 | Verifiable Quotes | M3-05, M3-11: source/version/page/offset |
| 11 | Laravel integration | M5-02, M5-10: server-side executable example |
| 12 | Two independent instances | M6-08: Ports, Networks, Volumes, and Distinct Credentials |
| 13 | Update a component while preserving API | M5-10, M6-07…M6-09: contract diff and real upgrade |

Final evidence, commands and residual limits: [acceptance-report.md](acceptance-report.md).## Conditional evolutions, separated from the MVP gate

They are not hidden release dependencies. The required contracts are already included
in mandatory tasks; the optional implementation is activated with a concrete need.

| ID | Evolution | It depends on | Acceptance and testing |
|---|---|---|---|
| P-01 | Executor and plugin isolated MCP, phase following the built-in/HTTP MVP | M4-09, M4-10 | Discovery/call/cancel on MCP fixture server; same HTTP policy and approval; pin protocol/versions; no remote code import |
| P-02 | Semantic memory opt-in | M6-01 | Explicit consent/policy, ownership/retention/delete; no automatic capture default; E2E also deletes carriers/cache |
| P-03 | LiteLLM adapter/optional profile | M2-03, M4-07 | Consistent capacity, usage, errors and timeouts; core bootable without LiteLLM; contract suite provider |
| P-04 | OCR opt-in | M3-04, M3-11, M6-05 | PDF image fixture, CPU/time limits, no silent OCR; page and provenance preserved |
| P-05 | SQL connector read-only | M3-04, M3-11, M6-05 | Approved DSN, read-only credentials, query/row/time limits, verified ACL and provenance |
| P-06 | Opt-in web crawler | M3-04, M3-11, M6-05 | Egress/SSRF/redirect and limited depth/bytes/time, verifiable source/version, local site fixture |
| P-07 | Git repository connector | M3-04, M3-11, M6-05 | Remote allowed, commit fixed, clone/file limits, no hooks/submodules executed; provenance path/commit |
| P-08 | Vision provider | M2-03, M4-07 | Explicit capability, validated MIME and image sizes, token limits and multimodal fixture |
| P-09 | Reranker additional provider | M3-10 | Does not expand ACL, meets budget, verified scores and order; explicit fallback if absent |
| P-10 | Redis for caching, distributed limiter or job transport when needed | M3-06, M6-04, M6-06 | Measure that justifies its use; PostgreSQL remains authoritative; restart Redis does not lose jobs/data; optional profile and test failure |

## Next operating sequence

1. M1–M6 are completed and verified; the local release candidate 0.1.0 is
   described in [acceptance-report.md](acceptance-report.md) e
   [RELEASE_NOTES.md](release-notes.md).
2. Deployment and upgrade are in [deployment.md](deployment.md) and
   [upgrades.md](upgrades.md); the baseline is in [capacity.md](capacity.md).
3. Keep the stated boundaries open: a gateway and a database runtime,
   no distributed replication, no Redis rate limiters, no installation
   of plugins via API. Publishing and public deployment remain separate actions
   authorized.
4. Update this index and [progress.md](progress.md) after each completed task.