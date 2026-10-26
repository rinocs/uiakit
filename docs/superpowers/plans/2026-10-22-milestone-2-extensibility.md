# Milestone 2 — Extensibility Implementation Plan

> **For agentic workers:** use superpowers:executing-plans; superpowers:subagent-driven-development only with authorized model and delegation. Each task has a responsible owner and a verifiable gate.

**Goal:** Complete Extensibility according to PROJECT_SPEC.md, with verified incremental deliverables.
**Architecture:** Go has public API, permissions, and authoritative persistence; Python has AI execution and adapters. Plugins register via contracts, they do not bypass the gateway authority.
**Tech Stack:** Go + chi/pgx, Python >=3.12 + FastAPI/Pydantic; optional components and SDKs introduced by the task that requires their use.
**Spec:** [PROJECT_SPEC.md](../../project-spec.md); index and dependencies in [TASKS.md](../../TASKS.md).

**Additional ADR:** [0013 — versions and snapshots](../../adr/0013-assistant-version-snapshots.md).

**Relevant ADRs:** [0002](../../adr/0002-api-contracts-and-events.md), [0003](../../adr/0003-authorization-and-secrets.md), [0004](../../adr/0004-directive-and-hook-lifecycle.md), [0005](../../adr/0005-plugin-trust-and-lifecycle.md), [0009](../../adr/0009-providers-and-model-capabilities.md), [0010](../../adr/0010-memory-and-data-lifecycle.md). States and scope in [ADR index](../../adr/README.md).

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

### M2-01 — Public core and execution context

**Status:** Completed with local checks and Milestone 2 Docker/E2E gates. **Owner:** Python.
**Depends on:** M1-01, M1-03.
**Expected files:** packages/core/pyproject.toml; packages/core/src/uai_core/{context,agent,memory}.py; apps/runtime/uai_runtime/agent.py; apps/runtime/tests/test_context.py.
**Produce/contract:** Typed ExecutionContext, Agent/AgentRuntime, and MemoryProvider with read/write/delete/retention; reuse and transfer existing contracts without duplicating them. Working memory per run, conversation memory delegated to gateway persistence.
**Acceptance:** Principal, permissions and limits are not editable from template content; working memory isolated between runs; no automatic semantic memory.
**Test scenarios:** cd apps/runtime && python -m pytest tests/test_context.py -q.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

### M2-02 — Credentials, scopes and ownership

**Status:** Completed; migration, ownership, revocation and expiry verified on real PostgreSQL. **Owner:** Go / Security.
**Depends on:** M1-02.
**Expected files:** apps/gateway/auth.go; apps/gateway/authorization.go; apps/gateway/migrations/002_credentials_audit.sql; apps/gateway/auth_test.go; packages/api-contract/public.openapi.json.
**Produce / contract:** Rotating/revoking/expiring hashed credentials; administrative RBAC and scopes; principal and resource ownership in the internal contract. Administrative APIs for secure credentials; Explicit bootstrap compatible with initial key.
**Acceptance:** Roles/scopes matrix documented and tested; reader does not modify; revoked credential denied; access to someone else's resource denied before runtime; audit drawn up without secrets.
**Testing scenarios:** cd apps/gateway && go test -race ./...; go vet ./....
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Complete local suite passed; E2E auth scenarios added.
- [x] Run migration and ownership/revoke/expiry scenarios on real PostgreSQL.
- [x] Local contracts and negative cases verified, log and TASKS updated.

### M2-03 — Assistant and model catalog versions

