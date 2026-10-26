# Milestone 4 — Agents Implementation Plan

> **For agentic workers:** use superpowers:executing-plans; superpowers:subagent-driven-development only with authorized model and delegation. Each task has a responsible owner and a verifiable gate.

**Goal:** Complete Agents per PROJECT_SPEC.md, with verified incremental deliverables.
**Architecture:** Go has public API, permissions, and authoritative persistence; Python has AI execution and adapters. Plugins register via contracts, they do not bypass the gateway authority.
**Tech Stack:** Go + chi/pgx, Python >=3.12 + FastAPI/Pydantic; optional components and SDKs introduced by the task that requires their use.
**Spec:** [PROJECT_SPEC.md](../../project-spec.md); index and dependencies in [TASKS.md](../../TASKS.md).

**Relevant ADRs:** [0002](../../adr/0002-api-contracts-and-events.md), [0003](../../adr/0003-authorization-and-secrets.md), [0004](../../adr/0004-directive-and-hook-lifecycle.md), [0005](../../adr/0005-plugin-trust-and-lifecycle.md), [0006](../../adr/0006-tool-effects-and-approvals.md), [0009](../../adr/0009-providers-and-model-capabilities.md). States and scope in [ADR index](../../adr/README.md).

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

### M4-01 — Persistent run state and deletion

