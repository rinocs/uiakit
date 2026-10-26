# Milestone 5 — Integration Implementation Plan

> **For agentic workers:** use superpowers:executing-plans; superpowers:subagent-driven-development only with authorized model and delegation. Each task has a responsible owner and a verifiable gate.

**Goal:** Complete Integration according to PROJECT_SPEC.md, with verified incremental deliverables.
**Architecture:** Go has public API, permissions, and authoritative persistence; Python has AI execution and adapters. Plugins register via contracts, they do not bypass the gateway authority.
**Tech Stack:** Go + chi/pgx, Python >=3.12 + FastAPI/Pydantic; optional components and SDKs introduced by the task that requires their use.
**Spec:** [PROJECT_SPEC.md](../../project-spec.md); index and dependencies in [TASKS.md](../../TASKS.md).

**Relevant ADRs:** [0002](../../adr/0002-api-contracts-and-events.md), [0003](../../adr/0003-authorization-and-secrets.md), [0011](../../adr/0011-sdks-widget-and-console.md). States and scope in [ADR index](../../adr/README.md).

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

### M5-01 — TypeScript SDK from contract

**Status:** To be done. **Owner:** TypeScript.
**Depends on:** M2-10, M3-11, M4-10.
**Expected files:** packages/sdk-typescript/{package.json,src/index.ts,src/sse.ts}; packages/sdk-typescript/tests/*.
**Produce / contract:** Resource-typed client and public SSE, explicit idempotency keys, AbortSignal, error normalization, and terminal handling; generation/validation against OpenAPI.
**Acceptance:** Fragmented SSE/Unicode and agent.failed fixed; abort cancel; EOF didn't happen; no browser dependency on internal runtime.
**Testing scenarios:** npm test in package; typecheck; Shared OpenAPI fixtures.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-02 — PHP SDK and Laravel integration

**Status:** To be done. **Owner:** PHP.
**Depends on:** M5-01.
**Expected files:** packages/sdk-php/{composer.json,src/*,tests/*}; examples/laravel/*; docs/laravel.md.
**Produce / contract:** Server-side PHP client, iterable SSE, and Laravel client with service provider/config; endpoint example backend with key preserved server-side.
**Acceptance:** Create mock-tested assistant/conversation/message and streaming; timeouts/errors mapped; credential absent from browser payloads; Laravel/PHP compatibility documented and tested.
**Testing scenarios:** composer test in package; E2E Laravel integration with UAI mock.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-03 — Go SDK from contract

**Status:** To be done. **Owner:** Go.
**Depends on:** M5-01.
**Expected files:** packages/sdk-go/{go.mod,client.go,sse.go,client_test.go}; examples/go/*.
**Produce/contract:** Client with context.Context, typed errors, API resources and reusable SSE decoder.
**Acceptance:** Cancel and timeout propagated; parser handles split frames and abnormal EOF; explicit idempotence; contracts aligned with other SDKs.
**Test scenarios:** cd packages/sdk-go && go test -race ./... && go vet ./....
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-04 — Widget session token and CORS

**Status:** To be done. **Owner:** Go / Security.
**Depends on:** M2-02, M4-01.
**Expected files:** apps/gateway/widget_tokens.go; apps/gateway/cors.go; apps/gateway/widget_tokens_test.go; packages/api-contract/*.
**Produce / contract:** Server-side mint of temporary tokens linked to assistant/conversation, subject, scopes and expiry; explicit origins and CORS policy; dedicated revocation and rate limits.
**Acceptance:** Token widget does not access console/credentials/config; another conversation denied; deadline/cancellation respected; unauthorized origin denied; browser never uses administrative key.
**Testing scenarios:** make test-go; browser preflight testing, expired token and cross access.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-05 — Web Component chatbot

**Status:** To be done. **Owner:** Frontend.
**Depends on:** M5-01, M5-04.
**Expected files:** packages/chat-widget/{package.json,src/*,tests/*}; examples/widgets/*.
**Produce/contract:** Framework-agnostic widgets: SSE, sanitized Markdown, whitelisted quotes, theme tokens, session tokens, and public callbacks; responsive keyboard and layout.
**Acceptance:** No HTML/script execution from template; safe links; loading/error/cancel and EOF handled; focus/keyboard/screen reader; vanilla, React and Svelte demos without widget forks.
**Test scenarios:** sanitizer/SSE unit test; mobile/desktop browser testing and accessibility.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-06 — Console: Login, Assistants, and Templates

**Status:** To be done. **Owner:** Frontend.
**Depends on:** M2-10, M5-01, M5-04.
**Expected files:** apps/console/{package.json,src/*,tests/*}; deploy/docker/console.Dockerfile; compose.yaml.
**Produce / contract:** Minimal SvelteKit console with server-side administrative session, effective roles, assistants/versions, system prompt, template and directives. No workflow editor.
**Acceptance:** Secrets not sent to browser or bundle; UI controls do not replace RBAC API; errors/validation/empty/loading states; save creates version, does not alter run.
**Testing scenarios:** console typecheck/test; browser roles testing and assistant configuration.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-07 — Console: KB and documents

**Status:** To be done. **Owner:** Frontend.
**Depends on:** M3-11, M5-06.
**Expected files:** apps/console/src/routes/knowledge-bases/*; apps/console/tests/knowledge-bases/*.
**Produce / contract:** KB management, assistant associations, upload, ingestion status, errors, reindex/export and confirmed deletion.
**Acceptance:** Visible file limits before and after upload; user does not see unauthorized KB; been updated without duplicating jobs; citation opens the permitted source.
**Test scenarios:** browser test upload→job→query→source and access denied.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-08 — Console: tools, plugins and approvals

**Status:** To be done. **Owner:** Frontend.
**Depends on:** M4-10, M5-06.
**Expected files:** apps/console/src/routes/{tools,plugins,approvals}/*; apps/console/tests/extensions/*.
**Produce / contract:** Register HTTP tools via approved connectors, configure/activate already installed plugins, show health and approvals with immutable arguments and expiration.
**Acceptance:** Risk and recipient visible before approving; UI does not modify approved topics; scopeless token does not approve; no arbitrary code upload/installation.
**Testing scenarios:** browser test tool read-only, approval expires and plugin disabled.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-09 — Console: conversations, runs and playgrounds

**Status:** To be done. **Owner:** Frontend.
**Depends on:** M5-05, M5-06, M5-08.
**Expected files:** apps/console/src/routes/{conversations,runs,playground}/*; apps/console/tests/runs/*.
**Produce / contract:** History, run state, usage, redacted audit/logs and test chatbot with SSE/cancel/citations; distinguish failed, canceled and completed runs.
**Acceptance:** Duplicate events do not duplicate text; disconnection does not appear successful; protected sensitive logs; updated data without bypassing scopes.
**Test scenarios:** browser test stream stopped, replay, approval waiting and audit.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M5-10 — Gate integrations and SDK compatibility

**Status:** To be done. **Owner:** QA / Docs.
**Depends on:** M5-02, M5-03, M5-07, M5-09.
**Expected files:** tests/contracts/*; tests/e2e/check_integrations.py; docs/integrations.md; .github/workflows/test.yaml.
**Produces / contract:** Go/TS/PHP contracts array, Laravel examples and widgets; Console package/build pipeline.
**Acceptance:** SDKs validated against same OpenAPI; full Laravel integration; widget without admin key; console covers all operations of section 16; green browser accessibility and security tests.
**Test scenarios:** contract suites of all SDKs; E2E browser/backend; build packages and consoles.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.