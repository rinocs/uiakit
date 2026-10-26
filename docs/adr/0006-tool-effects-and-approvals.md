# ADR 0006 — Tools, approvals and effect idempotence

**Status:** adopted for M2-07 registry/executor, M4-02 policy, M4-03 read-only HTTP connector, M4-04 approvals, M4-05 reservation, and M4-06 read-only loop; MCP and effects integration remain in the M4 tasks.
**Date:** 2026-10-22.
**Related tasks:** M2-07, M4-02, M4-03, M4-04, M4-05, M4-08. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

A model proposes actions, but cannot authorize them. Retry and crash between external HTTP request and local commit make it impossible to promise exactly-once without recipient cooperation.

## Alternatives considered

Executing template requests directly is insecure. A centralized executor with durable reservation, approval and explicit connectors makes the effect controllable.

## Proposed decision

Authoritative registry with input/output patterns and risk. Order: validate→authorize→limits→approval→reserve durable execution→execute→validate result→audit→return. Persist immutable tool/version and canonical arguments; approval linked to digest, run, principal approver, deadline and status, consumed atomically. Connector contains destination and secret references: the template does not provide URLs, auth headers or privileges. SSRF also protected on DNS/connection and redirect, with private networks only explicitly allowed. Mutations require idempotency key propagation when supported. External outcome unknown becomes unknown to be reconciled; no blind retry.

## Consequences and limits

An approval may expire or become invalid due to a policy change. You do not keep a DB transaction open during HTTP or human wait. Durable audit before sensitive effects; optional observability remains separate. The idempotent key of the message does not replace that of the individual tool execution.

## Verification required

Approval concurrency, modified arguments, timeout after effect, provider repeating call ID, bad input/output schema, and SSRF with redirect/DNS. The test checks the effect counter on the mock server, not just the wrapper calls.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Implementation M2-07 — 2026-10-22

ToolDefinition in core, unique host registry with descriptor snapshots and
Pydantic input/output models that generate the published schemas. The executor
standalone requires explicit scope and grant before validating parameters; such
order immediately denies unauthorized callers. Only one async handler invoked
time, timeout and budget before/after normalization, revalidated output and audit
local metadata-only through logs and hooks. Propagated real cancellation.

Default builtin.text_stats read-only, no network/file/model. GET /v1/tools is
a catalog protected by tools:read; the callable is not published. None
Public HTTP execution, installation from generated code, or tool calling in the
BasicAgent. Tool with effects rejected with approval_required, without simulating
lasting approvals or audits. Contract and Limits in [tools.md](../tools.md).
Gate Docker/E2E verified 2026-10-23; no additional SQL migration.

M4-02 implements the single policy: `ToolPolicyDirective` intersects grant, scope,
snapshot assistant, registry and allowlist connector and is re-evaluated immediately
before the effect. Prompts, documents, outputs and plugins do not add permissions;
BasicAgent remains without tool calling until M4-06.

M4-03 implements the HTTP boundary: the model does not provide URL/header, connectors
they are administrative, all DNS addresses are validated and the socket is pinned
to the approved address; redirect, proxy and Unix socket are disabled. The tools
Mutant HTTPs remain unpublishable until M4-05.M4-04 implements immutable binding: canonical digest of arguments, policy
snapshot, tool/version, run and expiry. The decision is transactional and
compare-and-set; only one more `waiting_approval` run restarts after the decision
persisted. Approval does not grant missing privileges and atomic consumption
after the effect remains M4-05/M4-06.

M4-05 implements reservation before effect: unique idempotent key for
run, tool/version/digest binding, approval atomic consumption, and status
durable. Retries are limited to read-only tools; a mutant with unknown outcome
becomes `unknown` and is not blindly retried. The absence of remains explicit
an exactly-once promise over external HTTP.

M4-06 connects the loop provider to the authorized read-only tools: tool call native,
untrusted results, maximum 4 generations/8 calls, mandatory capability.
Mutant tools are not offered until integration with approval and resumption
of the run is not completed.