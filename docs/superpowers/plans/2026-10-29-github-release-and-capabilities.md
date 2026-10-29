# GPL GitHub Release and Capability Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement accepted
> tasks inline. Checkboxes track implementation, not this planning/research work.

**Goal:** Release a usable GPLv3 self-hosted developer kit on GitHub, then close
the highest-value integration gaps without requiring Cheshire Cat parity.

**Architecture:** Preserve the Go gateway as the authorization/persistence owner,
Python runtime as the execution owner, and PostgreSQL worker queue as the job
owner. Reuse existing SDKs, plugin manager, approval bindings and RAG pipeline.
Fix source distribution before adding features.

**Tech Stack:** Go, Python, PostgreSQL, SvelteKit, Docker Compose, optional
Qdrant/Ollama; existing HTTP/SSE and JSON Schema contracts.

**Spec:** [Readiness and competitor assessment](../../open-source-readiness.md).
Status: the user approved implementation of the first public milestone with GPL.
First-party code uses `GPL-3.0-only`. Publication remains the explicit Task 5 gate;
P1/P2 are subsequent milestones, not prerequisites to this release.

## Global constraints

- Preserve unrelated working changes; do not commit the current dirty tree wholesale.
- No secrets, local agent state, runtime data, model weights or backup files in source bundles.
- Publication uses the existing `origin` repository unless the owner chooses otherwise.
- Repository visibility, releases and registry uploads happen only after reviewing concrete artifacts.
- Keep ownership/scopes, connector policy, DNS pinning, immutable versions, bounded budgets and audit.
- Keep semantic memory disabled and agents read-only until their own acceptance gates pass.
- No Redis, visual workflow engine, generic marketplace or mandatory new model service for v0.1.
- Write new docs in English; add them to the documentation index and MkDocs navigation.
- Public/internal contracts, SDKs and examples change together; unsupported features stay rejected.
- Implement migrations forward-only; document rollback/restore for new durable state.

## Review focus

1. Dirty checkout, ignored credentials or oversized archive members must not leak into a release (Task 1).
2. GPL metadata, SDK distribution and dependency notices must agree (Task 2).
3. Re-running setup must not rotate live secrets or overwrite existing configuration (Task 3).
4. URL redirects/DNS changes and plugin revocation must never bypass host policy (Tasks 6–7).
5. A restarted agent awaiting approval must not execute an effect twice or act on changed arguments (Task 10).

## Sequence and release gates

| Milestone | Tasks | Ship criterion | Effort estimate |
|---|---|---|---|
| Public v0.1 | 1–5 | Clean-clone install, current features, GPL, safe source bundle and community docs | 5–9 focused engineer-days |
| Integration v0.2 | 6–9, independently reviewable | URL ingestion, working isolated tools, selected skills, read-only MCP | 10–19 engineer-days |
| Optional v0.3 | 10–12 | Durable approved actions, opt-in memory, conversational forms | 16–29 engineer-days |

Estimates are planning ranges for one engineer, not deadlines. Confirm after
v0.1 smoke tests. Tasks 10–12 each require a scoped design before code because
they introduce durable state and user-data decisions. Existing 0.1.0 versioning
and tag history must be checked before selecting the actual public tag.

## Task 1: Export reviewed sources, not local runtime state — P0

**Files:** `scripts/release.py`, `tests/release/check_release.py`,
`tests/release/test_release_checks.py`, `.gitignore`, `.dockerignore`, `.github/workflows/release.yaml`.
Create `tests/release/test_source_archive.py` and a pinned/redacted secret-scan
workflow under `.github/workflows/`.

**Interface:** Keep `source_archive(output)` returning the produced Path. Require
a clean tracked release checkout and export its explicit commit with `git archive`.
Build images/packages from the same commit; the manifest records that commit.
Untracked files must never become source inputs. Fail closed if Git/ref verification
is unavailable; no recursive working-tree fallback.

