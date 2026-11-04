# Implementation log

Active plan: [Milestone 6](superpowers/plans/2026-10-22-milestone-6-production-hardening.md).
Authoritative backlog: [TASKS.md](TASKS.md). M1–M5 are completed and verified.

## 2026-10-22 — M2-01 completed (local verification)

- Baseline before changes: 16 Python and 7 Go tests with race detectors/vets passed.
- Implementation authorized by the user; local execution because the model
  requested subagent is not available. Git/worktree not usable in the workspace.
- Border: installable Python core, without FastAPI/httpx; the runtime maintains DTO
  HTTP and adapter providers. ModelProvider/ModelChunk/events are consolidated into
  core with re-export for compatibility, not recopied.
- Invariants: immutable permissions, operator prompts and limits; new context e
  working memory per call; model output cannot change authority; none
  semantic memory. PostgreSQL and conversation commits remain in the gateway.
- Ruling: MemoryProvider is the read/write/delete/retention contract; the adapter
  persistent conversation remains in task M2-06, without now introducing a second one
  DB path or unauthorized mutation endpoint. Cost: No new API
  Persistence Python until M2-06 attaches it to gateway policies.

### Steps M2-01

- [x] Test red: immutability, isolation, content updates, limits and lifecycle.
- [x] Uai-core package and integration into real API path.
- [x] Monorepo consistent installation/package, CI and Dockerfile.
- [x] Complete suite and task/ADR/documentation update.

### Evidence M2-01

- `make test`: 31 Python tests, 7 Go with race detector; green vet.
- Wheel uai-core built and installed, import from /tmp without FastAPI/httpx;
  py.typed marker present. Editable installation verified for development.
- Public/internal OpenAPI unchanged; compileall and Compose config green.
- Docker not executed, as agreed; no real E2E statement.

## M2-02 implemented — PostgreSQL gate opened

- Roles: admin (installation resources), operator (own resources), reader
  (reading own resources). Scopes reduce role permissions, never expand them.
- Key persist only as digest; creation/rotation returns the secret one
  only once. Revocation/expiration blocks subsequent requests.
- Ruling: persistent principal distinct from the credential; more keys than the same
  principal can have reduced scopes/roles. Cost: a principals table,
  necessary to maintain stable ownership during rotation/revocation.
- Incremental migration: M1 data assigned to bootstrap-operator; bootstrap
  compatible, without rewriting or deleting existing messages.
- [x] Test red auth/scopes/credentials.
- [x] Middleware, SQL ownership, migration and administrative audit.
- [x] Internal principal contract, API/OpenAPI and E2E auth scenarios.
- [x] Complete suite and revision of local boundaries.
- [ ] Real PostgreSQL gate (migration, ownership, expiry/revoke, restart).

### Evidence and limitations M2-02

- Updated local tests: 33 Python and 14 Go tests (plus RBAC subcases), with races
  detector and vet. Public/internal OpenAPI validated; SSE compatibility preserved.
- Principals, key hashed, revoke/rotate/expiry, scopes, ownership and audit implemented.
  Resource ownership is filtered in the SQL layer, not just in individual handlers.
- E2E auth added to run.sh: two isolated principals, reader on same principal,
  rotation, revocation, expiry and absence of secrets from the list. Not run on real DB.
- Ruling: no self-revoke/self-rotate of the authorizing key. Cost: one admin
  requires a separate key or bootstrap to replace its own key.
- Ruling: no automatic retry of the key creation/rotation API and no replay
  of the persisting secrecy. Cost: Lost response requires new key/rotation using
  a separate admin. Idempotent replay of tool effects remains M4-05.
- Open gate: 001→002 migration, SQL auth, DB race and actual reboot; Docker
  remains to be verified by the user, without declaring the entire M2-02 complete.
- Next task: M2-03. M2-04…M2-10 and the previous integrated gates remain open.### Fix emerged from review

A valid assistant response of 40,000 characters was rejected by DTO history
in the next round, because Message shared the user limit of 32,000. Test red
reproduced (422 instead of 200), then green: assistant up to 64,000, user remains
32,000, overall run budget unchanged. Internal scheme updated with constraint
conditional by role; public message contract unchanged.

### Local final test

`make test`: 33 Python and 14 Go, race detectors and green vets. `compileall`, syntax
E2E shell and Compose config (core + E2E override) green. Updated gateway build.
Docker/SQL evidence remains open; no release or deployment performed.

## M2-03 implemented — PostgreSQL gate opened

- Invariant: PATCH creates a new immutable configuration; the run saves the
  version and the catalog snapshot before calling the runtime. A retry uses
  the original snapshot, not the most recent configuration.
- PATCH with If-Match/ETag avoids lost updates. Ownership and scopes applied
  also single GET and reading versions.
- Ruling: the runtime owns the effective capabilities of its adapter; the gateway
  imports metadata without secrets. The admin API can configure provider kind, base
  URL, model catalog and a secret reference after runtime validation and egress
  checks; secret values are never stored or returned. Cost: one additional
  authenticated call per provider change, with runtime pull reconciliation.
- Extension fields present in the configuration but not yet implemented
  are rejected if enabled: do not ignore required tool/skill/RAG/structured output.
- [x] Test red versions, conditional PATCH and capability.
- [x] Migration 003 and transactional snapshots in the real run path.
- [x] Runtime with authenticated catalog, snapshot capabilities and limits.
- [x] OpenAPI, E2E scenarios, documentation and full local verification.
- [ ] Run PostgreSQL/Docker scenarios: migration, lock, replay and memory off.

### Evidence M2-03

- Baseline: 33 Python and 14 Go before changes.
- Current suite: 43 Python, 19 Go with race detector/vet; shared fixture config
  in the two languages, public/internal OpenAPI validated and private snapshot updated.
- New routes: GET /v1/models, GET/PATCH /v1/assistants/{id}, GET .../versions.
  ETag/If-Match with 428/412; X-Run-ID and X-Assistant-Version also on replay.
- Historical configurations and model metadata saved in the run before invocation;
  lock head separated from read version to avoid rechecks on mutable joins.
- E2E scenarios added: replay after PATCH, new run version, two writers same
  Expected ETag [200,412], ownership versions and conversation memory disabled.
- New contracts consolidated in packages/core/{capabilities,configuration}; none
  copying domain models to the runtime. No new dependencies introduced.
- Limitations: an active backend; no token-aware budget yet; future options rejected
  if activated. Memory off omits history from provider, does not delete persisted data.
- Ruling: update runtime before gateway. Cost: the new gateway does not start
  against old runtime without catalog. SQL 003 prevents schema downgrade;
  Compatible backup/restore remains necessary for full rollback.
- Detailed decision in ADR 0013. No migration applied on real data,
  no Docker/E2E declared passing and no publish/deploy performed.
- Next task: M2-04. Real gates M1-06, M2-02/M2-03 remain open.

### Final check M2-03

`make test`: 43 Python and 19 Go with race detector/vet passed. Build gateways,
compileall, shell syntax and Compose config passed. Wheel rebuilt with new ones
modules and imported from isolated directory without FastAPI/httpx. Connections of
new validated documents. Real Docker and PostgreSQL not running, as agreed.

## M2-04 — runtime pipeline implemented, open public integration- [x] RED observed: test_directives.py fails on missing uai_core.directives.
- [x] Core contract with trusted registry, selection by assistant, dependencies,
  stable ordering, cooperative timeouts and fail/continue policies.
- [x] Mandatory host directives always selected, duplicates not replaceable;
  returns reconstructed and validated to protect context and budget input.
- [x] BasicAgent applies before/after in global timeout; after law
  immutable model_output, without altering delta SSE or saturating history.
- [x] 20 new tests; full suite: 63 Python, Go races/vets passed (19 Go tests).
  Internal OpenAPI snapshot regenerated and verified by the suite.
- [ ] Authenticated catalog/validation shared with gateway and enablement
  publishes registered names. M2-04 remains ongoing, not declared complete.
- Ruling: after_model valid only; does not rewrite output already sent. Cost:
  a late refusal ends the run but cannot collect deltas already delivered.
- Ruling: keep public activation closed until validation is missing
  shared. Cost: Directive configuration available only at runtime
  trusted in this iteration. No public configurations ignored.
- Author's local review: checked boundaries, SSE cycle, full history,
  deletion and model_copy. No independent reviewer: template required
  deepseek-4.1-flash not available; no replacement used.
- Docker/PostgreSQL not running; previous gates remain open.

## M2-04 — closing implementation and local verification

- [x] RED observed in runtime: validation endpoint missing (404 instead of 401).
  RED Go: POST/PATCH reject valid selections before the runtime call.
- [x] Endpoint Bearer POST /internal/v1/directives/validate: build the graph,
  does not perform callbacks; 204 valid, 422 for invalid names/duplicates/dependencies/loops.
- [x] Public POST/PATCHES accept a maximum of 64 unique names in the expected format.
  The gateway validates the non-empty selection before calling persistence.
  Private/network failures result in 503 runtime_unavailable; timeout 5 seconds,
  Redirects blocked and no private details forwarded. No automatic retry.
- [x] PATCH with [] remove optional selection for future runs and preserve
  the historical versions; mandatory host directives remain enforced by the core.
- [x] Local runtime/gateway and Docker fixture tests: authorization, selection,
  versions, rejections without persistence, redirect/deadline, after-model and factory
  trusted. The basic deployment does not yet register built-in directives.
- [x] Public/internal OpenAPI updated; contract in docs/directives.md,
  updated plan, backlog, implementation-status and ADR 0004.
- [x] Scenario tests/e2e/check_directives.py linked to make e2e: activation,
  invalidation, deactivation, versions/replays and after-model rejection. The factory
  test is only mounted in the E2E override; unchanged production.
- [ ] Run make e2e with Docker: one gate remains open, as agreed.

### Final evidence M2-04

`make tests`: 65 Python and 22 top-level Go tests with race detector/vet passed.
Build gateway, compileall (core/runtime/E2E), shell syntax and Compose config
core+override E2E passed. Wheel core rebuilt and imported from isolated directory:
registry/directives present, without importing FastAPI/httpx. No migration
new, no deployment, real Docker/PostgreSQL not running.

Ruling: delegate validation to the runtime owner instead of copying the catalog e
the algorithm in Go. Cost: creation/PATCH with non-empty selection depend on
runtime availability (503 checked); empty lists remain compatible.
The pipeline lives in the core, without a second directive_pipeline.py wrapper.
Revalidation at run startup handles post-run deployment changes
validation; the snapshot preserves names, not a copy of the plugin code.Final local review by author: checked existing authentication and scope,
absence of redirect/retry, preconditions/versions, no validation callbacks,
SSE and fixture mounted only in E2E. No independent reviewer: template required
not available, no used replacement. No local blocking problems emerged.
Next task: M2-05. All previous Docker/PostgreSQL gates remain open.

## M2-05 — typed events and implemented observation hooks

- [x] RED observed: LifecycleEvent missing from test_hooks.py collection.
- [x] Core contract for all 18 phases of the specification, specific payloads
  immutable and JSON schema that binds phase/payload. Common Envelope with SSE v1;
  observations of the four public frames retain identity and correlation.
- [x] Subscriber async host with priority/name order, filters, snapshots per run and
  independent copy for callback. No context, authority, working memory,
  text, prompts, or tool/memory data delivered to observers.
