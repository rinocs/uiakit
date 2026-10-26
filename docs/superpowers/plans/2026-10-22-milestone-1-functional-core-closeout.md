# Milestone 1 — Functional Core Implementation Plan

> **For agentic workers:** use superpowers:executing-plans; superpowers:subagent-driven-development only with authorized model and delegation. Each task has a responsible owner and a verifiable gate.

**Goal:** Complete Functional Core per PROJECT_SPEC.md, with verified incremental deliverables.
**Architecture:** Go has public API, permissions, and authoritative persistence; Python has AI execution and adapters. Plugins register via contracts, they do not bypass the gateway authority.
**Tech Stack:** Go + chi/pgx, Python >=3.12 + FastAPI/Pydantic; optional components and SDKs introduced by the task that requires their use.
**Spec:** [PROJECT_SPEC.md](../../project-spec.md); index and dependencies in [TASKS.md](../../TASKS.md).

**Relevant ADRs:** [0001](../../adr/0001-functional-core.md), [0002](../../adr/0002-api-contracts-and-events.md), [0012](../../adr/0012-deployment-upgrades-and-recovery.md). States and scope in [ADR index](../../adr/README.md).

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

### M1-01 — Initial boundaries and contracts

**Status:** Implemented; local checks performed in the initial session. **Owner:** Architecture.
**Depends on:** none.
**Expected files:** docs/adr/0001-functional-core.md; packages/api-contract/*.json.
**Produce / contract:** Gateway responsible for auth and data; runtime responsible for agent and provider; Separate public and internal OpenAPI.
**Acceptance:** Versioned contracts and snapshots consistent with the implemented routes.
**Testing scenarios:** make test.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Local implementation and testing present; see the initial session log.
- [ ] Confirm the integrated behavior via M1-06.

### M1-02 — Gateway and initial persistence

**Status:** Implemented; local checks performed in the initial session. **Owner:** Go.
**Depends on:** M1-01.
**Expected files:** apps/gateway/{main,server,store,types}.go; apps/gateway/migrations/001_core.sql.
**Produce / contract:** Assistants, conversations, messages and agent_runs persisted; migration before traffic.
**Acceptance:** Health, assistant/conversation creation and history reading; no database exposed.
**Testing scenarios:** make test-go; make e2e.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Local implementation and testing present; see the initial session log.
- [ ] Confirm the integrated behavior via M1-06.

### M1-03 — Streaming agent and provider

**Status:** Implemented; local checks performed in the initial session. **Owner:** Python.
**Depends on:** M1-01.
**Expected files:** apps/runtime/uai_runtime/{agent,provider,models,app}.py.
**Produce / contract:** BasicAgent.run(RunRequest) returns asynchronous events; ModelProvider.stream produces ModelChunk.
**Acceptance:** Immediate first delta, normalized errors, lifetime/output/input limited, and upstream closed on cancellation.
**Testing scenarios:** make test-python.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Local implementation and testing present; see the initial session log.
- [ ] Confirm the integrated behavior via M1-06.

### M1-04 — Persistent SSE and idempotence

**Status:** Implemented; local checks performed in the initial session. **Owner:** Go.
**Depends on:** M1-02, M1-03.
**Expected files:** apps/gateway/server.go; apps/gateway/store.go; apps/gateway/server_test.go.
**Produce/contract:** Idempotency-Key for conversation, canonical replay; save before terminal.
**Acceptance:** No double runs on retry; 409 on conflict; final output equal to deltas; incomplete stream fails.
**Testing scenarios:** make test-go; make e2e.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Local implementation and testing present; see the initial session log.
- [ ] Confirm the integrated behavior via M1-06.

### M1-05 — Initial deployment and automated testing

**Status:** Implemented; local checks performed in the initial session. **Owner:** DevOps.
**Depends on:** M1-02, M1-03.
**Expected files:** compose.yaml; deploy/docker/*; tests/e2e/*; .github/workflows/test.yaml; README.md.
**Produce/contract:** Minimum core, optional Ollama, internal networks, volumes and healthcheck; Offline OpenAI-compatible fixture.
**Acceptance:** Config Compose valid; no real secrets; Unit test and E2E pipeline set up.
**Testing Scenarios:** docker compose config --quiet; make test; make e2e.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Local implementation and testing present; see the initial session log.
- [ ] Confirm the integrated behavior via M1-06.

### M1-06 — Real testing Docker and PostgreSQL

**Status:** To be verified on Docker; user executes next. **Owner:** QA / user.
**Depends on:** M1-04, M1-05.
**Expected files:** tests/e2e/{run.sh,check.py}; docs/implementation-status.md.
**Produce/contract:** Run the existing stack on Docker enabled, recording command, version and result; correct any reproducible defects.
**Acceptance:** Image build, migration to empty DB, SSE, replay, reboot and persistence pass; core doesn't start Ollama/Redis/Qdrant. The trial remains open until there is real evidence.
**Testing scenarios:** make e2e; docker compose --profile core config --services.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.