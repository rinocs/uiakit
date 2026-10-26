# ADR 0002 — API, SSE and Compatibility Agreements

**Status:** adopted for SSE v1 and M2-05 observational lifecycle; future extensions
proposals remain. Docker/E2E gate verified on 2026-10-23.
**Date:** 2026-10-22.
**Related tasks:** M1-01, M1-04, M2-05, M4-01, M5-10, M6-07. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

The core already has API /v1 and envelope SSE v1. Extending lifecycle and SDK without separating public and internal would make every runtime change a client change.

## Alternatives considered

A single public/internal contract reduces documents but couples implementations. Distinct, versioned contracts keep the gateway accountable to the public; is the proposed choice.

## Proposed decision

Keep OpenAPI 3.1 public and internal schema distinct. Events carry event_id, event_type, event_version, UTC timestamp, run_id, and correlation_id; Phase-specific payloads. Distinguish observational events from middleware. Compatible additions are additive; breaking change requires new version, fixture and client migration. EOF without terminal does not equal completion. The gateway persists before the terminal; full replay for Idempotency-Key, without promising Last-Event-ID resume. A run resumes the original assistant version.

## Consequences and limits

Two contracts to maintain and validate. The initial SSE format remains compatible; new events must be tolerated by clients without losing terminal recognition. Request-level event before run creation must have its own pattern, without inventing persisted run IDs.

## Verification required

Public/internal snapshot, fragmented SSE/Unicode parser, replay after PostgreSQL JSONB, anomalous EOF and contract diff of SDKs. SSE basis already implemented; lifecycle extensions remain to be implemented.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Implementation M2-05 — 2026-10-22

Shared core envelope; RuntimeEvent holds the four public SSE events.
LifecycleEvent has 18 phases typed in a distinct internal JSON schema, with
immutable metadata and stage/payload constraints. Observations of public frames
they preserve UUID/timestamp/correlation, without arbitrary text or usage.
BasicAgent outputs real available and agent.cancelled phases to observers;
does not simulate tool/memory events before their implementations. The events
requests are for accepted runs, with no invented IDs for rejected HTTP requests.
The gateway continues to reject metadata on the public channel; border tests,
lifecycle sequence and replays linked to the suite. No SQL migration.
Documentation and limitations in [events-hooks.md](../events-hooks.md).

## Implementation M4-01

Added `agent.cancelled` to SSE/event contract, persistent run state and API
`/v1/agent-runs` with cancel compare-and-set. The deleted run persists
terminal and replay; lifecycle events remain metadata-only. Details in
[agent-runs.md](../agent-runs.md).