- [ ] Add a temporary Git-repository regression fixture with tracked VERSION/README and untracked synthetic `.env`, `.bootstrap-admin-key`, `.aws`, `.codex`, `.worktrees`, backups and data; assert archive membership contains only approved tracked release paths.
- [ ] Assert modified tracked inputs reject a release build, reviewed tracked changes appear at the selected ref, symlinks cannot pull external contents into the bundle, and stale artifacts cannot be reused as the current release.
- [ ] Run the new tests and record expected failures against the current exporter.
- [ ] Replace recursive filesystem source selection with the verified commit export; exclude local-state directories from accidental Git addition and validate exported paths before packaging.
- [ ] Exclude the same credential/agent/worktree paths from Docker build contexts; check the context allow/deny rules with synthetic paths before building images.
- [ ] Reject sensitive member paths before size-based content scanning; test `.aws/credentials`, bootstrap tokens and an oversized synthetic credential file. Use a maintained secret scanner for content/history rather than expanding ad hoc regexes indefinitely.
- [ ] Run `python3 -m unittest discover -s tests/release -p 'test_*.py'`; expect no failures. Run redacted working-tree/full-history/artifact scans, record findings without values, and inspect previously built bundles. Revoke any exposed real credential before public distribution; history rewriting requires a separate reviewed action.

**Done:** A fixture proves local secrets never enter a bundle, and the actual
candidate's file list/hash/commit and redacted scan reports are reviewable.

## Task 2: Apply a coherent GPLv3 licensing policy — P0

