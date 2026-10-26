# ADR 0013 — Assistant versions and execution snapshots

**Status:** adopted in M2-03 implementation; PostgreSQL/Docker test open.
**Date:** 2026-10-22.
**Tasks:** M2-03, M4-01, M6-08. [Backlog](../TASKS.md).

## Context

An editable assistant must maintain run history and reproducibility.
The idempotent key must return the original result even after a modification.
The runtime must verify capability without receiving provider secrets from the API.

## Alternatives

- Save only the current configuration: simple but loses historical provenance.
- Save only a version reference: sufficient in the gateway but requires
  additional lookups to pass context to Python and maintain provider metadata.
- Immutable versions plus snapshots in run: more data, explicit runtime boundary.

## Decision

assistant_versions is append-only via API, with trigger that prevents UPDATE; the head
assistants.current_version points to the current version. PATCH uses If-Match/ETag,
lock on the head and subsequent reading of the version in a second query. The run
preserves FK assistant_id/version, JSON configuration and model metadata before
start HTTP. The lock ends at commit, before generation. Replay reads
the original snapshot without revalidating it on the active catalog or recalling the model.

The runtime owns the adapter capabilities and serves an authenticated catalog.
The gateway imports a copy without secrets into PostgreSQL at startup. The model
active is one at this stage. Unknown data like context_window remains null.
The runtime compares model_snapshot with the active configuration and rejects mismatch;
Assistant limits reduce, but do not increase, the global cap.

## Consequences

Deliberate duplication of historical JSON per run in exchange for provenance and autonomy
of the internal contract. No hot reload or public endpoint for URL/key provider.
The new runtime must start before the new gateway, which requires the catalog;
rollback after 003 migration requires a compatible backup/schema. Configurations
of tools/RAG/skills not yet implemented fail 422 if activated.

## Evidence

Go/Python shared fixture; PATCH/ETag testing and prohibited fields, capabilities and snapshots
immutable; E2E versions, replays and two concurrent PATCHES expected [200,412]. The tests
Real SQL and upgrade remain open in the [registry](../progress.md).