- [x] Timeout for callback (default 50 ms), total budget 1 second per run;
  isolated errors, diagnostics without exceptions/contents/credentials. Cancellation
  of the caller propagated; no queues or abandoned observation tasks.
- [x] Real BasicAgent sequence linked to lifecycle events. Tools/memory event
  defined but not fictitiously issued before their respective capacities.
- [x] Mandatory middleware rejection observed as agent.failed before
  providers; failed after-model does not produce completed. External terminal notification
  at the execution timeout, in the residue of the budget hook, to avoid double terminal.
- [x] Further RED observed: closing after delta leaves provider suspended.
  GREEN: explicit upstream closure before return; test inside the loop,
  without relying on asyncio.run's deferred cleanup. Clean working memory
  from AgentRuntime on cancellation even during a callback.
- [x] Public SSE contract unchanged and Go testing against internal metadata frames.
  Reused the gateway owner parser: no second events.go parser introduced.
- [x] Fixture E2E with metadata sink in test runtime only; check_hooks.py
  connected to make e2e checks order, terminals and no new traces on replays.
- [x] Documentation events-hooks.md, lifecycle schema, backlog/plan and ADR 0002/0004.
- [ ] Run make e2e with Docker/PostgreSQL available: real gate open.

### Evidence M2-05

`make tests`: 77 Python and 23 top-level Go tests with race/vet passed. Build gateways,
compileall core/runtime/E2E, shell and Compose config core+override passed. Wheel
core rebuilt; no new dependencies introduced. Internal OpenAPI contract
still corresponding to the existing snapshot; schema metadata in an artifact
separated, compared in tests. No real SQL migration, deployment or Docker testing.

Ruling: Observational lifecycle separated from SSE v1 to preserve current clients.
Cost: New stages are available to trusted subscribers, not SSE clients;
any public exhibition will require a dedicated compatible contract.

Author's local final revision: Checked snapshots without references to
context, filters/order, isolated budget per run, deletion and termination of providers,
absence of a second terminal and public border. No independent reviewers:
Requested model not available and no used replacement. No local blocking
emerged. Observations are best efforts and logs are not durable PostgreSQL audits;
the run limit includes intermediate notifications, while terminals and deletion
remain bounded by the remaining budget hook. Details in the contract.
Next task: M2-06. Previous Docker/PostgreSQL gates still open.

## M2-06 — starting built-in directives

Implement five stateless guards in the core package already installed in the runtime:
operator prompt consistent with snapshot, history limited to authorized history
initial, non-empty text output, metadata-only telemetry, and deny-by-default tool.
Always register them in the factory and in the BasicAgent, even when deploying
provides a custom register. Do not introduce SQL retrieval or dummy tools.Ruling: Place implementations in uai_core.builtin.directives, instead of one
plugins folder not yet installable; use the same Directive contract e
the existing wheel. Cost: Future plugin loader will need to import these built-ins.

Host guards are sorted after all middleware and cannot change
messages. A dependency that requires middleware after a guard is invalid.
This closes the case where a middleware modifies history after a check.
The context preserves the original history as a protected snapshot per run; middleware can shorten it to an authorized suffix, not invent it.

### M2-06 — deployment complete, verify locally

- [x] RED observed: uai_core.builtin missing from test collection.
- [x] Five classes distributed in the wheel core and installed by the BasicAgent:
  SystemPromptDirective, ConversationMemoryDirective, OutputValidationDirective,
  ObservabilityDirective, ToolPolicyDirective. No plugin loader required.
- [x] register_guard: guards always selected, readonly, sorted after all
  middleware; dependencies requiring middleware after a guard rejected.
  Collisions on built-in names cause the factory to fail. Repeatable installation
  on the same registry and new host registrations still visible on future runs.
- [x] ExecutionContext captures authorized_history only once and protects it
  through with_messages/with_output and rebuilding the pipeline. Guard
  conversational allows only authorized suffixes and last user role; memory
  off prevents history. Ownership and persistence remain in the gateway paths.
- [x] Validate blank/whitespace/over-budget output; prompt preserved; logging
  INFO with counts and correlation only; authorize_tool also denies IDs granted to
  caller in this profile without executor. Structured output/RAG remain future.
- [x] 14 new built-in test cases, including HTTP integration with custom registry,
  high priority middleware and attempts to spoof provenance history.
- [x] check_builtins.py linked to make e2e: public names, empty list, whitespace,
  extraneous history after middleware and failed replay. Fixture only in Docker tests.
- [x] Backlog/plan, built-in contract and ADR 0004/0010 updated.
- [ ] Run make e2e with Docker/PostgreSQL available: real gate open.

Ruling: Update previous mutant MemoryProvider adapter referral from
M2-06 to M6-01, along with retention/deletion policies and scope gateways.
Product conversation persistence already exists in the gateway. Cost: API
Python write/delete/retention still unavailable; no simulated mutations.
The referral is also traced in sheet M6-01 and in ADR 0010.

### Final evidence M2-06

`make test`: 91 Python and 23 Go with race/vet passed. Build gateway, compileall
core/runtime/E2E, shell and Compose config core+override passed. Wheel rebuilt,
extracted into isolated directory and used to perform both phases of the five
guards without FastAPI/httpx. OpenAPI contracts and lifecycles still matching
to existing snapshots. No new dependencies or SQL migrations.

Local review by the author: final order and readonly of the guards verified,
preservation of source history, custom/reused registers, nothing contained in
log and deny-by-default tools. No independent reviewer: no template required
available, no used replacement. No local blocking problems emerged.
Docker/PostgreSQL not running; all previous gates remain open.
Next task: M2-07, tool registry and executor built-in.

## M2-07 — registry startup and executor tool built-in

Single host registry for approved Python metadata and callables; ToolDefinition in
core with ID/version, schemas, permissions, risk, timeout, retry_policy ed
executor. Schemas are generated and verified against Pydantic models
input/output: no custom JSON Schema interpreter or remote $ref fetch.Implement read-only builtin.text_stats and a trusted programmable executor,
with scope tools:execute + declared permissions + explicit grant of the ID.
The assistant selection, if present, must allow the tool. At this stage
side effect and approval not available imply deny, never simulated approval.
Model invocations and assistant.tools activation remain in the M4 tasks.
GET /v1/tools requests tools:read and reads bounded metadata from the private runtime;
no public API to install or run code. Real tool events in
hook metadata and log without parameters/results. No SQL migration planned.

Ruling: Validate using host Pydantic models and derived patterns, rather than one
new JSON Schema dependency not available in the environment. Cost: register a
tool requires Python templates extra=forbid; arbitrary patterns disconnected from models
they are not accepted. HTTP/MCP and full approval remain in the scheduled tasks.

### M2-07 — deployment complete, verify locally

- [x] RED observed: uai_core.tools missing from test_tool_registry.py collection.
- [x] ToolDefinition with all required metadata; host registry with unique IDs,
  patterns consistent with Pydantic input/output models extra=forbid, async handler and
  JSON snapshot detached. Maximum 64 tools and 8 KiB by definition.
- [x] Executor on the same registry as the factory catalog (app.state.tool_executor).
  tools:execute, permissions and exact grant needed; whitelist assistant when
  present. No implied wildcards or authority derived from template arguments.
- [x] Finite and strict JSON input/output, limits 128 KiB and context characters,
  applied even after normalization. Additional RED: A validator could expand
  the result beyond the limit; GREEN with verification of the normalized result.
- [x] Minimum timeout between tool and context, propagated deletion, only one attempt
  without retry. Real tool.requested/authorized/started/completed/failed events in
  hooks and logs metadata-only. Normalized handler errors without private details.
- [x] Write/destructive tools denied with approval_required before handler.
  Builtin text_stats read-only counts characters/words/lines without pattern or IO.
- [x] RED Go: /v1/tools does not exist (404). GREEN with tools:read, runtime reading
  authenticated, 5 seconds, no redirects, max 1 MiB and narrow descriptors.
  Scope tools:read for reader/operator/admin; tools:execute operator/admin only.
  Persisted credentials retain their original scopes; no automatic grants.
- [x] RED interop regression: Go's HTML escape inflated beyond valid metadata
  8 KiB. GREEN by measuring received UTF-8 descriptors before re-serialization.
- [x] Updated public/internal OpenAPI, metadata schema without callables/secrets,
  test scope/redirect/invalid responses/normalization/deletion and unique log.
- [x] E2E catalog and SDK invocation within runtimes linked to make e2e. The fixture
  SDK was run locally and produced tool sequence expected for success,
  grant denied and input invalid; it's not a Docker/PostgreSQL test.
- [x] Documentation tools.md/auth, backlog/plan, implementation-status and ADR 0006.
- [ ] Run make e2e with Docker/PostgreSQL available: real gate open.

### Final evidence M2-07

`make test`: 112 Python (20 tool_registry cases and new contract test) and 26 Go
with past race/vet. Build gateway, compileall core/runtime/E2E, shell and Compose
config core+override passed. Wheel rebuilt; import of ToolDefinition and call
text_stats from isolated directory without FastAPI/httpx passed. Nothing new
SQL dependency or migration. Internal OpenAPI compared to the updated snapshot.

Local review by author: Check grant/scope before handler, code
host distinguished by arguments, metadata snapshots, limits before/after validation,
error normalization, deletion and absence of retry. No independent reviewers:
Requested model not available, no used replacement. No local blocking
emerged. Current audit in log/hook; lasting effects, approval and tool call from
model remain M4, not simulated capabilities. HTTP/MCP remain in dedicated tasks.
Docker/PostgreSQL not running; previous gates still open.
Next task: M2-08, Plugin SDK, local manifests and skills.## M2-08 — starting SDK plugins and local skills

Separately installable, core-dependent SDK and packaging for compatibility
PEP 440. Trusted Python manifest with namespaces, versions, dependency graph,
capability, config JSON and connector declared; no implicit grant.
Plugins/registrar/lifecycle are SDK contracts; discovery and activation remain M2-09.
The HookSubscriber contract is consolidated into the core with re-export runtime,
so SDK and plugins do not import FastAPI or application packages.

Host approved root skill, regular and bounded UTF-8 files, relative reading with
file descriptor and O_NOFOLLOW on each component. Delimited JSON content e
characters < > escaped; no interpretation of frontmatter as permissions.
Ruling: POSIX safe local loader, without path-based fallback on non-platforms
of dir_fd/O_NOFOLLOW. Cost: Such platforms must provide an approved loader
alternative; Current Docker/Linux deployment is supported.

### M2-08 — deployment completed, local verification

- [x] RED observed: uai_plugin_sdk not installed when collecting the two new suites.
- [x] Separate SDK package with py.typed, PluginManifest/PluginDependency,
  Public Plugins/PluginRegistrar/PluginHealth and Skill/SkillLoader.
- [x] Compatibility and dependency specifier PEP 440 with packaging; dependency graph
  stable with graphlib. Rejected invalid, duplicate, version/capability/connector versions
  missing/incompatible dependencies and loops. Manifest max 32 KiB, max 64 plugins.
- [x] Capability/permissions are declarations, without grants or activations. Config
  and config_schema are bounded JSON metadata; the M2-09 manager must validate them e
  apply policy connectors, namespaces, and atomic registrations.
- [x] HookSubscriber moved to core and re-export runtime retained: SDK not
  import FastAPI/httpx/runtime. Plugin maintains detached snapshots and unknown health.
