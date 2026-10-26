# Milestone 6 — Production Hardening Implementation Plan

> **For agentic workers:** use superpowers:executing-plans; superpowers:subagent-driven-development only with authorized model and delegation. Each task has a responsible owner and a verifiable gate.

**Goal:** Complete Production Hardening per PROJECT_SPEC.md, with verified incremental deliverables.
**Architecture:** Go has public API, permissions, and authoritative persistence; Python has AI execution and adapters. Plugins register via contracts, they do not bypass the gateway authority.
**Tech Stack:** Go + chi/pgx, Python >=3.12 + FastAPI/Pydantic; optional components and SDKs introduced by the task that requires their use.
**Spec:** [PROJECT_SPEC.md](../../project-spec.md); index and dependencies in [TASKS.md](../../TASKS.md).

**Relevant ADRs:** [0003](../../adr/0003-authorization-and-secrets.md), [0006](../../adr/0006-tool-effects-and-approvals.md), [0007](../../adr/0007-rag-data-and-provenance.md), [0008](../../adr/0008-durable-jobs-and-optional-redis.md), [0010](../../adr/0010-memory-and-data-lifecycle.md), [0012](../../adr/0012-deployment-upgrades-and-recovery.md). States and scope in [ADR index](../../adr/README.md).

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

### M6-01 — Retention, deletion and privacy

**Status:** To be done. **Owner:** Go / Python / Security.
**Depends on:** M2-01, M3-11, M4-08.
**Expected files:** docs/data-policy.md; apps/gateway/retention.go; apps/gateway/migrations/012_retention.sql; apps/worker/uai_worker/deletion.py; tests/e2e/check_deletion.py.
**Produce / contract:** Explicit policy for conversation/working/semantic memory, documents, chunks, vectors, jobs, approval, and audit; authorized delete/retention, tombstone and repeatable garbage collection; semantic memory disabled.
**Acceptance:** Deleted data does not return from reindex/cache; consistent elimination of sources and vectors; minimized audit with declared retention; backup expiration documented before using real data.
**Testing scenarios:** E2E deletion during ingestion/retrieval, GC retry and data type retention.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

- [ ] Connect the mutant/retention MemoryProvider adapter to the gateway policies and related scopes; Explicit referral from M2-06, without new DB owner in runtime or no-op mutations.

### M6-02 — Verified backup and restore

**Status:** To be done. **Owner:** DevOps.
**Depends on:** M6-01.
**Expected files:** deploy/backup.sh; deploy/restore.sh; docs/backup-restore.md; tests/e2e/check_restore.py.
**Produce/contract:** Consistent backup of PostgreSQL, blobs, and non-secret configurations; isolated restore and Qdrant reconstruction; secrets provided separately; no privileged backup via public API.
**Acceptance:** Restore on new installation preserves ownership, history and provenance; verified checksums; reconstructable carriers; incompatible restore stops before overwriting data; RPO/RTO measured.
**Test scenarios:** E2E backup→new stack→restore→query and replay.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M6-03 — OpenTelemetry and observability