**Files:** Create root `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
`.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/feature_request.yml`,
`.github/pull_request_template.md`. Modify README, `docs/releases.md`,
`docs/dependencies.md`, `scripts/release.py`, `tests/release/check_licenses.py`,
`tests/release/test_release_checks.py`, first-party `pyproject.toml`/`package.json`
files, npm lock root metadata, `packages/sdk-php/composer.json` and lock metadata,
and all `deploy/docker/*.Dockerfile` license labels.

**Interface:** Proposed first-party SPDX value `GPL-3.0-only`. Existing dependency
license identifiers remain unchanged. Keep package privacy flags until registry
publication is actually requested; a public Git repository does not require npm/PyPI.

- [ ] Confirm copyright holder, right to relicense all first-party contributions, precise GPL variant, and whether SDKs share the same terms. Default scope is GPL for all first-party code; do not add exceptions without an owner decision.
- [ ] Add failing metadata/inventory tests: first-party SBOM entries and OCI labels must match the chosen SPDX value; `UNLICENSED`/`proprietary` may not survive for released first-party components; unknown dependency licenses still fail.
- [ ] Add the unmodified official license text and project copyright/license notices; update manifests, generated notices and the first-party SBOM policy together. Replace the test that currently explicitly rejects GPL-3.0-only; do not broadly allow arbitrary GPL or custom dependencies without review.
- [ ] Explain GPL distribution obligations, HTTP/API boundaries, SDK incorporation and the GPL/AGPL network distinction. Inventory dependency source/notices obligations, including LGPL binary components and container packages; make corresponding source/build instructions available for the exact distributed release.
- [ ] Define contribution terms using the same license, a practical review/test path, and a private vulnerability-reporting channel verified with the owner. Use GitHub private reporting only after it is actually enabled; do not invent a security email.
- [ ] Run release unit tests, regenerate SBOM/notices with `make release-inventory`, and run `python3 tests/release/check_licenses.py release/sbom.cdx.json`. Review obligations beyond the automated allowlist.

**Done:** License text, source/packages/images and notices agree; community
contributors know how to contribute/report. GPL adoption alone does not clear P0.

## Task 3: One safe setup path and runnable examples — P0

**Files:** Create `scripts/bootstrap.py`, `tests/release/test_bootstrap.py`.
Modify `.env.example`, README, `docs/installation.md`, `docs/examples.md`,
`docs/console.md`, existing `examples/laravel/` and `examples/widget/` guides.

**Interface:** `python3 scripts/bootstrap.py` creates a missing `.env` from the
template, generates `POSTGRES_PASSWORD`, `INTERNAL_API_KEY`, `RUSTFS_ACCESS_KEY`,
`RUSTFS_SECRET_KEY` and the admin-key digest, writes mode 0600 and prints
the new admin key once. Existing `.env` causes a clear refusal without modifying
the file; external model credentials stay user-supplied. Do not read/overwrite
`.bootstrap-admin-key` or regenerate credentials on rerun.

- [ ] Test missing template, existing configuration, required generated values, file permissions and absence of secret values from failure output; run tests red first.
- [ ] Verify generated configuration with `docker compose --env-file <temporary-generated-env> config --quiet`. The current README's three-secret setup fails even in the core profile because RustFS credentials are required during interpolation; include both credentials in the unified bootstrap and test this regression explicitly.
- [ ] Implement using `pathlib`, `secrets`, `hashlib` and exclusive file creation; no setup service, dependency or automatic model download.
- [ ] Replace duplicated inline secret-generation snippets with this single supported command. Replace `<repository-url>` with the reviewed public URL at publication time.
- [ ] Provide two copyable demonstrations: website widget with expiring scoped tokens; server-side Laravel/PHP integration. Add a document-upload → completed job → cited answer walkthrough.
- [ ] Exercise both external-provider and local Ollama/full-profile paths from a clean checkout with empty data volumes; report measured prerequisites/startup steps, costs and model downloads.

**Done:** A new user can install and obtain a first answer without borrowing the
developer's environment or exposing admin credentials in browser code.

## Task 4: Align supported features and prove the candidate — P0

**Files:** README, `docs/assistants-models.md`, `docs/plugin-sdk.md`,
`docs/agents.md`, `docs/approvals.md`, `docs/acceptance-report.md`,
`.github/workflows/test.yaml`, `.github/workflows/release.yaml`, existing E2E fixtures.

- [ ] Remove stale statements that classify already-shipped RAG/tool/structured-output work as future milestones. Clearly state skills/semantic memory rejection, read-only model loop, plugin-install limits and single-instance topology.
- [ ] Ensure public PR CI runs with read-only token permissions and no production secrets. Configure redacted secret scanning for the reviewed history and candidate artifacts; a skipped external-service check is not a pass.
- [ ] Run `make test`, `make build-packages`, `make test-console-browser`, `make e2e`, `make e2e-upgrade` and `make e2e-restore` in their documented environments. Reuse existing tests instead of adding an equivalent parallel suite.
- [ ] Run `make docs` and `make release-dry-run` only after Task 1. Record commit, environment, pass/fail/skips, SBOM/notices, source membership and checksum evidence for that exact candidate.

**Done:** Reproducible clean-clone evidence replaces historical milestone claims.

## Task 5: Review and publish the public source release — P0 final step

**Files:** Release notes and `.github/workflows/release.yaml` only as required.

- [ ] Inspect current repository visibility/tag history and present the exact repository, license, commit, source artifact and release notes. Do not create a duplicate repository by default.
- [ ] After owner approval of that candidate, make the intended repository public if needed and create the reviewed release/tag. The existing workflow only uploads temporary Actions artifacts; GitHub Releases needs a separate explicit publishing step.
- [ ] Provide durable downloadable source/checksums/notices and verify the anonymous clone/install path. Keep registry pushes, hosted demos and package publication separate unless included in the approved candidate.

**Done:** A public GPL source release can be cloned and installed. GHCR images
are a convenience follow-up, not a requirement for free source availability.

## Task 6: Add safe URL-to-knowledge-base ingestion — P1

**Files:** `apps/gateway/documents.go`, `document_store.go`, `jobs.go`, a new
forward migration, `apps/worker/uai_worker/ingestion.py`,
`apps/runtime/uai_runtime/tools/connectors.py`, `tools/http.py`, new worker web-loader
module/tests, API contracts/SDKs, knowledge-base console upload action.

**Interface proposal:** `POST /v1/knowledge-bases/{id}/sources` with
`{ "url": "https://approved.example/page" }` returns `202` and a durable source/job
identifier. Only principals with existing KB/document write authority may submit.
Gateway validates authorization/input; the worker fetches, validates bytes and
feeds existing blob/document/chunk/index processing. A queued source is not yet
a completed document. Pin the exact schema/migration in this task's design before code.

- [ ] Add failing tests for unauthorized KB, disallowed host, private/metadata IPv4/IPv6, DNS rebinding, redirect, credentials in URL, excessive/compressed response, unsupported MIME and repeated requests.
- [ ] Reuse `httpx`, existing DNS/address validation and pinned transport; extract shared network-boundary code only where both owners need it. The admin explicitly enables allowed web hosts. Keep redirects disabled initially and do not inherit secret connector headers.
- [ ] Fetch one public page per job, with bounded time and at most 20 MiB decoded input; no crawler, browser execution, cookies or automatic refresh. Reuse current text/HTML/PDF validation and limits; redact source URLs in logs/errors and forbid credential-bearing URLs.
- [ ] Store source/provenance and job status; support cancellation/delete during fetch/index, deduplicate content, and preserve existing ACLs/citations. A repeated completed request must not create duplicate documents.
- [ ] Prove URL → worker → indexed chunks → cited answer and retry/cancellation in Docker/PostgreSQL E2E; update SDKs and console with the same contract.

**Done:** An explicitly authorized page becomes a traceable KB document without
introducing an unrestricted network client.

## Task 7: Make existing isolated tools usable by the model — P1

**Files:** `apps/runtime/uai_runtime/tool_loop.py`, `plugin_manager.py`,
`plugins/http_plugin.py`, `tool_registry.py`, `apps/runtime/tests/test_agent_loop.py`,
`test_isolated_plugins.py`, `tests/e2e/check_isolated_plugin.py`.

**Interface:** Extend `_available_tools(context, catalog)` to admit authorized
read-only `isolated` tools, using the same executor/journal as standalone plugin
execution. Do not bypass policy or add plugin discovery/installation endpoints.

- [ ] Add a failing model tool-call test that reaches an approved isolated mock plugin and produces the normal terminal answer.
- [ ] Test missing grants/scopes, forbidden connectors, deactivation after selection, snapshot leases, timeout and malformed/oversized responses; unauthorized cases must make zero remote calls.
- [ ] Connect the existing isolated executor path to the loop, preserving audit and budgets. Run runtime agent/plugin tests and the isolated-plugin Docker gate.

**Done:** Existing HTTP plugin capabilities work through an actual assistant run.

## Task 8: Connect registered skills to assistant execution — P1

**Files:** `packages/core/src/uai_core/configuration.py`,
`packages/plugin-sdk/src/uai_plugin_sdk/skills.py`, runtime plugin-manager/agent
composition, `apps/gateway/assistants.go`, directive validation/catalog routes,
shared contracts/SDKs, assistant console form and runtime tests.

- [ ] Test selected registered skills in both basic/tool agents, unknown IDs, disabled plugins, duplicates, rendered context limits and in-flight configuration changes.
- [ ] Resolve IDs only from approved active plugin snapshots; render existing Skill objects as untrusted reference text using the existing renderer. No arbitrary paths, imports, commands or added permissions.
- [ ] Remove the nonempty-skills rejection in Go/Python/contracts only when runtime preflight validates selection. Keep semantic memory and approval guards intact.
- [ ] Publish the supported skill catalog, regenerate SDK types and prove an assistant selecting a skill receives it while a different assistant does not.

**Done:** A capability already implemented in the SDK is selectable and bounded
through the public API, not just directly callable in tests.

## Task 9: Read-only remote MCP integration — P1 after Task 7

**Files:** New `apps/runtime/uai_runtime/tools/mcp.py`, host-approved MCP config,
tool-registry/loop composition and plugin lifecycle files; new runtime MCP tests
and E2E fixture. Update tool contracts/SDK docs only for working capabilities.

- [ ] Pin a supported protocol/SDK version after checking its current security model and license. Use the maintained SDK if it lowers total complexity; do not implement JSON-RPC/session semantics by hand.
- [ ] Initially support admin-configured remote Streamable HTTP servers and explicitly selected read-only tools. No stdio process launch, dynamic server installation, OAuth UI, resource/prompt execution or model-selected endpoints.
- [ ] Namespace tools and pin approved schema/version snapshots. A remote `readOnlyHint` is not authorization: the administrator must classify/approve tools, scopes and connectors.
- [ ] Route calls through existing authorization, argument/output validation, budget, audit and durable execution. Enforce destination validation/DNS policy on every request and secret-reference/session isolation; if SDK transport cannot preserve this boundary, do not enable it.
- [ ] Test schema drift, duplicate IDs, unauthorized calls, reconnect/session expiry, malicious output, timeouts, deactivation and shutdown. Prove one MCP tool in a real assistant conversation.

**Done:** MCP exists as an operational, constrained adapter rather than an enum.

## Task 10: Durable human-approved write actions — P2, separate design

**Owners/files:** Gateway `agent_run_store.go`, `approval_store.go`,
`tool_execution_store.go`, new migration; runtime `tool_loop.py`, `approvals.py`,
`tool_executor.py`, `tool_registry.py`; approval console and API/SDK contracts.

- [ ] Design a persisted pending tool-call/checkpoint containing canonical arguments, model tool-call correlation, assistant/tool/policy versions and consumed budgets. Currently approvals keep only digests: restart cannot reconstruct the arguments from a digest.
- [ ] Define who may inspect/redact argument previews, sensitive-field storage/retention and approver policy before persisting new content. The human must see a meaningful effect summary, not approve only a hash.
- [ ] Keep gateway authoritative for waiting/decision/resume and atomic approval consumption. Do not keep an HTTP stream or DB transaction open during human wait. Define a backward-compatible resume/event contract and recovery owner before enabling mutating tools.
- [ ] Revalidate policy and exact arguments at execution; use existing single-attempt effect journal, never claim external exactly-once delivery, and surface unknown outcomes for reconciliation.
- [ ] Test restart while waiting, two approvers/resumers, expired/revoked approval, changed tool/policy, cancellation, exceeded budgets, and a crash/timeout after the external effect. Assert the mock effect counter stays one and stale approvals produce no effect.

**Done:** A real user requests a write, reviews its exact scope, approves it,
and sees a recoverable outcome across restart without silent duplicate effects.

## Task 11: Opt-in semantic memory — P2, separate design

**Owners/files:** Core `memory.py`/configuration, new gateway memory store/API and
migration, existing worker/index cleanup, runtime memory directive/retrieval,
privacy docs and console memory management.

- [ ] Start with user-confirmed memory facts scoped to principal and assistant; no silent indexing of every conversation. Add read/list/delete before automatic extraction.
- [ ] Keep PostgreSQL authoritative with provenance, timestamps, embedding version and source links; reuse embedding/vector adapters while keeping memory authorization separate from document KB access.
- [ ] Specify per-memory and context budgets, opt-in, retention, edit/delete, source-conversation deletion, tombstones and restore behavior before enabling `memory.semantic`.
- [ ] Test cross-principal/assistant isolation, opt-out, disabled/missing index, delete during embedding/reindex and vector-cleanup retry. Audit metadata must not duplicate remembered text.

**Done:** Users can inspect, control and remove every persistent fact; retrieval
cannot expose another principal's memory or revive a deleted record.

## Task 12: Schema-driven conversational forms — P2, separate design

**Owners/files:** Core form-state contract, gateway conversation form store and
migration, runtime collection directive, widget/console review UI, contracts/SDKs.

- [ ] Define host-approved JSON Schema forms, explicit start/cancel, persisted field values/validation, confirmation and expiry. Reuse structured extraction; no new workflow engine or arbitrary Python form code.
- [ ] Test missing/invalid fields, corrections, locale-specific values, cancellation and restart. Confirmation alone grants no tool permissions.
- [ ] For submission with effects, bind the exact confirmed values to Task 10 approval/execution; editing a confirmed field invalidates the old confirmation. A form definition must declare required tools at host configuration time.

**Done:** A user can complete, review, correct and cancel a form; any submission
with effects follows the same approval and idempotency controls as other actions.

## Explicit deferrals

Visual workflow editor, arbitrary ZIP/registry plugin installation, hot reload,
WebSocket compatibility, procedural vector tool selection, OCR/Git/SQL loaders,
SSO/OIDC, simultaneous native multi-provider routing, multi-agent orchestration
and HA are not first-release blockers. Revisit on user evidence. Remote model
providers compatible with the existing adapter need documentation, not new code.

## Planning verification

Research used upstream README/license files for seven competitors. Local source
inspection, a synthetic archive reproduction and clean-template Compose failure
informed Tasks 1–3; secret values were not inspected. Implementation checkboxes
remain open. Fresh validation: 8 release unit tests passed, the existing source
metadata check passed, and new documentation links/navigation registrations were
verified. Strict MkDocs build was attempted but unavailable (`No module named
mkdocs`). These are planning checks, not the future feature acceptance gates.

## Implementation evidence

Tasks 1–3 are implemented and the local Task 4 checks pass: full suite, package
builds, strict MkDocs, 25 browser tests, E2E, schema upgrade and backup/restore.
The release-tool suite contains 26 passing tests, including synthetic archive
inclusion, tracked dirtiness, stale stage markers, uploaded-marker removal,
missing/image commit provenance, GPL package metadata and bootstrap overwrite
protection. Three optional real-service runtime tests remain skipped.

An independent staged-diff review found two Important candidate-provenance issues;
both were reproduced by failing tests and fixed. The review's minor command-copy
issue was corrected. Build packaging now installs/builds from a temporary source
export instead of trusting untracked development outputs. Candidate artifact
checks must run on the final clean commit, before Task 5.