- [x] Skill loader from approved root and approved package directory: path
  relative, no traversal/symlink/FIFO/device/directory, UTF-8 and max 16 KiB. Reading
  descriptor-relative resistant to symlink swap and bounds on the actual read.
- [x] Skill frozen, JSON content delimited with < > & escaped, max 32000
  characters; frontmatter preserved as given, no prompt/authority changes.
- [x] Additional REDs observed: model_copy with NaN became null before
  revalidation; directory openings were losing FD. GREEN with snapshots from Python data
  and explicit ownership of descriptors, covered by regression tests.
- [x] Offline local editable installation, requirements/pyproject, README dev,
  Dockerfile and CI updated. packaging already present dev promoted to SDK runtime;
  setuptools 84 also declared in the dev requirements for the build/check targets.
- [x] make plugin-sdk-test/check/build available; make test collects the suites
  SDK. Fixture SDK/skill run locally and linked to make e2e in the container.
- [x] Backlog/plan, SDK documentation and ADR 0005 updated.
- [ ] Run make e2e with Docker/PostgreSQL available: real gate open.

### Final evidence M2-08

`make test`: 140 Python (28 new SDK/skill cases) and 26 Go with past race/vet.
make plugin-sdk-check/plugin-sdk-build passed; wheel SDK in packages/plugin-sdk/dist.
Wheel core and SDK extracted together in isolated directory: import from those wheels,
compatibility with installed core and skill loading passed without FastAPI,
httpx or runtime. Fixture run_plugin_sdk.py passed locally, not in Docker.
Compileall core/SDK/runtime/E2E, shell syntax and Compose config core+override
past. Existing OpenAPI/lifecycle contracts still matching snapshots;
no new public API or SQL migration. CI workflow updated, not executed
on GitHub. No package publishing or deployments done.Local review by the author: verified metadata without auto-grant, absence of
dynamic import from manifest, compatibility/graph, revalidated snapshots, FD cleanup,
swap resistance and delimited rendering. No independent reviewers:
Requested model not available, no used replacement. No local blocking
emerged. The loader requires POSIX; activation and config enforcement are reserved
to manager M2-09. These are explicit boundaries, with no trusted process sandbox.
Next task: M2-09. All previous Docker/PostgreSQL gates remain open.

## 2026-10-22 — M2-09, foundation manager (ongoing)

- Implemented PluginManager for host-approved trusted instances: no import,
  installation or grant from administrative input.
- Extended owner registers with membership clone; staging of contributions e
  publishing without await, previous snapshots preserved. Registration closed
  after register; namespace, capability, collisions and max 64 contributions checked.
- SDK resolution of versions/core/graph, required active dependencies and locking
  deactivation of plugins with active employees.
- Finished JSON configuration max 32 KiB, Pydantic template approved with extras
  prohibited, consistent manifest pattern when present. Health/activate/deactivate
  bounded to five seconds; log without configuration or exception text.
- Cleanup after failed activation; Contributions removed even if deactivate fails.
- RED observed: manager absent, health absent, registrar still writable later
  register. Final GREEN: make test, 149 Python and Go suites with race/vet passed.
  Nine manager cases cover staging, config, namespace/collisions, dependencies,
  cleanup failed, tool removal, snapshot membership, health and registrar closed.
- Local review by the author; no independent reviewer or replacement model.
  ADR 0005 documents host config model and snapshot selection limits.
- M2-09 remains open: discovery/build hello, wiring runtime, coordination run,
  Go API, persistence/restart/configure and E2E not implemented in this block.
  No distributed atomicity declared nor draining of resources of active runs.
  Docker/PostgreSQL gates unchanged and still to be run.

## 2026-10-22 — M2-09, runtime and example installed (in progress)

- Connected PluginManager to create_app: catalog/tool executor, validation
  directives and snapshots of each run share active contributions.
- Added authenticated private routes for catalog, activate/deactivate and health;
  Internal OpenAPI regenerated and verified. No install/import/reload endpoints.
- Package hello installable from build/CI/dev; static approval in from_env,
  inactive at boot, directive selectable only on affected assistants.
- Run/tool ​​maintain a lease until completion/error/exit; deactivate
  rejected as long as executions exist. New runs during mutation receive 503.
- RED observed: package hello absent, execution pinning absent, parameter
  approved_plugins absent. Integration then GREEN. The initial mock provider
  finish_reason=stop was missing: fix the fixture, not the provider contract.
- Full suite exhibited regression on subsequent host registrations
  factory: Fixed by composing each new snapshot from the current host logs and
  from active contributions. Existing snapshots remain separate. Pre-existing test
  RED→GREEN preserved; no weakening of the contract.
- First attempt at synchronous background cleanup crashed the ASGI test
  sandbox threadpool; replaced with asynchronous cleanup on the same event loop.
- Added HTTP tests for auth, isolate for assistant, remove and release after
  preflight failed; competitor streaming blocks deactivate, completion
  allows. Also verified disconnection before the first frame.
- Final evidence: make test, 154 Python and Go suites with race/vet passed. Wheel
  hello built in /tmp, extracted and imported with valid manifest. Compileall,
  bash -n and docker compose config with E2E overrides passed.
- Smoke runtime hello linked to tests/e2e/run.sh and mount Compose; NOT executed
  with Docker. Image build and PostgreSQL integration NOT verified. CI
  updated, not run on GitHub. Local review by the author, without agents
  replacements for the requested model.
- ADR 0005 and docs/plugins.md record the conservative choice: any run
  active blocks deactivation. Cost: the administrator is under constant burden
  must drain the runtime and try again. Dependency tracking not introduced
  implicit plugin resources.
- M2-09 remains open for Go public API/authorization, SQL migration,
  persistence/configure and reconciliation after restart, full public E2E.
  The current runtime loses activation on restart. No tasks marked complete.## 2026-10-22 — M2-09, public administration and reconciliation

- Implement GET /v1/plugins, PUT/DELETE /v1/plugins/{id}, GET health. Role
  explicit admin and scope plugins:read/plugins:write; no installation/import
  or hot reload from requests. Catalog without config values, bounded metadata,
  Strict runtime responses, prohibited redirects, and non-propagated private diagnostics.
- If-Match mandatory on global review, 428 absent and 412 stable. Config
  complete validated in runtime before the desired writing; API and contract
  public document the model 200 applied / 202 saved but pending.
- Migration 004: plugin_configuration singleton document and audit revisions,
  actors and IDs changed without config. Store reuses the administrative lock and
  double check credentials/role/scope before commit. HTTP out of transactions
  SQL. The audit JSON comparison preserves the numbers, without float64 conversion.
- Runtime reconciles in topological order, removes dependents before
  dependencies and restarts them if config changes. Obsolete revisions and different reuse
  of the same revision rejected; retry of the same idempotent configuration.
- Boot gateway and subsequent requests restore from the DB even after restart
  runtime. No polling/new workers. Removing the last setting continues to
  reconcile even with empty map: only the initial review can skip it.
- An activation failure without active contributions lets the core run
  independent; pending removals/configurations prevent new executions
  with stale status while existing leases drain. Failed cleanup remains
  visible without republishing removed contributions. General health remains core.
- RED observed for absent reconcile and missing Store methods; GREEN on API,
  simulated persistence, ETag, privileges, retry, simulated restart and dependencies.
  Additional RED→GREEN: Auto-deletion plugin propagated as deletion
  request; normalized default configs could exceed 32 KiB; mutation of
  dict in activate altered the tracking host and blocked new runs. Now isolate yourself
  self-cancellations, propagated real ones, unified budget validation and
  registered config snapshot separate from the callback snapshot.
- Public/internal OpenAPI updated and verified, README/auth/plugins/ADR 0005
  and task index updated. Document your choices: global review (conflicts
  even between separate plugins), retry on request (no restore until
  next request), a supported gateway and runtime process.
- Prepared check_plugin_admin.py in runner: configuration, race If-Match,
  two assistants with/without directive, SQL desired/audit, restart runtime without
  gateway, then restart gateway and remove. Private smoke preserved. These
  scenarios have NOT been run on Docker/PostgreSQL.

### Local evidence M2-09

make tests: **162 Python and 32 top-level Go tests**, race detectors and vets passed.
Native gateway build passed; compileall core/SDK/runtime/hello/E2E, bash -n e
Compose config core+override passed. The wheel hellos were already verified in
previous block and the package has not changed. Local review by the author of
auth boundaries, commit-before-apply, revisions, recovery, and isolation; no reviewers
independent, no replacement model for the requested model.

M2-09 implemented and verified locally; SQL migration, Docker image,
Real audit and restart yet to be tested with make e2e. Not declared completed
the M1/M2 gate nor the integration on PostgreSQL. Next task: M2-10.

## 2026-10-23 — M2-10, gate Extensibility and real Docker/PostgreSQL verification

- Performed real gate with Docker 29.8.2 and Compose v5.6.0. `make test` passes with
  165 Python tests and Go suites with race detector/vet. `make e2e` completes all
  scenarios and ends with exit 0: auth, versions, directives, built-in, tools, SDK,
  hello plugin, hooks, public administration, race If-Match, SQL audit, migrations 1–4 and restart
  separate runtime and gateway.
- RED→GREEN E2E infrastructure: Compose v5.6.0 published `UAI_PORT=0` as `:0`;
  Docker 29 does not publish container ports only on `internal` networks; `up --wait`
  started the gateway before PostgreSQL; `up --build` reused images
  stale. The runner now chooses a free port, the gateway has a network
  `frontend` not internal, dependencies start before the gateway and the build is
  explicit.
- RED→GREEN provider: with `MODEL_API_KEY` empty the adapter sent
  `Authorization: Bearer `, rejected by httpx/h11 with `provider_error`. The header
  it is now omitted; `tests/test_provider.py` covers absent and present key.
- RED→GREEN migration 004: `INSERT INTO schema_migrations(version)` was missing, so
  every restart of the gateway re-migrated (`relation already exists`) e
  `OpenStore` deadlocked closing the pool before rollback. The
  migration is idempotent and registers the version; rollback precedes closing.
  The runner's restart gateway is now green.
- RED→GREEN pipeline directives: Context comparison used JSON dumps with
  `frozenset` (scopes/capabilities), whose order is not stable. This caused
  Intermittent `directive_failed` after `with_messages` (e.g. hello directive).
  The comparison now uses Pydantic data; added a regression test that
  constructs a set with unstable JSON order. Repeated E2E executions passed.
- M2-10 Documentation: Created [runtime-lifecycle.md](runtime-lifecycle.md) with
  trust boundary, activation, reconciliation and run diagrams, invariants and
  criteria→test matrix. Updated [plugins.md](plugins.md),
  [plugin-sdk.md](plugin-sdk.md), TASKS, M2 plan and implementation-status.
- Limitations: GitHub pipeline not running on GitHub; local Docker/PostgreSQL tests.
  One gateway and one runtime per database remain valid, no replication
  distributed, no installation/import/hot reload via API.
- M2 closed. Next application task: M3-01 (knowledge base, versions and access).## 2026-10-23 — M3-01, knowledge base, versions and access

- Implemented `/v1/knowledge-bases` API (list/create/get/patch/delete) and
  `/v1/knowledge-bases/{id}/versions` (list/create) with scope
  `knowledge-bases:read/write`, ownership owner/admin, ETag on review e
  `If-Match` on patch/delete/version create. Someone else's resource returns 404.