**Status:** To be done. **Owner:** Go / Python.
**Depends on:** M2-05, M4-08.
**Expected files:** apps/gateway/telemetry.go; apps/runtime/uai_runtime/telemetry.py; apps/worker/uai_worker/telemetry.py; deploy/observability/*; docs/observability.md.
**Produce / contract:** Trace gateway→runtime→provider/tool/ingestion, known latency/error/token/cost metrics, structured logs with correlation/run ID; optional collector.
**Acceptance:** No prompts/credentials in default attributes; controlled cardinality; unavailable collector does not block requests; metrics distinguish timeout/cancel/approval/retrieval.
**Test scenarios:** unit/integration telemetry exporter fixture; E2E correlation between services.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M6-04 — Secrets, rate limits and operational egress

**Status:** To be done. **Owner:** Security / DevOps.
**Depends on:** M2-02, M4-03, M5-04.
**Expected files:** configs/policies/*; deploy/docker/*; compose.yaml; docs/security-operations.md; tests/e2e/check_security_config.py.
**Produce / contract:** Secret files/references and rotation, explicit egress policy for provider/connector, CORS/TLS reverse proxy, optional Redis rate limiting if required by deployment; documented fail policy.
**Acceptance:** No exposed interior doors; deny unauthorized connections; leak-free rotation; minimum profiles unchanged; limits per principal/session with bounded storage. Do not enable gateway replicas without adequate lease/recovery.
**Test scenarios:** config scans; integration rotation, limiter and policy egress on Docker enabled.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M6-05 — Security regression suite

**Status:** To be done. **Owner:** QA / Security.
**Depends on:** M6-01, M6-04, M5-10.
**Expected files:** tests/security/*; tests/fixtures/security/*; .github/workflows/test.yaml.
**Produce / contract:** Permanent negative tests for auth/scopes/ownership, prompt injection, SSRF/DNS/redirect, upload, XSS, plugin boundaries, approval/replay, and log redaction.
**Acceptance:** Each trust boundary has a deny case and a valid case; mutant tool does not duplicate; KB isolated; no model code execution; API key does not persist in the clear; testing without cloud calls.
**Test scenarios:** security suites; E2E attacker/authorized user matrix.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M6-06 — Performance, capacity and recovery

**Status:** To be done. **Owner:** QA / Backend.
**Depends on:** M3-06, M4-10, M6-03.
**Expected files:** tests/performance/*; tests/e2e/check_recovery.py; docs/capacity.md.
**Produces / contract:** Reproducible workloads chat/SSE/ingestion/retrieval, slow clients, deletes, backpressure and crash recovery in supported deployment; Documented CPU/RAM/latency baseline.
**Acceptance:** No unlimited growth of buffers/connections/queues; competing runs respect policies; worker fetch lease; slow provider does not exhaust gateway; limits sized by measurements, not invented thresholds.
**Test scenarios:** benchmark with provider/embedding fixture; soak/recovery test and baseline comparison.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M6-07 — Dependencies, licenses and release packaging

**Status:** To be done. **Owner:** DevOps.
**Depends on:** M5-10, M6-05.
**Expected files:** .github/workflows/release.yaml; docs/dependencies.md; docs/releases.md; deploy/docker/*; packages/*.
**Produce / contract:** Reproducible lock/checksums, SBOM and transitive notices, image/template license analysis, vulnerability scanning, semantic tags and versioned/digest images. Prepare SDK/plugin packages without automatically publishing them.
**Acceptance:** Playable clean build; no secrets in the artifacts; breaking contract intercepted; managed and documented vulnerabilities/license conditions; signature/provenance if supported by the pipeline.
**Testing scenarios:** build in clean runner; SBOM/license checks; contract diff; dry-run packaging.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M6-08 — Upgrade, rollback, and two instances

**Status:** To be done. **Owner:** DevOps / Docs.
**Depends on:** M6-02, M6-04, M6-07.
**Expected files:** docs/deployment.md; docs/upgrades.md; tests/e2e/check_upgrade.py; tests/e2e/check_two_instances.py; compose.yaml.
**Produces / contract:** Clean install runbook, core/local-ai/full profiles, template prerequisites, graceful shutdown, compatible migrations, backup before upgrade, application rollback or restore when non-reversible scheme.
**Acceptance:** Two instances with separate ports/networks/volumes/credentials; upgrade component preserves API and data; incompatible schema downgrade rejected; shutdown during run occurred; Destructive rollback requires explicit procedure.
**Test scenarios:** E2E old→new→recovery; two simultaneous stacks; core without optional services.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M6-09 — Final gate and release candidate

**Status:** To be done. **Owner:** QA / Maintainer.
**Depends on:** M6-05, M6-06, M6-08.
**Expected files:** docs/acceptance-report.md; docs/TASKS.md; .github/workflows/test.yaml.
**Produce / contract:** Execute all 13 section 20 acceptance criteria with evidence, versions and residual limits; local release candidate and release notes.
**Acceptance:** All green mandatory gates, including real Docker; isolated update demonstrated; no missed tests presented as successes. Publishing/public deployment remain separate authorized actions.
**Testing scenarios:** make test; make e2e; contract/browser/security/restore/upgrade suites; checklist section 20.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.