**Status:** Completed; verified with real E2E `make test` and cancel/replay. **Owner:** Go / Python.
**Depends on:** M2-02, M2-03, M2-05.
**Expected files:** apps/gateway/agent_runs.go; apps/gateway/migrations/008_run_state.sql; apps/runtime/uai_runtime/run_state.py; apps/runtime/tests/test_run_state.py; packages/api-contract/*.
**Produces / contract:** /v1/agent-runs list/get/cancel with ownership; queued/running/waiting_approval/completed/failed/cancelled states, compare-and-set transitions, and assistant version fixed.
**Acceptance:** Illegal transitions rejected; cancel closes provider/tool ​​and produces agent.cancelled; reboot does not repeat effects; SSE/replay preserves previous semantics.
**Testing scenarios:** make test; integration cancel/restart/concurrent state update.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M4-02 — Tool authorization cannot be bypassed

**Status:** Completed; Unique policy with recheck before effect, prompt/tool ​​output/plugin/document escalations covered by tests. **Owner:** Python / Go.
**Depends on:** M2-02, M2-06, M2-07, M4-01.
**Enforced files:** packages/core/src/uai_core/builtin/directives/tool_policy.py; apps/runtime/uai_runtime/{tool_registry,plugin_manager,app}.py; apps/runtime/tests/test_tool_authorization.py; docs/tools.md; docs/builtin-directives.md; docs/adr/0006-tool-effects-and-approvals.md.
**Produce / contract:** Effective permissions = intersection principal/scopes, assistant version, registry, and connector policy. ToolPolicyDirective required; the model offers only tool_id and arguments.
**Acceptance:** Unknown or disallowed tool never run; template/plugin/retrieval does not broaden permissions; policy re-evaluated before taking effect after awaiting approval.
**Testing scenarios:** make test-python; escalation testing from prompt, tool output, plugin and document.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M4-03 — Secure HTTP executor and connector

**Status:** Completed; read-only HTTP executor with administrative connectors, SSRF/DNS pinning, redirect/proxy off, limits and secret refs; MCP remains contracted. **Owner:** Python / Go.
**Depends on:** M2-07, M4-02.
**Files implemented:** apps/runtime/uai_runtime/tools/{http,connectors}.py; apps/gateway/{connectors,tools}.go; apps/runtime/tests/test_http_tools.py; docs/http-tools.md; packages/api-contract/*.openapi.json.
**Produce / contract:** Administrative connectors with destination, methods, path, header secret references, schemas, timeout, response limit and retry policy; HTTP executor does not accept arbitrary URLs from the template; MCP executor contract prepared.
**Acceptance:** Block loopback/link-local/metadata and unauthorized networks; private services only explicitly allowlist; DNS rebinding/redirect/proxy does not bypass policy; secrets do not return to the model. Mutant tools not publishable before M4-05.
**Testing scenarios:** make test; HTTP SSRF fixtures, redirects, DNS and oversized responses.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.### M4-04 — Constrained human approvals

**Status:** Completed; Canonical binding, list/get/approve/reject API, concurrent decision and run resume verified on real PostgreSQL. **Owner:** Go / Python.
**Depends on:** M2-02, M4-01, M4-02.
**Files implemented:** apps/gateway/{approvals,approval_store}.go; apps/gateway/migrations/011_approvals.sql; apps/runtime/uai_runtime/approvals.py; apps/gateway/approvals_test.go; apps/runtime/tests/test_approvals.py; tests/e2e/check_approvals.py; packages/api-contract/public.openapi.json; docs/approvals.md.
**Produce / contract:** /v1/approvals list/get/approve/reject; immutable binding to run, tool/version, canonical topic digest, authorizing principal, snapshot policy, and expiration.
**Acceptance:** Modified topics/version invalidate approval; expired/revoked/reused denied; scopeless approver denied; run waiting_approval restarts only after decision persists.
**Testing scenarios:** make test-go; integration double competitor approval and topics changed.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M4-05 — Idempotent and retry executions of effects

**Status:** Completed; durable reservation, read-only retry, unknown/reconcile and approval consumption verified on real PostgreSQL. **Owner:** Go / Python.
**Depends on:** M4-03, M4-04.
**Files implemented:** apps/gateway/migrations/012_tool_executions.sql; apps/gateway/{tool_executions,tool_execution_store}.go; apps/runtime/uai_runtime/tool_executor.py; apps/runtime/tests/test_tool_idempotency.py; apps/gateway/tool_executions_test.go; tests/e2e/check_tool_executions.py; docs/tool-executions.md.
**Produce / contract:** Input validation→auth→limits→approval→durable reservation→executor→output validation→audit→result. Stable idempotent key propagated to connector when supported.
**Acceptance:** Limited read-only retry; mutant action without guarantee idempotent never blindly retried; crash after effect with unknown outcome produces unknown state to be reconciled, with no exactly-once promise over external HTTP.
**Test scenarios:** integration timeout before/after effect and concurrent retry; bad schema test output.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M4-06 — Agent loop with tool calling

**Status:** Completed; deltas tool providers, multi-step loops, authorized read-only tools and verified untrusted results. **Owner:** Python.
**Depends on:** M4-01, M4-02, M4-05.
**Files implemented:** apps/runtime/uai_runtime/{agent,provider,tool_loop,app}.py; packages/core/src/uai_core/{models,providers}.py; apps/runtime/tests/test_agent_loop.py; apps/runtime/tests/test_provider.py; docs/agent-loop.md.
**Produce / contract:** Incremental accumulation tool_call_id/name/JSON provider, authorized calls, tool result, new generation and terminal. Capability tool_calling required; state persisted via gateway contract.
**Acceptance:** Direct response and multiple correct steps; Partial/malformed JSON never executed; tool result does not become privileged instruction; no model code in the process.
**Testing scenarios:** make test-python; mock provider with tool request→result→response.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M4-07 — Budget, context window and structured output

**Status:** Completed; budget step/tool/token/context, transparent usage and validated structured output. **Owner:** Python.
**Depends on:** M2-03, M2-06, M4-06.
**Files implemented:** apps/runtime/uai_runtime/{budgets,token_usage,agent,tool_loop,app}.py; packages/core/src/uai_core/{configuration,builtin/directives/output_validation}.py; apps/runtime/tests/test_execution_limits.py; docs/budgets.md.
**Produces / contract:** Limits max_steps/max_tool_calls/max_tokens/duration per run; context count/limit consistent with model; aggregate usage and costs only with known rates; structured_output validated if capability available.
**Acceptance:** Infinite loop, tool storm, duration and token budget stopped; bad output scheme fails; usage unknown distinct from zero; unknown cost not invented; no retry after delta.
**Testing scenarios:** make test-python; budget edge cases including failed tool steps and approval waits.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M4-08 — Audit of sensitive operations

**Status:** Completed; transactional audit, centralized editing and protected reading. **Owner:** Go / Python.
**Depends on:** M2-02, M2-05, M4-05, M4-07.
**Files implemented:** apps/gateway/{audit,audit_test,store,assistant_store,credential_store,approval_store,agent_run_store,tool_execution_store}.go; apps/gateway/migrations/013_audit_executions.sql; apps/runtime/uai_runtime/{audit,tool_executor,tool_loop,app}.py; apps/runtime/tests/test_audit.py; packages/api-contract/public.openapi.json; docs/{audit,auth,approvals,tool-executions}.md; tests/e2e/{check_approvals.py,run.sh}.
**Produce / contract:** Authorization, configuration, approval and tool execution events with actor/run/correlation/digest/outcome; protected audit reading. Centralized editing of sensitive fields.
**Acceptance:** Secrets and auth headers never registered; rebuildable execution/approval; audit error before the effect blocks the sensitive action; retention linked to policy M6-01.
**Testing scenarios:** make test; capture logs and verify the absence of secrets/confidential bodies.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.### M4-09 — HTTP isolated plugins

**Status:** Completed; HTTP plugin isolated in container, versioned protocol and policy connector. **Owner:** Python / DevOps.
**Depends on:** M2-09, M4-02, M4-03, M4-08.
**Files implemented:** apps/runtime/uai_runtime/plugins/{__init__,http_plugin}.py; packages/plugin-sdk/src/uai_plugin_sdk/{manifest,plugin}.py; apps/runtime/uai_runtime/{plugin_manager,tool_registry,app}.py; plugins/examples/isolated-http/server.py; configs/plugins/isolated-example.json; deploy/docker/{isolated-plugin,runtime}.Dockerfile; apps/runtime/tests/test_isolated_plugins.py; tests/e2e/{check_isolated_plugin.py,compose.yaml,run.sh}; docs/plugins.md.
**Produce / contract:** Manifest isolated HTTP with separate process/container, versioned protocol, health, activation and connector policy. No import of isolated code in runtime.
**Acceptance:** Isolated crash/timeout; auth connector and tool authorization required; limited network/container permissions; trusted remains a distinct category, without the promise of a sandbox.
**Testing scenarios:** HTTP plugin integration in containers and protocol/timeout unit tests.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M4-10 — Gate Agents with mock real HTTP tool

**Status:** Completed; read-only and mutant gate with approval, replay, limits, audit and SSE. **Owner:** QA.
**Depends on:** M4-06, M4-07, M4-08, M4-09.
**Implemented files:** tests/e2e/{check_agents,run_mutating_tool,mock_tool}.py; tests/e2e/{compose.yaml,run.sh,mock_provider.py}; apps/runtime/uai_runtime/{app,tool_loop}.py; apps/runtime/uai_runtime/tools/{connectors,http}.py; packages/core/src/uai_core/builtin/directives/tool_policy.py; docs/agents.md.
**Produce / contract:** Complete read-only and mutant scenario with pass, fail, cancel and controlled resume.
**Acceptance:** Unauthorized tool does not reach server; immutable approval; retry does not duplicate the effect; effective limits; Consistent SQL run/tool/audit; SSE terminal correct.
**Testing scenarios:** make test; make e2e with agent scenarios and real Docker gate.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [ ] Prepare fixture and test criteria above; execute and observe expected failure.
- [ ] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [ ] Run the indicated test and the core suite; correct errors before the dependent task.
- [ ] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.