- Migration 005: `knowledge_bases` and `knowledge_base_versions`, config JSON
  bounded 64 KiB, FK `ON DELETE CASCADE`, FK deferred `(id, active_version)`,
  unique partial indexes for a single `active` version and a single `reindexing`,
  audit of operations. Version 1 is active at creation; a new one
  version remains `reindexing` and does not change `active_version` until M3-09
  performs the atomic switch.
- `knowledge_base_ids` of the assistant admitted (max 64, unique UUIDs) and validated
  in the same transaction as the version with `FOR SHARE` lock on the KB. ID
  unknown or other owners produce 422 without entering the snapshot.
  Admin can bind any KB. The Python core accepts snapshot; the
  retrieval will use it from M3-10/M3-11. DELETE returns 409 if the version
  current of an assistant references the KB.
- RED→GREEN: HTTP test initially 404; then green CRUD/versioning/cross-owner.
  Fixed E2E test using admin for cross-owner case: admin is
  authorized; the test now uses two distinct operator credentials. The first run
  E2E also confirmed that the runtime accepts `knowledge_base_ids` in the
  snapshot and complete the run.
- Highlight: `make test` (167 Python, Go race/vet) and `make e2e` complete with
  `check_knowledge_bases.py` on real PostgreSQL, including `schema_migrations`
  1–5, versions, associations, deny cross-owner, delete guard, cascade, and restart.
  Documentation in [knowledge-bases.md](knowledge-bases.md); public contract
  updated and validated. Next task: M3-02 (local storage and S3-compatible).

## 2026-10-23 — M3-02, blob storage filesystem and optional S3

- Added `uai_core.storage` contract: `BlobStore` put/get/delete,
  `BlobNotFound`/`BlobStoreError`/`BlobStoreUnavailable`, `new_blob_key` and
  key validation. Keys are generated by the host; no URL/path arrives
  from the model or public requests.
- Filesystem adapter: root configurable with `UAI_STORAGE_DIR`, write
  temporary with `O_EXCL|O_NOFOLLOW`, `fsync` and `os.replace` (partial upload not
  visible), no final/parent symlinks outside root, idempotent delete and cleanup
  of temporary workers. Volume Compose `blob-data`, directory created with ownership
  of the runtime user and verified with a real container.
- Optional S3 adapter with lazy boto3 and secret/env (`UAI_S3_*`), prefix
  validated, errors sanitized and repr without credentials. Pinnate addiction in
  `requirements-s3.txt` is in dev; the base image does not include it.
- Fixture S3: Compose profile `s3` with LocalStack 3.8 (free port, volume
  dedicated) and target `make storage-s3`. Real roundtrip boto3 passes; the test
  S3 is skipped by default when the endpoint is not configured.
- RED→GREEN: storage module absent at first test; then 8 green storage tests.
  The first attempt `make storage-s3` did not reach LocalStack because the
  fixture was only on the internal network (Docker 29 does not publish ports on networks
  internal); added the network `frontend` as for the gateway.
- Evidence: `make test` 174 passed + 1 skip, Go race/vet; `make storage-s3` 8/8
  on LocalStack; `make e2e` complete. Documentation [storage.md](storage.md),
  public contract unchanged (no new route). Next task: M3-03
  (upload documents and metadata).

## 2026-10-23 — M3-03, upload documents, validation and jobs

- Added `/v1/documents` with multipart upload, list/get/delete, scope
  `documents:read/write`, ownership via KB and 20 MiB limit.
- Validation: declared MIME vs server-side sniff, allowlist TXT/Markdown/HTML/
  PDF/DOCX, server-side SHA-256 hash, filename metadata only. DOCX validated as
  ZIP (required entries, macros/encryption/traversal and expansion limits).
  Inconsistent MIME, archive hostile and oversize rejected.
- Migration 006: `documents` + `document_jobs`, dedup for KB, FK, indexes and jobs
  `queued` created atomically. Storage PUT before insert; blob cleanup
  on error/race; delete document + job + blob; KB with documents → 409.
- Runtime: internal endpoint `PUT/GET/DELETE /internal/v1/storage/{key}` with auth,
  body limit and adapter filesystem/S3 from `UAI_STORAGE_BACKEND`; OpenAPI snapshots
  regenerated interior. Gateway: tmpfs `/tmp` for multipart.
- Rate limiter made configurable with `UAI_RATE_LIMIT` (default 120) to avoid
  that the larger E2E suite is distorted by the installation-wide limit.
- RED→GREEN: document route 404, then green upload/validation/dedup. The first
  E2E exposed the rate limit (429) on the extended suite; raised only in the runner
  E2E. E2E test uses two principals, checks dedup per KB, valid PDF/DOCX,
  MIME/hostile archive, job queued, delete and KB guard.
- Evidence: `make test` 177 passed + 1 skip, Go race/vet; `make e2e` complete
  (document upload + job on PostgreSQL/real runtimes); `make storage-s3` 8/8.
  Documentation [documents.md](documents.md). Next task: M3-04.## 2026-10-23 — M3-04, parser and normalization

- Core contracts: `DocumentLoader`, `DocumentParser`, `DocumentProcessor`,
  `ParsedDocument`/`DocumentPage` with verifiable offsets, `BytesLoader` and
  protocol OCR/SQL/web/Git; stable `CorruptDocument` errors,
  `UnsupportedDocument`, `DocumentLimit`, `UnsupportedBackend`.
- Parser runtime: TXT/Markdown UTF-8 normalized; HTML with stdlib parser
  (script/style excluded, entities decoded, no fetch); PDF with pypdf and
  pages/offsets preserved; DOCX with defusedxml and ZIP limits, macro rejection,
  encryption and traversal. PDF without text declares `ocr_required`, OCR does not
  simulated.
- Limits: 20 MiB, 2,000,000 characters, 2,000 pages, 1,000 entries/32 MiB/64 MiB
  for DOCX. Deterministic TXT/MD/HTML/PDF/DOCX/corrupted fixes and testing
  five formats, negative cases and registry.
- Added and pinned runtime dependencies: pypdf 6.21.2 (BSD-3-Clause),
  defusedxml 0.7.1 (PSFL). Documentation [parsing.md](parsing.md), dependencies,
  ADR 0007, README, TASKS, M3 plan and status updated.
- Evidence: `make test` 184 passed + 1 skip; regenerable fixtures with
  `tests/fixtures/documents/generate_fixtures.py`. Next task: M3-05
  (chunking and provenance).

## 2026-10-23 — M3-05, chunking and provenance

- Added `uai_core.chunks` with `Chunker`/`Chunk`/`ChunkingError` and
  `chunk_document`; runtime wrapper `uai_runtime.rag.chunking`.
- Algorithm per page: no chunk crosses a boundary, offset in code points,
  configurable overlap, last fragment correct, empty chunk → no chunk.
- SHA-256 stable `Chunk.id` on document hash/version, page, index, offset,
  configuration and text; identical reingestion does not duplicate.
- Migration 007 `document_chunks` with FK cascade, hash/version, page/offset,
  normalized text, consistency check and indexes. Provenance before index;
  worker/upsert in M3-06.
- Test: 191 Python passed + 1 skip, property on lengths/sizes/overlap,
  Unicode, page boundaries, stable IDs and bad cases. `make e2e` applies 007 e
  check the table. Documentation [chunking.md](chunking.md), parsing,
  documents, README, ADR 0007, TASKS, M3 plan and status updated.
- Next task: M3-06 (durable workers and jobs).

## 2026-10-23 — M3-06, workers and durable jobs

- Added worker `apps/worker/uai_worker` with `JobStore`/`JobWorker`/`main`:
  claim `FOR UPDATE SKIP LOCKED`, lease, maximum retry, dead-letter and cancel.
  The worker reads blob/config KB, parse/chunk and inserts chunks with stable IDs
  `ON CONFLICT DO NOTHING`, completing the job in the same transaction; lease
  lost/cancel don't post.
- Migration 008: lease_owner/lease_until/dead_lettered_at and claim index.
  API `GET /v1/documents/{id}/job` and cancel with document scope and ownership.
- Compose/Docker: dedicated profile `worker` service, `blob-data` storage
  shared, variables attempts/lease/poll. Test worker with fake backend for
  success, permanent failure, transient storage, and cancel/lease.
- E2E: real worker on PostgreSQL; PDF/DOCX completed, deleted job remains
  deleted, job running with expired lease recovered, completed job requeued
  without duplicating chunks. The first run exposed an invalid PDF fixture for
  pypdf; replaced with the deterministic fixture M3-04.
- Evidence: `make test` 192 runtime + 5 workers + 1 skip, Go race/vet; `make e2e`
  complete. Documentation [jobs.md](jobs.md), parsing/documents/chunking,
  dependencies, ADR 0007, TASKS, M3 plan and status updated.
- Next task: M3-07 (embedding provider and Ollama).

## 2026-10-23 — S3 fixture migrated from LocalStack to RustFS

- Replaced test-only `s3` service: LocalStack 3.8 → RustFS (image
  pinnata for digest, local port, volume `rustfs-data`, healthcheck `/health`).
- Updated `make storage-s3` to start RustFS on free port, create the
  bucket and roundtrip boto3 with fixture credentials.
- Check: `make storage-s3` 8/8 with RustFS; no residual containers.
  Updated storage/dependencies documentation. LocalStack is no longer required.## 2026-10-23 — M3-07, embedding and Ollama

- `EmbeddingModel`/`EmbeddingProvider` contract with Ollama provider o
  OpenAI-compatible, size/version/batch, text/batch limits and
  `index_version` SHA-256 stable; change model/version/size → new
  index version.
- Ollama Adapter `/api/embed` (no key) and OpenAI-compatible `/embeddings`
  (Bearer optional, LiteLLM behind the same border), with number control
  vectors, dimension and finite values; transient retry only (timeout/429/5xx),
  timeout/redirect policy and errors sanitized.
- Added `OllamaProvider` native chat `/api/chat`, selectable with
  `MODEL_PROVIDER=ollama`; the OpenAI-compatible provider remains the default.
- Example config embedding and factory `embedding_provider_from_env`; test
  adapter, batch, size, retry, header, index sorting, factory, chat
  Ollama and skipped opt-in real test without endpoint.
- Evidence: `make test` 200 runtime + 5 workers + 2 skipped (real S3/Ollama
  absent), Go race/vet; real opt-in test with Ollama 0.6.8 + nomic-embed-text
  past (768 dimensions).
  Documentation [embeddings.md](embeddings.md), assistants-models, README,
  dependencies, ADR 0007, TASKS, M3 plan and status updated.
- Next task: M3-08 (Qdrant and mandatory filters).

## 2026-10-23 — M3-08, Qdrant and mandatory filters

- `VectorStore` contract with `VectorPoint`/`VectorHit`, deterministic collection
  for `index_version`, size/points/delete validation and KB filter
  mandatory. Empty filter → `missing_authorized_filter`; no wildcards.
- Qdrant REST Adapter: ensure collection with exact size, upsert with UUIDv5
  stable and provenance payload, server-side search `match.any` on KB
  authorized, delete/delete_collection idempotent, collection absent
  fail-closed (`index_not_ready`), errors sanitized.
- Qdrant 1.15.0 in Compose profile `rag`/`full`, dedicated volume, no ports
  published; target `make vector-store-qdrant` on free loopback port.
