# ADR 0004 — Directives, hooks, and protected context

**Status:** Adopted for context, pipeline, hooks, and five initial built-ins
(M2-01/M2-04/M2-05/M2-06); RAG and advanced policy tool remain in future tasks. Docker/E2E gate verified on 2026-10-23.
**Date:** 2026-10-22.
**Related tasks:** M2-01, M2-04, M2-05, M2-06, M3-11, M4-02. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

The runtime must be extensible without becoming an event emitter where each subscriber modifies state and policy. The pipeline must be deterministic and verifiable.

## Alternatives considered

A mutable emitter is simple but does not preserve order and authority. A typed pipeline with separate observers limits the editing surface without introducing a workflow engine.

## Proposed decision

ExecutionContext separates identities/permissions/limits from editable content. Registered directives, configured by assistant version and sorted by dependencies, then priority and stable tie-break. Missing loops/dependencies fail in configuration. Before/after models return validated context. Observational hooks receive immutable snapshots; modifying middlewares pass through the pipeline. Timeout for component; failures of mandatory guards stop the run, optional observers can fail in isolation with diagnostics. Security guards remain out of control of plugin removal.

## Consequences and limits

We need a typed representation of the context, not protection based on convention alone. There is no claim to sandbox trusted Python plugins: an administrator who installs trusted code assumes the risk of the process. The pipeline prevents escalation via framework APIs, not malicious native code.

## Verification required

Deterministic ordering, loops, timeouts, non-mutant hooks, and guard removal attempts. Integrate the six required directives when the respective capability arrives, without stubs pretending to do RAG.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Incremental implementation — 2026-10-22

M2-01: adopted immutable context, authority/limits separated from ModelInput and working memory per run. Directives and hooks not yet implemented. Evidence in the [progress log](../progress.md).

M2-04 (partial): Host registry, deterministic pipeline, and validation implemented
deep returns in the core, with before/after integration in the BasicAgent.
Mandatory directives cannot be deselected through the registry;
no sandboxing of hostile Python code. `after_model` reads `model_output`
immutable and can refuse completion, without rewriting deltas already sent.
Cooperative timeouts and explicit policies, with context errors always fail closed.
Gateway catalog/validation, public activation, observation hooks remain open
and built-in directives. Details in the [contract](../directives.md) and evidence in the register.

M2-04 completed in code: public selections validated by gateway through
POST authenticated `/internal/v1/directives/validate`, without duplicating the algorithm
of the core in Go. Maximum 64 unique names; invalid graphs rejected before
persistence. Deadline 5 seconds, no redirect/retry, 503 no new releases
in case of unavailability. Revalidation for selection runs and snapshots in
existing versions; no additional SQL migration. E2E Docker ready,
performed 2026-10-23; hooks and built-ins are checked in their respective tasks.

M2-05: Adopted ordered async subscribers, filters, immutable detached snapshots with
just metadata, callback timeouts and total budget per run. Observational errors
isolated and recorded without private content or exceptions; real cancellation
propagated, immediate upstream cleanup. Middleware and guards remain in the pipeline
protected. Best effort notifications, without promise of lasting audit; details in
[events contract/hook](../events-hooks.md). Docker/E2E gate verified on 2026-10-23.M2-06: five stateless built-ins in the core package, always installed in the
custom registers. register_guard introduces mandatory non-mutant host validators,
sorted after all middleware: no history changes after checks.
Middleware dependencies on guards are loops and are rejected. Initial History
protected in ExecutionContext, with trimming allowed only at suffix;
rejected whitespace output, metadata-only telemetry, and deny-by-default tools.
RAG remains M3-11. Agreement and Limitations in [builtin-directives.md](../builtin-directives.md).
Gate Docker/E2E verified 2026-10-23; no new DB owner or loader plugin anticipated.