**Status:** Completed; 003 migration, replay and concurrency verified on real PostgreSQL. **Owner:** Go / Python.
**Depends on:** M2-01, M2-02.
**Expected files:** apps/gateway/assistants.go; apps/gateway/models.go; apps/gateway/migrations/003_assistant_versions_models.sql; configs/assistants/*; configs/models/*; apps/runtime/uai_runtime/capabilities.py; apps/gateway/assistants_test.go; apps/runtime/tests/test_capabilities.py.
**Produce / contract:** Immutable versions of AssistantConfig: id, name, description, prompt, template, directives, allowed tools, skills, KB, memory, limits and policies. GET/PATCH assistant, versions and /v1/models; capability chat/streaming/tool_calling/structured_output/embeddings/reranking/vision.
**Acceptance:** Each run fixes version and capability; modifying config does not change run in progress; missing capability rejected; provider secrets resolved via administrative references, never returned.
**Testing scenarios:** make test; OpenAPI test contracts and version fixtures.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Local suite, contracts and Go/Python fixtures passed.
- [x] Migration 003, replay and concurrent PATCH on real PostgreSQL.
- [x] Negative cases and local limits verified; register, ADR and TASKS updated.### M2-04 — Clean and secure directive pipeline

**Status:** Completed; Docker/E2E gate verified. **Owner:** Python / Go.
**Depends on:** M2-01, M2-03.
**Files implemented:** packages/core/src/uai_core/directives.py; apps/runtime/uai_runtime/{agent,app,models}.py; apps/gateway/{assistants,directives}.go; test_directives.py; directives_test.go; tests/e2e/check_directives.py.
**Decision:** Consolidated pipeline in core, without duplicate wrapper in runtime; authenticated validation delegated to the owner register.
**Produce / contract:** Directive.before_model/after_model applied to ExecutionContext; dynamic register, priorities and dependencies with deterministic topological ordering; Explicit timeout and error policies.
**Acceptance:** Missing loops and dependencies rejected; stable order with equal priority; timeout produces controlled failure; mandatory security directives that cannot be removed or bypassed by plugins.
**Testing scenarios:** cd apps/runtime && python -m pytest tests/test_directives.py -q.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

- [x] Run `make e2e` with Docker/PostgreSQL available; directive scenario already connected.

### M2-05 — Typed events and observation hooks

**Status:** Completed; Docker/E2E gate verified. **Owner:** Python / Go.
**Depends on:** M2-01, M2-04.
**Files implemented:** packages/core/src/uai_core/events.py; apps/runtime/uai_runtime/{hooks,agent,app}.py; apps/gateway/events_test.go; apps/runtime/tests/test_hooks.py; packages/api-contract/lifecycle.schema.json; tests/e2e/check_hooks.py.
**Decision:** lifecycle metadata separated from public stream v1; reused the existing gateway boundary without a second event parser.
**Produce / contract:** All section 6 lifecycle payloads with version, correlation_id and run_id; tidy async subscriber registration; Observational hooks receive immutable snapshots, modifying middleware passes through the authorized pipeline.
**Acceptance:** Verified lifecycle sequence; subscriber does not change status or privileges; timeout/observational error isolated and audited; mandatory middleware error abort run; SSE v1 compatible additions.
**Testing scenarios:** make test; Contract snapshot and hook order/error testing.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

- [x] Run `make e2e` with Docker/PostgreSQL available; metadata sink and check lifecycle already connected.### M2-06 — Initial built-in directives

**Status:** Completed; Docker/E2E gate verified. **Owner:** Python.
**Depends on:** M2-04, M2-05.
**Enforced files:** packages/core/src/uai_core/builtin/directives/{system_prompt,conversation_memory,output_validation,observability,tool_policy}.py; packages/core/src/uai_core/{context,directives}.py; apps/runtime/tests/test_builtin_directives.py; tests/e2e/check_builtins.py.
**Decisions:** built-ins installed by the wheel core; readonly final host guards. Conversational memory from existing gateway; Python adapter mutant/retention realigned to M6-01 (ADR 0010), without persistence stubs.
**Produces/contract:** SystemPromptDirective, ConversationMemoryDirective, OutputValidationDirective, ObservabilityDirective, and ToolPolicyDirective; the latter deny-by-default, extended in M4. RAGRetrievalDirective arrives in M3-11.
**Acceptance:** Operator prompt preserved; authorized history; non-compliant output fails; telemetry without prompts/secrets; policy cannot be deactivated by the assistant.
**Testing scenarios:** cd apps/runtime && python -m pytest tests/test_builtin_directives.py -q.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

- [x] Run make e2e with Docker/PostgreSQL available; built-in scenario already connected.

### M2-07 — Tool registry and executor built-in

**Status:** Completed; Docker/E2E gate verified. **Owner:** Python / Go.
**Depends on:** M2-01, M2-02, M2-05.
**Files implemented:** packages/core/src/uai_core/tools.py; apps/runtime/uai_runtime/tool_registry.py; packages/core/src/uai_core/builtin/tools/text_stats.py; apps/runtime/tests/test_tool_registry.py; apps/gateway/{tools,tools_test}.go; tests/e2e/{check_tools,run_tools}.py.
**Decisions:** schemas derived from Pydantic templates host extra=forbid; no custom JSON Schema interpreter. Registry shared by catalog and factory executor. Standalone read-only; template/approval/HTTP loop in M4 tasks.
**Produce/contract:** ToolDefinition with id/name/description/version/input_schema/output_schema/permissions/risk_level/timeout/retry_policy/executor; unique registry and built-in executor; /v1/tools with scopes.
**Acceptance:** Duplicate ID rejected; input/output schema validation; deny-by-default before executing; timeout and failure audited; read-only example testable without template. No execution of generated code.
**Testing scenarios:** make test; test executor with local tool fixture and hostile input.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.- [x] Run make e2e with Docker/PostgreSQL available; public catalog and executor in the container already connected.

### M2-08 — SDK plugins, manifests and local skills

**Status:** Completed; Docker/E2E gate verified. **Owner:** Python.
**Depends on:** M2-01, M2-04, M2-05, M2-07.
**Files implemented:** packages/plugin-sdk/pyproject.toml; packages/plugin-sdk/src/uai_plugin_sdk/{manifest,plugin,skills}.py; packages/core/src/uai_core/hooks.py; apps/runtime/tests/{test_plugin_manifest,test_skills}.py; tests/e2e/run_plugin_sdk.py; Makefile, CI and Dockerfile runtime.
**Decisions:** PEP 440 releases with packaging, graphlib for dependencies; manifest metadata-only and registrar SDK without grant. POSIX SkillLoader with relative descriptors and O_NOFOLLOW, without insecure fallback; no activation as long as M2-09 is missing.
**Produce / contract:** Manifest with core compatibility, dependencies, capabilities, config and permissions connector; Public Plugins and Skills; skills from administratively approved directories/packages, delimited contents and no implicit privileges.
**Acceptance:** Invalid manifest, incompatibility, dependency cycle, path traversal and missing skill rejected; the permissions declared do not grant runtime permissions.
**Test scenarios:** cd apps/runtime && python -m pytest tests/test_plugin_manifest.py tests/test_skills.py -q.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.

- [x] Run make e2e with Docker/PostgreSQL available; smoke SDK/skill in the already connected container.

### M2-09 — Loader plugin and administrative integration

**Status:** Completed; Docker/PostgreSQL/E2E gate checked. **Owner:** Python / Go.
**Depends on:** M2-02, M2-03, M2-08.
**Expected files:** apps/runtime/uai_runtime/plugin_manager.py; apps/gateway/plugins.go; apps/gateway/migrations/004_plugins.sql; plugins/examples/hello/*; apps/runtime/tests/test_plugins.py; tests/e2e/check_plugins.py.
**Produce / contract:** Discovery only from approved trusted installations, dependency resolution, loading/registration, activate/deactivate/configure/health/logging; /v1/plugins. Example installed in the build, activated by assistant.
**Acceptance:** Isolated and visible plugin error; deactivation leaves no registered tools; collision-free namespace; no arbitrary installation/hot reload via API; explicitly trusted not sandboxed.
**Testing scenarios:** make test; E2E hello plugin with active directive only on the chosen assistant.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run local Python/Go suites and contract/build/Compose controls; see progress.md.
- [x] Run make e2e with Docker/PostgreSQL: smoke runtime and public administration, SQL audit and restart connected to the runner.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.### M2-10 — Gate Extensibility and plugin SDK guide

**Status:** Completed; gate Extensibility checked with `make test` and `make e2e`. **Owner:** QA / Docs.
**Depends on:** M2-06, M2-07, M2-09.
**Expected files:** tests/e2e/check_extensibility.py; docs/plugins.md; docs/runtime-lifecycle.md; .github/workflows/test.yaml.
**Produces / contract:** Fixture plugin, lifecycle diagram, manifest/directive/hook/tool/skill examples and core regression tests.
**Acceptance:** Example installation, directive activation and deactivation verified; hook does not change authority; green auth/lifecycle/ordering/discovery/validation tests; Docker M1 gate required before milestone closure.
**Testing scenarios:** make test; make e2e with scenario extensibility; core typing/static checks.
**Implementation:** the gate reuses `check_plugins.py`, `check_plugin_admin.py`, `check_hooks.py` and core suites instead of duplicating a `check_extensibility.py` scenario; the criteria→test array is in [runtime-lifecycle.md](../../runtime-lifecycle.md). The existing CI runs `make test` and `make e2e`.
**Basic commands:** `make test`; `make e2e` when the task includes services or browsers. Connect the new suites to the targets in the task that introduces them; for SDK/console declare test/check/build package scripts in the same task. Required outcome: all cases of the task pass, no regression in the core; integration tests require the declared services.

- [x] Prepare fixture and test criteria above; execute and observe expected failure.
- [x] Implement the contract in the owner layer, including necessary migrations/config/documentation.
- [x] Run the indicated test and the core suite; correct errors before the dependent task.
- [x] Check contracts, negative cases and limits; record commands/evidence and update TASKS.md.