- Unit tests with MockTransport and real integration with two KB: results
  isolated, mandatory filter, repeatable delete, fail-closed absent collection.
- Evidence: `make test` 205 runtime + 5 worker + 3 skipped, Go race/vet;
  `make vector-store-qdrant` 6/6. Documentation [vector-store.md](vector-store.md),
  embeddings, README, dependencies, ADR 0007, TASKS, M3 plan and status updated.
- Next task: M3-09 (pipeline ingestion, reindex and export).

## 2026-10-23 — M3-09, ingestion, reindex and export

- Migration 009: embedding/collection/chunk_count/ready/lease in KB versions,
  states building/ready/superseded and queue `vector_cleanup_jobs`.
- API versions extended with embedding (or copy from active); export
  `/v1/knowledge-bases/{id}/export` with KB/versions/documents/chunk, without blobs
  keys or secrets and limits 2,000 chunks/8 MiB.
- Worker `ingestion.py`: IndexBuilder with new collection for index_version,
  parse/chunk/embed batch/Qdrant upsert, idempotent chunks, atomic switch
  superseded→active, lease/retry and cleanup collection on error. Cleanup
  vector after delete document on all collections.
- Qdrant/worker E2E: mock embedding `/api/embed` 8 dimensions, Qdrant 1.15.0,
  reindex PDF/DOCX, active_version 2, export, delete PDF and dot removal.
- Fixed in development: `IndexBuilder` didn't await on
  delete/ensure collection; fake store tests; compose dependency Qdrant profile;
  E2E order to not delete the PDF before the retry/crash test.
- Evidence: `make test` 206 runtime + 8 workers + 3 skipped, Go race/vet;
  `make e2e` 20 checks passed. Documentation [ingestion.md](ingestion.md),
  vector-store, documents, README, dependencies, ADR 0007, TASKS, M3 plan and
  updated statuses. Next task: M3-10 (retrieval and Haystack adapter).## 2026-10-23 — M3-10, composable retrieval

- Added `uai_core.retrieval`: `AccessFilter`, `IndexTarget`, `Retriever`,
  `RetrievedChunk`, `ContextAssembler`, `RetrievalResult`. Query flow
  normalized→embedding→search with KB filter→hit check→optional reranker→
  budget.
- Empty ACL, hits outside ACL, version/embedding mismatch, invalid queries and
  reranker adding/duplicating chunks fail closed. Deterministic ranking
  for score/chunk ID; character/chunk budget with skip, without truncation.
- Optional Haystack Adapter for injected object, without import into core;
  Validated KB/version and provenance filters. Factory `retriever_from_env` with
  `RETRIEVAL_*`; no default reranker.
- Test: 5 retrieval cases with fake embedding/vector store and Haystack; factory,
  ACL, version, budget, reranker, replaceable backend.
- Evidence: `make test` 211 runtime + 8 workers + 3 skipped, Go race/vet.
  Documentation [retrieval.md](retrieval.md), vector-store, ingestion, README,
  ADR 0007/0009, TASKS, M3 plan and status updated.
- Next task: M3-11 (RAG directive, citations and gates).

## 2026-10-23 — M3-11, RAG directive, citations and gates

- Added `builtin.rag` with targets sent from the gateway (`retrieval_targets`),
  retrieval for KB with ACL, untrusted context, budget and citation map.
  System prompt, assistant, authority, policy and history remain unchanged; built-in guards are not removable.
- `after_model` outputs only truly referenced citations; `response.completed`
  include `citations[]` with citation_id/chunk/KB/document/hash/version/page/
  offset. Public `Citation` contract and internal snapshot updated; gateway
  preserves the event and replay.
- Gateway `Start` resolves collection/index_version/embedding from active versions
  of the server KB and sends them to the runtime; missing targets/ACL/version
  they fail closed.
- Fixed: `RetrievalTargets` nil serialized as null (runtime 422/502);
  `index_version` not set in Go target; RAG recording duplicated on
  shared registry.
- E2E `check_rag.py`: KB+`builtin.rag` assistant, query, response with `[C1]`,
  quotes compared to export (chunk/document/version/page/offset),
  prompt/KB unchanged. Evidence: `make test` 216 runtime + 8 workers + 3 skipped,
  Go race/vet; `make e2e` 21 checks passed. Documentation [rag.md](rag.md).
- M3 closed. Next task: M4-01 (persistent run state and deletion).

## 2026-10-23 — M4-01, persistent run state and deletion

- Migration 010: statuses queued/waiting_approval/cancelled, updated_at and
  cancel_requested_at; Finish compare-and-set and durable erased transition.
- API `/v1/agent-runs` list/get/cancel owner/admin, scope agent-runs:read/write,
  ID and 409 validation on terminals.
- Runtime `RunStateRegistry` + internal cancel endpoint + cancel-aware wrapper:
  closes provider/tool and issues `agent.cancelled`; gateway cancels the request
  activate as a fallback, persist and replay the terminal.
- Fixed in gate: active flag not set by public cancel, cancel runtime
  404 treated as success (no local fallback), finalized missing after
  persist deleted, `RetrievalTargets` nil in run body.
- E2E: mock slow run, public cancel, `agent.cancelled`, DB status cancelled,
  second cancel 409 and identical replay.
- Evidence: `make test` 221 runtime + 8 workers + 3 skipped, Go race/vet;
  `make e2e` 22 checks passed. Documentation [agent-runs.md](agent-runs.md),
  auth, README, ADR, TASKS, M4 plan, progress and status updated.
- Next task: M4-02 (tool authorization cannot be bypassed).

## 2026-10-24 — M4-02, tool authorization cannot be bypassed

- `ToolPolicyDirective` is the only policy: intersects principal's grant, scope
  required by the definition, tools selected in the assistant version,
  registry membership and allowlist connector (`connector:<id>`). None
  wildcard; allowlist connector empty by default.
- The executor uses the policy for the first check and reevaluates it after
  validation of arguments, immediately before the effect. A revoked grant
  while waiting for approvals it does not start the handler. Policy errors e
  implementation fail closed with normalized codes.
- Removed duplicate checks from the executor; `PluginToolExecutor` e
  `create_app` accept policy, `TOOL_ALLOWED_CONNECTORS` configure
  the host allowlist. No config `configs/policies/*` until M4-03
  introduces real connectors and their loading.
- Escalation test: prompt, retrieved document, tool output and tool
  plugins do not extend authority; unknown/unselected tool never run;
  recheck before effect; the mandatory guard is not replaceable.
- The `assistant.tools` configuration gate remains active until M4-06; the tests
  of the policy build the future snapshot from the validated version without
  reopen the calling tool in the BasicAgent.
- Evidence: `make test-python` 229 runtime + 8 workers, 3 skipped (S3/Ollama
  real absent); `make test-go` race/vet. Documentation [tools.md](tools.md),
  [builtin-directives.md](builtin-directives.md), TASKS, M4 plan and status
  updated.
- Next task: M4-03 (HTTP executor and protected connector).## 2026-10-24 — M4-03, HTTP executor and connector protected

- Added `uai_runtime.tools.connectors` and `uai_runtime.tools.http`: connector
  administrative with URL base, GET/HEAD methods, exact paths, headers like
  `SecretRef(env=...)`, timeout, response limit `max_response_bytes`, retry
  `never` and explicitly permitted private CIDRs.
- `HTTPToolBinding` binds tool, connector, method and path. The registry requires
  exactly one permission `connector:<id>` for executor `http`/`mcp` and reject
  HTTP write/destructive up to M4-05; the gateway applies the same filter to the
  catalog and accept the MCP contract.
- SSRF: validate all DNS addresses, block loopback/link-local/
  multicast/reserved/unspecified and known metadata, private only on CIDR allowlist.
  The connection is pinned to the address validated with backend `httpcore`, the name
  original remains in URL/SNI; redirects, environmental proxies and Unix sockets disabled.
- Secrets resolved per request, hop-by-hop headers prohibited, absent/invalid values
  fail before connection; if the server reflects a secret in the response body is rejected. The body is streamed within the limit and the JSON is
  validated by the tool's schema output.
- Fixed executor: a `ToolExecutionError` raised by a non-HTTP handler
  it was more normalized as `executor_error`.
- `ToolDefinition.executor` allows `builtin`/`http`/`mcp`; API contracts and validation
  updated gateways. `httpcore==1.0.9` is declared direct dependency for the
  finned transport.
- Public registration/CRUD of connectors and consoles remain M5-08; in M4-03 i
  connector are configured by the host and registered in-process. MCP is contract only.
- Evidence: `make test` 255 runtime + 8 workers, 3 skipped (real S3/Ollama
  absent); Go race/vet. Documentation [http-tools.md](http-tools.md), tools,
  dependencies, TASKS, M4 plan and status updated.
- Next task: M4-04 (constrained human approvals).

## 2026-10-24 — M4-04, human approvals constrained

- Runtime `uai_runtime.approvals`: canonical JSON and SHA-256 digest of arguments,
  policy snapshot (principal/scopes/grant, assistant version, tool/version,
  permissions/risk/executor), maximum expiration of 24 hours and transitions
  pending→approved/rejected/expired/invalidated→consumed. Reuse, double decision,
  Binding changed and expiration fail with stable codes.
- Migration 011: `approvals` table with FK at run/principal, immutable digests,
  JSONB snapshot policy, status/expiration/decision/consumption and indexes; single index
  on equivalent pending approvals.
- API `/v1/approvals` list/get/approve/reject with dedicated scopes
  `approvals:read/write` (operator/admin, not reader). The decision uses lock and
  compare-and-set: only the first wins, an expired becomes `expired`, a run does not
  plus `waiting_approval` invalidates the approval. `approve` returns the run to
  `running`, `reject` to `failed`, with audit `approval.approved/rejected`.
- Full topics are not persisted, only the digest; policy snapshot
  bounded and without prompts/user text. Contract API and [approvals.md](approvals.md)
  updated.
- Evidence: `make test` 262 runtimes + 8 workers, 3 skipped (real S3/Ollama
  absent); Go race/vet; `make e2e` complete with migration 011, double
  concurrent approval, deadline, rejection, scope and resumption of run on
  Real PostgreSQL.
- Next task: M4-05 (idempotent executions and effects retry).

## 2026-10-24 — M4-05, idempotent executions and effects retry

- Migration 012 `tool_executions`: run/tool/version, digest arguments, approval,
  risk, idempotent key, attempt, result/error code, timestamp e
  unique constraint `(run_id,idempotency_key)`.
- Internal API `/internal/v1/tool-executions` (Bearer internal key, non-public):
  reserve/get/start/complete/fail/unknown/reconcile. Reservation consumes
  atomically a valid approval and checks run/tool/version/digest.
- States: completed replay without effect; failed read-only retry within
  limit; failed/unknown mutants never retried; lease stale over 60 seconds →
  `unknown`; reconcile explicit completed/failed. JSON result bounded 128 KiB.
- Runtime `DurableToolRunner`: stable idempotent key from run/tool_call/tool/
  version/digest/approval, retry read-only only on timeout/non-connector
  available, mutants → unknown, cancel → unknown/cancelled. Internal client
  `GatewayExecutionJournal` with timeout, no redirect and trust_env off.
- Runtime test with fake journal and internal client; test gateway with reserve,
  replay, retry, consummate approval, unknown, reconcile, internal auth e
  competition. Real E2E: reserve/replay/retry/unknown/reconcile on PostgreSQL.
- M4-06 will connect the model loop to this reservation; no execution
  public or exactly-once promise over external HTTP.
- Evidence: `make test` 270 runtime + 8 workers, 3 skipped (real S3/Ollama
  absent); Go race/vet; `make e2e` complete with 012 migration and tool execution.
  Documentation [tool-executions.md](tool-executions.md), TASKS, M4 plan and
  updated statuses.
- Next task: M4-06 (agent loop with tool calling).## 2026-10-24 — M4-06, agent loop with tool calling

- Provider: `ModelChunk`/`ToolCallDelta` with incremental accumulation of id, name and
  JSON fragments; OpenAI-compatible adapter sends `tools` and accepts
  `finish_reason=tool_calls`. Partial/malformed/unfinished JSON never comes
  executed.
- `ToolCallingAgent`: loop up to 4 generations and 8 tool calls, direct response or
  tool→result→new generation; results added as `tool` messages, never
  as system; unknown/unauthorized tools fail closed.
- Authorization: gateway sends `allowed_tool_ids` only with `tools:execute`;
  runtime intersects version assistant, grant, scope, register and connector
  policy. Only read-only builtin/http tools are offered at this stage.
- Capability `tool_calling` required; `MODEL_TOOL_CALLING=true` enables it
  factory. With `GATEWAY_URL` the tools go from `DurableToolRunner`/M4-05.
- BasicAgent remains text-only and rejects assistant.tools; AssistantConfig and gateway
  now accept validated tool selections (IDs/duplicates/limits).
- Test: direct response, multi-step, malformed JSON, unknown tool,
  untrusted result, missing capability, executor error and delta provider.
- Evidence: `make test` 278 runtimes + 8 workers, 3 skipped (real S3/Ollama
  absent); Go race/vet. Documentation [agent-loop.md](agent-loop.md), tools,
  updated builtin-directives, TASKS, M4 plan and status.
- Next task: M4-07 (budget, context window and structured output).

## 2026-10-24 — M4-07, budget, context window and structured output

- `ExecutionLimits` adds `max_steps` (4), `max_tool_calls` (8) and `max_tokens`
  (8192); 0 retains the default for assistants that persisted before M4-07.
- `RunBudget` applies steps, tool calls, tokens and context windows; the tool storm comes
  stopped before effect, infinite loop with `step_limit`, duration remains
  covered by the timeout. No retry providers after a delta.
- `UsageAccumulator` aggregates prompt/completion/total only if reported by
  providers; usage unknown ≠ zero, internal estimate `ceil(chars/4)` for budget only,
  cost calculated only with known rates. Context window estimated with system,
  messages, tool results, patterns and maximum output.
- `structured_output` is allowed with dedicated capability, JSON Draft schema
  2020-12 bounded to 16 KiB validated at creation and on the final text; scheme or
  non-compliant outputs fail. `jsonschema==4.26.0` added to core dependencies.
- Extended gateway/assistant limits with compatibility for legacy values; APIs
  contract and internal snapshot regenerated. `MODEL_STRUCTURED_OUTPUT` configures the
  capability in factory.
- Test: usage unknown/zero/costs, step/tool/token/context, tool storm, duration,
  tool failed without retry, invalid schema rejected, native response_format request, structured output valid/invalid/capability missing
  and absence of retry providers after delta.
- Evidence: `make test` 288 runtime + 8 workers, 3 skipped (real S3/Ollama
  absent); Go race/vet. Documentation [budgets.md](budgets.md), tools, TASKS,
  M4 plan and status updated.
- Next task: M4-08 (audit of sensitive operations).

## 2026-10-24 — M4-08, audit of sensitive operations

- Migration 013: `audit_events` extended with target type, run/correlation/digest,
  outcome, details redacted and `retention_class`; `agent_runs.correlation_id`
  persisted and indexed. Existing migrations remain compatible.
- Transactional audit for authorized runs, assistant configuration, credentials,
  approvals (approve/reject/expired/invalidated) and all tool transitions
  (reserve/start/complete/fail/unknown/retry/reconcile). An audit error cancels
  the transaction and blocks the effect; run/approval are rebuildable from
  run, correlation, digest, tool/version and outcome.
- Recursive centralized editing in Go and Python: header, authorization,
  cookie, token, password, secret, API key, key digest, prompt, messages,
  arguments, results and bodies are not persisted; details unknown not
  are serialized. Reading `/v1/audit-events` requires `audit:read`
  (admin only), supports run/action/target/limit filters and redrafts again.
- `AuditLog` runtime logs authorized binding before effect; a sink
  fault produces `audit_unavailable` without invoking the executor. Retry/unknown
  those of M4-05 remain.
- Retention: `retention_class='security'` and run FK `ON DELETE SET NULL`; the
  duration/minimization policy remains M6-01. Contract API and docs updated.
- Test: recursive redaction and log, scope/filters/reading, pre-effect block, E2E with
  SQL assertions about bindings, tool transitions, and the absence of secrets.
- Evidence: `make test` 292 runtimes + 8 workers, 3 skipped (real S3/Ollama
  absent); Go race/vet; `make e2e` exit 0.
- Next task: M4-09 (HTTP isolated plugins).## 2026-10-24 — M4-09, HTTP isolated plugins

- Manifest SDK extended with `runtime: isolated_http`; the approved manifest remains
  authoritative. `IsolatedHTTPPlugin` valid remote manifest, tool catalog, schema
  JSON Draft 2020-12, timeouts, namespaces and connectors; does not matter remote code.
- Versioned HTTP protocol (`X-UAI-Plugin-Protocol: 1`) with Bearer token,
  `/v1/health`, `/v1/manifest`, `/v1/tools`, `/v1/activate`, `/v1/deactivate`,
  `/v1/tools/{id}/execute`. Bounded, redirect/proxy off, timeout and crash responses
  mapped to tool errors; an error does not bring down the runtime.
- Isolated tools registered as `isolated`, read-only, with permissions
  `tools:execute` + `connector:<id>`; the normal `ToolPolicyDirective` continues
  to enforce grant, scope, assistant selection and allowlist connector.
- `PluginManager` runs `prepare()` bounded before `register`; deactivation
  always closes the remote client. Gateway accepts manifest `isolated_http` and the
  `ToolDefinition.executor` contract includes `isolated`.
- Example in `plugins/examples/isolated-http`, non-root/read-only/ image
  cap-drop on backend network; compose E2E starts the container. Test units:
  manifest mismatch, auth header, catalog, execution, timeout/crash, scheme
  invalid, connector denied and removal.
- Evidence: `make test` 299 runtime + 8 workers, 3 skipped; Go race/vet;
  `make e2e` exit 0 with isolated check container.
- Next task: M4-10 (Gate Agents with mock real HTTP tool).

## 2026-10-24 — M4-10, gate Agents with mock real HTTP tool

- `mock_provider` issues OpenAI-compatible tool calls; `mock_tool.py` exposes
  Real read, write with effect count and stats. The E2E runtime registers a
  HTTP connector `mocktool` and the `mocktool.read` tool.
- `check_agents.py`: read-only through gateway/journal; tool not selected
  (`mocktool.write`) does not reach the server; two tool calls with
  `max_tool_calls=1` are stopped before the effects; audit and terminal SSE
  verified.
- `run_mutating_tool.py`: Real HTTP POST with approval already approved,
  Exact digest/tool/run, atomic consumption, replay without second effect e
  I check `tool_executions`/`approval`/audit via SQL.
- Fixed effective limits for `max_steps`/`max_tool_calls`/`max_tokens` between
  assistant and factory; connector permission is no longer required as del scope
  principal (the host allowlist remains) to make HTTP tools usable.
- Cancellation and resuming remain covered by `check_agent_runs.py` and
  `check_approvals.py`; the complete gate is `make e2e`.
- Evidence: `make test` 299 runtime + 8 workers, 3 skipped; Go race/vet;
  `make e2e` exit 0 with agent/mutation/isolated/audit.
- Milestone 4 completed. Next task: M5-01 (TypeScript SDK from contract).

## 2026-10-25 — M5-01, TypeScript SDK from contract

- New package `packages/sdk-typescript`: client typed for all 41
  Public API operations, with resources for assistants, conversations,
  credentials, templates, tools, plugins, knowledge base, documents, run,
  approvals and audits.
- `src/generated.ts` is generated from `packages/api-contract/public.openapi.json`;
  `src/operations.ts` is checked against the same contract (method, path,
  `Idempotency-Key` and `If-Match` required). No runtime dependencies.
- SSE: Incremental decoder with broken UTF-8, split frames, CRLF and `data:`
  multiple; `sendMessage` requires an explicit idempotency key, distinguishes
  `response.completed` from `agent.failed`, `agent.cancelled` and incomplete EOF.
  `AbortSignal` aborts the request and requests the run be canceled.
- Normalized errors (`APIError`, `ValidationError`, `AbortError`,
  `TimeoutError`, `NetworkError`, `StreamIncompleteError`,
  `AgentFailedError`, `AgentCancelledError`); upload multipart documents.
- Integration: `make test-typescript` target, included in `make test`; CI with
  Node 24 and `npm ci`; README of the package with usage, streaming and security.
- Evidence: `make test-typescript` exit 0 (17 test, contract check, typecheck,
  build); `npm run build` produces `dist/`.
- Next task: M5-02 (PHP SDK and Laravel integration) or M5-03 (Go SDK).## 2026-10-25 — M5-03, SDK Go from contract

- New package `packages/sdk-go` (`github.com/universal-ai-kit/sdk-go`) without
  external dependencies: client for all public operations, `context.Context`,
  typed errors and helper resources, conversations, credentials, templates,
  tools, plugins, knowledge base, documents, runs, approvals and audits.
- Synchronous SSE with reusable `SSEDecoder`: split frames, broken UTF-8,
  CRLF, comments and multiple `data:`; `Next` distinguishes `response.completed`,
  `agent.failed`, `agent.cancelled` and incomplete EOF.
- `SendMessage` requires explicit idempotency key; Explicit `If-Match` for mutations. Abort/timeout of the context interrupts the reading and requests the
  canceling the run with an independent context.
- `TestOperationsMatchPublicContract` compares the `Operations` map with
  `packages/api-contract/public.openapi.json`; parsers and errors covered by tests.
- Integration: `make test-go-sdk` target, included in `make test`.
- Evidence: `make test-go-sdk` exit 0 (`go test -race ./...`, `go vet ./...`).
- Next task: M5-02 (PHP and Laravel SDK) or M5-04 (widget token/CORS).

## 2026-10-25 — M5-02, PHP SDK and Laravel integration

- New package `packages/sdk-php` (PHP 8.2+, cURL + HTTP streams): client
  server-side for all public operations, incremental `SseDecoder` and
  `MessageStream` iterable only once.
- SSE: split frames, broken UTF-8, CRLF, comments and multiple `data:`;
  `response.completed` happened, `agent.failed`/`agent.cancelled` are
  terminals with typed exception, EOF without terminal is
  `StreamIncompleteException`.
- Idempotency key required for `streamMessage`; Explicit `If-Match` for mutations; cURL/stream timeout mapped to `TimeoutException`, HTTP errors a
  `ApiException` with status/code/body.
- Upload multipart documents; `Operations::ALL` checked against the OpenAPI
  public from `ContractTest`.
- Laravel: service provider auto-discovered, config `UAI_BASE_URL`/`UAI_API_KEY`/
  `UAI_TIMEOUT_MS`, example route with server-side SSE; the key does not reach the
  browser. Help in `docs/laravel.md` and example in `examples/laravel/`.
- Integration: `make test-php` target, included in `make test`; CI with PHP 8.3 e
  `composer install`.
- Evidence: `make test-php` exit 0 (13 tests, 198 assertions) with mock gateway
  local and Laravel provider testing.
- Next task: M5-04 (token widget and CORS) or M5-05 (Web Component).

## 2026-10-25 — M5-04, widget tokens and CORS

- Temporary browser tokens `uai_widget_…` with SHA-256 in database, tied to
  assistant, conversation, subject, origin and expiry; `widget` role with soli
  `messages:read`/`messages:write`. Mint/revocation require
  `widget-tokens:write` (operator/admin) and are audited.
- `POST /v1/widget/tokens` valid origin in `UAI_WIDGET_ORIGINS`, TTL 60s–24h,
  conversation/assistant ownership; `DELETE /v1/widget/tokens/{id}` revoke
  immediately. The token is returned only once.
- Auth: dedicated prefix, `WidgetBinding` in principal, control in middleware
  and in the store (`Messages`/`Start`) on conversation and assistant; no access
  to credentials, assistants, runs, plugins or configuration.
- Explicit CORS only on message routes: preflight `OPTIONS` 204 for origins
  in allowlist, `403 origin_forbidden` otherwise; actual request with
  `Origin` bound to token.
- Dedicated rate limit per token (`UAI_WIDGET_RATE_LIMIT`, default 60/min), separate
  from the global limit; migrate `014_widget_tokens.sql`; docs `widgets.md`.
- Updated public OpenAPI with mint/revocation and schemas; maps operations of the three
  aligned SDKs; `make test-go` race/vet, `make test-typescript`,
  `make test-go-sdk`, `make test-php` all exit 0.
- Next task: M5-05 (Web Component chatbot) or M5-06 (console).## 2026-10-25 — M5-05, Web Component chatbot

- New package `packages/chat-widget`: custom element `<uai-chat>` with shadow
  DOM, configuration via attributes or `setConfig`, injectable SDK backend for i
  test, `onEvent`/`onCitation`/`onError`, and `uai:*` DOM events.
- Markdown rendered by building DOM and `textContent` nodes: no HTML del
  model is interpreted; link only `http`/`https`/`mailto`, with
  `rel=noopener noreferrer`; quotes authorized by the `completed` payload,
  deduplicated and opened only via callback.
- SSE: delta accumulation, deduplication for `event_id`, completed distinction,
  failed, canceled and incomplete EOF; cancel via button/Escape with
  `AbortSignal` (which also cancels the gateway side run).
- Accessibility: `role=log`, `role=status`, `aria-live`, label textarea, focus
  management, Enter/Shift+Enter/Escape keyboard and responsive layout; theme
  light/dark and CSS variables `--uai-*`.
- Demo without forks: vanilla with import map, React with ref/`setConfig`, Svelte with
  `bind:this`; Documented mint token backend endpoint.
- Integration: `make test-widget` target, included in `make test`; CI with
  `npm ci` of the widget. Evidence: `make test-widget` exit 0 (8 test, typecheck,
  build).
- Next task: M5-06 (access console/assistants/templates).

## 2026-10-25 — M5-06, access console/assistants/templates

- New SvelteKit app `apps/console` with adapter Node: login via API key
  validated with the new `GET /v1/me`, opaque session in server-side memory,
  HttpOnly/SameSite=Lax cookie, 8h expiration, logout and security header.
- The key is never returned to the browser: SvelteKit load/actions use the
  client SDK server-side only; `GET /v1/me` exposes actual role and scope
  without credential material.
- UI: dashboard, list/creation of assistants, detail with versions, system
  prompt, template, and directives; read-only templates. Saving creates a
  new version and use `If-Match`. Read-only reader role; errors/empty/
  managed loading; no workflow editor.
- OpenAPI and SDK updated with `me`; TypeScript/Go/PHP aligned contracts.
- Test: `make test-console` (svelte-check 0 errors, 2 test sessions, build) and
  `make test-console-browser` with Playwright/Chromium: admin creates and versions a
  assistant without exposing the key, reader does not see the form, widget token
  refused. Browser tests were run in Playwright containers for
  system dependencies missing on the host.
- Integration: `deploy/docker/console.Dockerfile`, `console` service in
  `compose.yaml`, `.env.example` with `CONSOLE_*` and `ORIGIN`.
- Next task: M5-07 (KB console and documents).

## 2026-10-25 — M5-01…M5-06 integration check

- Updated public OpenAPI with `GET /v1/me`, mint/revoke widgets and schemas
  `PrincipalInfo`/`WidgetToken*`; TypeScript/Go/PHP SDK and aligned contract tests.
- Verified `014_widget_tokens.sql` migration: `make e2e` exit 0,
  including gateway restart and Agents/plugin/RAG suite.
- Local highlights: `make test-go` (race/vet), `make test-typescript`,
  `make test-go-sdk`, `make test-php`, `make test-widget`, `make test-console`;
  runtime 299 passed/3 skipped and worker 8 passed with dedicated venv.
- Browser console tests performed with Playwright/Chromium: 3 passed (admin
  create/release without exposing the key, reader read only, widget rejected).
- M5-07 (KB/documents), M5-08 (tools/plugins/approvals), M5-09 remain
  (conversations/run/playground) and M5-10 (integrations gate).

## 2026-10-25 — M5-07, KB console and documents

- Console: KB list/creation with chunk size/overlap, detail with review,
  versions, reindexing and associations to assistants (new version
  assistant with If-Match).
- Multipart upload with explicit limits (20 MiB; TXT/MD/HTML/PDF/DOCX), status
  ingestion and job, polling/refresh without duplicating the job, cancellation and
  confirmed deletion of document/KB. Downloadable JSON export.
- Authorized source: document route filtered by KB and document, chunk from
  export with page/offset, highlighting via `?chunk=` for future links to
  quotes. Errors/empty/loading and read-only reader role.
- Extended mock gateway with public/reserved KB, documents, progressive job,
  export/chunk and associations; browser test Playwright 5 passed (KB admin,
  upload→job→source, filtered reader, M5-06 console).
- `BODY_SIZE_LIMIT=24M` for SvelteKit/adapter-node, needed to upload up to
  20 MiB over multipart overhead; updated compose and docs.
- Evidence: `make test-console` exit 0 (svelte-check 0/0, 2 units, build);
  Playwright 5/5 in Chromium container; `make test` and `make e2e` remain green.
- Next task: M5-08 (tools, plugins and approvals).## 2026-10-25 — M5-08, console tools/plugins/approvals

- Tool: read-only catalog with executor, connectors, risk and input schema;
  no upload/install or arbitrary URL from the UI.
- Plugin: installed catalog, status/health, desired, validated JSON configuration
  and activation/deactivation with If-Match; configuration removal. None
  loading archives or manifests.
- Approvals: list and detail with tool/version/run, risk, connector
  recipient, topic/policy digest, expiration, and immutable snapshot policy.
  Approve/reject require confirmation and `approvals:write`; the arguments are not
  modifiable because they are not persisted. Approvals that have expired or have already been decided
  they show no action.
- Mock gateway extended with tools, plugins and approval pending/expired; browser tests
  Playwright 8/8 (including inactive→active plugins, risk/connector visible,
  approval approved, expired and token reader without scope).
- Highlight: `make test-console` exit 0 (svelte-check 0/0, 2 units, build).
- Next task: M5-09 (conversations, runs and playgrounds with SSE/quotes).

## 2026-10-25 — M5-09, conversations/run/playground console

- Run list/detail with statuses queued/running/waiting_approval/completed/failed/
  cancelled, usage in the playground, related approvals and audit already drawn up.
- Conversation history with completed messages and connected runs; link to
  playground and run.
- Playground with server-side SSE proxy (the key remains in the console process),
  deduplication for `event_id`, completed/failed/cancelled/EOF distinction
  incomplete, cancel via AbortSignal, retry/replay with same idempotency key,
  usage and citations with links to the authorized source.
- Security fix: CSP SvelteKit in hash mode (inline bootstrap script
  allowed with hashes, no `unsafe-inline` for script) instead of header
  manual that blocked hydration.
- Extended gateway mockup with runs, conversations, redacted audit, duplicate SSE/
  stopped/replay/cancel and quotes.
- Evidence: `make test-console` exit 0 (svelte-check 0/0, 2 units, build);
  Playwright 12/12 (console, KB, tools/plugins/approvals, run/playground).
- Next task: M5-10 (gate integrations and SDK compatibility).

## 2026-10-25 — M5-10, gate integrations and closure of M5

- Added shared array `tests/contracts/` + `check_contracts.py`:
  TypeScript, Go and PHP expose exactly **44 operations** of the OpenAPI
  public, including `Idempotency-Key`/`If-Match`. Target `make test-contracts`,
  included in `make test`.
- `tests/e2e/check_integrations.py` checks on real gateway: mint token
  widget, conversation/assistant binding, CORS preflight allowed/denied,
  bound origin, credential/mint lock with widget token, full SSE,
  persistent history and immediate revocation. Added to `make e2e`; check
  also migration 014 and `widget_tokens` table.
- Documentation [integrations.md](integrations.md): SDK matrix, SSE/terminals,
  Laravel, widgets, section 16 coverage and security boundaries. Registration
  of HTTP tools remains deployment-owned (connector/allowlist), consistent with the
  prohibition of arbitrary installation via API.
- Pipeline: `make build-packages` target (TS/Go/PHP SDK, widgets, console) and
  `make test-contracts`; Updated CI. Browser gate with CSP hash, header of
  security and ax (no serious/critical violations).
- Evidence: `make test` exit 0; `make e2e` exit 0 (integrations/widget tokens e
  all suites M1–M4); Playwright **13/13** (accessibility, roles, KB,
  extensions, run/playground/SSE); `make build-packages` exit 0.
- **Milestone 5 completed.** Next task: M6-01 (retention, cancellation and
  privacy).

## 2026-10-25 — M6-01, retention, cancellation and privacy

- Added [data-policy.md](data-policy.md): conversation/working memory classes,
  documents/chunks/vectors, jobs, approval and audit, default retention disabled,
  semantic memory disabled, tombstone, expiry backup and restore limits.
- Migration `015_retention.sql`: conversation-insensitive tombstones,
  document and knowledge base + principal `system-retention`.
- `DELETE /v1/conversations/{id}` allowed and with ownership, run blocking
  active, cascades on messages/runs/approvals and `conversation.deleted` audits.
  Updated TypeScript/Go/PHP SDKs; public contract now 45 operations.
- Internal retention `POST /internal/v1/retention/run` with advisory lock,
  `UAI_RETENTION_*_DAYS` configuration (0 = disabled), idempotent counts for
  conversations, approvals, audits and cleanup jobs. Delete document/KB now
  they write tombstone; the vector cleanup remains in the existing worker.
- `tests/e2e/check_deletion.py` + seed E2E check delete conversation,
  tombstone/audit, absence of runs/messages, conversation retention,
  approvals, audits and cleanup jobs, double idempotent execution.
- Evidence: `make e2e` exit 0 (deletion/tombstone/retention + all suites
  M1–M5); `make test` exit 0; contract matrix 45 ops for the three SDKs.
- Next task: M6-02 (verified backup and restore).## 2026-10-26 — M6-02, backup and restore verified

- `deploy/backup.sh`: custom PostgreSQL dump, filesystem blob archive, config
  non-secret, manifest with RPO scheme/checksum/times, pause services and
  reboot; excluding `.env`, secrets and Qdrant (rebuildable).
- `deploy/restore.sh`: check checksum/format/schema before touching it
  status, explicit target reset, DB/blob restore, RTO report, optional boot.
  Newer code backup scheme is rejected without overwrite.
- Vector reconstruction: fixed reindex with the same embedding
  (release of the previous collection) and the procedure documented; sources
  deleted remain excluded because the reindex only reads existing documents.
- `docs/backup-restore.md`: procedure, separate secrets, RPO/RTO, expiry backup
  and reindex; updated data policy.
- `tests/e2e/check_restore.py` + `make e2e-restore`: source stack, seed with
  ownership/history/provenance, backup, destruction, isolated destination stack,
  restore, query, replay with idempotency key, empty Qdrant, reindex and RAG query,
  incompatible restore rejected without data loss.
- Evidence: `make e2e-restore` exit 0; `make e2e` exit 0; `make test` exit 0;
  contract matrix 45 ops.
- Next task: M6-03 (OpenTelemetry and observability).

## 2026-10-26 — M6-03, OpenTelemetry and observability

- Optional fail-open telemetry in Go gateway, Python runtime, and worker:
  OTLP/HTTP endpoint via `UAI_OTEL_ENDPOINT`; without endpoint tracer/meter no-op.
- Trace W3C `traceparent` gateway→runtime, HTTP span, `runtime.run`,
  `provider.stream`, `tool.execute`, `retrieval.query`, `ingestion.document`;
  `X-Trace-ID` returned on SSE responses and streams. Redacted attributes:
  no prompts, messages, arguments, headers or secrets; normalized routes/IDs.
- Metrics `uai.requests`, `uai.request.duration`, `uai.events`, `uai.tokens`,
  `uai.errors`; Input/output tokens per model, distinct errors/timeouts/cancels
  for code/event_type. JSON gateway log `slog` with trace/run/correlation ID.
- Optional collector in `deploy/observability/` (profile `observability`) with
  config OTLP HTTP, batch, memory limiter and file/debug exporter; docs in
  [observability.md](observability.md).
- Test: Go in-memory span/exporter and propagation; Python span in-memory e
  editorial staff; `tests/e2e/check_observability.py` with collector unreachable
  verify fail-open and that `X-Trace-ID` passes through gateway→runtime.
- Highlight: `make test` 302 runtime/8 worker and Go race/vet; `make e2e` exit 0
  (observability included); `make e2e-restore` exit 0; contract matrix 45 ops.
- Next task: M6-04 (secrets, rate limit and operational egress).

## Update M6-04 — secrets, rate limits and operational egress

- Secrets: `_FILE` variables or files (absolute path, single source, UTF-8,
  maximum 64 KiB, one final newline) in gateway, runtime and worker; gateway reads
  also `DATABASE_URL_FILE`. `SecretRef(file=...)` in connectors is read back to
  every request, so file rotation does not require restart.
- Rate limit: 60 s fixed window limiter with bounded storage (10,000 keys,
  sweep and deny fail-closed at full capacity) for installation, principal and token
  widgets. `UAI_RATE_LIMIT_PER_PRINCIPAL` new; Widget budgets remain separate.
- Egress: `UAI_EGRESS_ALLOW=host:port` limits chat providers, embeddings and plugins
  isolated; empty value denies all, absent disables checking for
  compatibility. `HTTPToolExecutor(egress=...)` applies the same allowlist ai
  connector before DNS/connection. Compose connects runtime and worker to
  `model-egress`; only the gateway, console, and rustfs ports remain on loopback.
  Policy uses `UAI_EGRESS_ALLOW` instead of a `configs/policies/*` file: avoid
  a second configuration owner not read by processes.
- TLS/CORS: `deploy/reverse-proxy/nginx.conf.example` with TLS 1.2/1.3, HSTS,
  SSE buffering disabled and no duplicate CORS. The static scan
  `tests/e2e/check_security_config.py` checks ports, networks, literal secrets,
  hardening containers, egress policy and `key_digest` scheme.
- Documentation: [security-operations.md](security-operations.md); updated
  auth, http-tools, README, `.env.example` and Compose.
- Evidence: runtime 341 passed + 3 skipped (real S3/Ollama absent), worker 8
  past; Go `test -race`/vet/build; contract matrix 45 ops; `make test-security`
  ok; `make e2e` exit 0. Added `opentelemetry-sdk` to dev dependencies for
  make the existing telemetry test executable.
- Limits: limiter and rotation of boot secrets are per-instance;
  Redis/distributed not enabled and gateway replicas not supported without it
  lease/recovery. `UAI_EGRESS_ALLOW` must be set in production (the default
  Compose only covers local Ollama). Next task: M6-05.## Update M6-05 — security regression suite

- `tests/security/matrix.json` declares 15 trust boundaries: credentials, scopes,
  ownership, widget, runtime internal auth, prompt injection/retrieval,
  SSRF/DNS/redirect, upload/parser/traversal, XSS, plugin, approval/replay,
  editorial staff, secrets, rate limit/egress and KB isolation.
- Each boundary requires at least one deny and one allow case. `check_matrix.py`
  verify that the 73 referenced tests still exist and that the 15 E2E scripts
  are scheduled by `run.sh` (directly or via mount runtime), then them
  runs (`--run`) on Go, Python and chat-widget.
- No duplication of suites: the matrix is a coverage contract on the
  existing tests and new regressions must update both `required` and the
  boundary. Documentation: `tests/security/README.md`.
- Evidence: `make test-security` exit 0; 15 boundaries, 73 references, 8 tests
  widgets; config scan ok. Core suite unchanged (runtime 341 + 3 skipped, worker
  8, Go race/vet, contract 45 ops); E2E already green. Next task: M6-06.

## 2026-10-26 — M6-06, performance, capacity and recovery

- `tests/performance/run.py` measures chat/SSE, ingestion and retrieval with
  provider/embedding fixture, 12 chat requests and 6 RAGs at concurrency 4,
  slow provider/container CPU/RAM clearing and sampling. The
  baseline is versioned in `tests/performance/baseline.json` and validated by
  `make test-capacity`; `UAI_PERF_COMPARE` enables explicit comparison.
- `docs/capacity.md` documents workload, measured baseline, limits already present
  (rate limit, runtime `--limit-concurrency 32`, SSE 64k/2MB/4096 events,
  deadline 15 s, lease worker 300 s, retry/dead-letter) and
  sizing. No new threshold invented: the defaults remain the same
  existing.
- `apps/gateway/backpressure_test.go` checks for a slow client
  aborted by SSE write deadline instead of blocking the handler; the gateway
  continues to read/write the stream synchronously, without buffering
  unlimited.
- `tests/e2e/check_recovery.py`, run by `make e2e`, really kills gateway
  and worker: the interrupted run is marked `failed` with event
  `gateway_restarted` and same `correlation_id` (idempotent replay), the job
  worker with expired lease is resumed without duplicating chunk; a new one
  key on the same conversation works.
- Fixed recovery gateway to preserve the run's `correlation_id`
  in the error event, instead of generating a new one.
- Highlights: `make e2e` exit 0 with recovery and performance; baseline 8 documents,
  12 chats, 6 retrievals, 2 slow providers; `make test` (included
  green `test-capacity`) and `make test-security`. Next task: M6-07
  (dependencies, licenses and release packaging).

## 2026-10-26 — M6-07, dependencies, licenses and release packaging

- Added `VERSION` (0.1.0) as SemVer source; `tests/release/check_release.py`
  check versions in manifests and Compose tags, pin `==` Python, lockfile
  npm/Go/Composer and no floating base images.
- `scripts/release.py` prepares a non-publishing bundle: SBOM CycloneDX 1.5 and
  `THIRD_PARTY_NOTICES.md` (329 components from lockfiles), npm pack/wheel/
  Composer archive/Go source, OCI images with version tags and labels,
  `images.json`, source archive, `manifest.json` and `SHA256SUMS`.
- Added `.github/workflows/release.yaml` pipeline: contract diff against the
  previous tag, Syft for SBOM, Grype high/critical with fix, secret scan,
  attestation of origin and artifact upload. No `npm publish`,
  `composer publish` or `docker push`.
- `tests/release/contract_diff.py` + 8 unit tests block path/operations
  removed, required parameters added, properties removed, type changes,
  restricted enums and mandatory request fields.
- `tests/release/check_licenses.py` applies an SPDX allowlist to the SBOM;
  `check_release.py` checks artifact checksums, presence of packages and
  images, and absence of secret/`.env`/private keys. Added `.gitattributes`
  to exclude `vendor` from the PHP archive and label OCI to Dockerfiles.
- Evidence: `make test-release` exit 0 (8 tests); `make release-dry-run` exit 0
  with 5 images, 7 packages, 329 SBOM components and green artifact check;
  green `composer validate` and version checks. Next task: M6-08.## 2026-10-26 — M6-08, upgrade, rollback and two instances

- Added [deployment.md](deployment.md) and [upgrades.md](upgrades.md):
  clean install, core/local-ai/full profiles, template prerequisites,
  graceful shutdown, upgrade order, pre-upgrade backup, application rollback
  vs destructive restore, single-gateway limits.
- `compose.yaml`: gateway expects PostgreSQL and sane runtimes; the worker is in the
  `full` profile. This eliminates the startup failure observed with services
  started at the same time.
- `tests/e2e/check_upgrade.py`: stack schema 14→15, data/replay preserved,
  ordered shutdown during slow run, pattern 16 rejected on startup e
  recovery after removal. Target `make e2e-upgrade`.
- `tests/e2e/check_two_instances.py`: two simultaneous stacks with project, ports,
  distinct credentials, networks and volumes; assistants and API keys do not cross the
  border; stop of A does not affect B. Target `make e2e-two-instances`.
- Evidence: `make e2e-upgrade` exit 0; `make e2e-two-instances` exit 0;
  `make e2e` exit 0 after new Compose dependencies. Next task: M6-09.

## 2026-10-26 — M6-09, final gate and release candidate 0.1.0

- Executed all mandatory gates on the current version: `make test`,
  `make build-packages`, `make e2e`, `make e2e-upgrade`,
  `make e2e-two-instances`, `make e2e-restore`, browser 13/13,
  `make test-security`, `make release-dry-run`/`release-check`. All exits 0.
- Fixed restore fixture: env file did not set `RUSTFS_*`, required
  from Compose interpolation even with inactive s3 profile; now restore
  isolated passes again.
- Added [acceptance-report.md](acceptance-report.md) with the 13 criteria and
  evidence, and [RELEASE_NOTES.md](release-notes.md) with the release candidate
  local 0.1.0. The `release/` bundle also includes these documents and comes
  validated by checksum/secret scan.
- The 3 skipped runtime tests (real Ollama, real S3, real Qdrant) are listed
  explicitly and not counted as successes. The historical contract diff remains
  verified by the workflow on the previous tag; the local workspace has no tags.
- Evidence: green Docker/PostgreSQL/E2E gates, demonstrated isolated upgrade,
  release candidate not published. Publishing/deploy remain separate actions.
- Milestone 6 completed.