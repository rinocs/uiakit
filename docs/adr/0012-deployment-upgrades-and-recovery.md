# ADR 0012 — Deployment, observability and recovery

**Status:** proposed for future milestones. The explicit constraints of PROJECT_SPEC.md
remain mandatory; this document does not declare the proposed capabilities implemented.
**Date:** 2026-10-22.
**Related tasks:** M1-05, M1-06, M6-02…M6-09. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

M1 supports a single gateway with pending run recovery upon reboot. Multiple independent instances on the same host are not the same as multiple replicas on the same database.

## Alternatives considered

Enabling replication without ownership/lease can mark failed runs that are still active. Keeping single replica declared avoids a false promise of high availability; Scaling is a subsequent decision supported by measurements.

## Proposed decision

Compose core starts only necessary services; local-ai/full add optional capabilities. Networks and volumes per project, default local binding, runtime/DB not exposed: Gateway uses a non-internal `frontend` network for published ingress, while `backend` remains internal. Providers and connectors with explicit egress; TLS for remote exposure. Single database gateway until recovery with lease is designed and proven. Versioned migrations, backward-compatible when possible, backups before upgrades; application rollback only with compatible scheme, otherwise restore tried. Optional OpenTelemetry, redacted logs and bounded cardinality. Releases with versions/digests, SBOMs/licenses and startup/restore/upgrade tests.

## Consequences and limits

No promises of HA or destructive automatic rollback. Collector unavailable does not block runs, but the sensitive audit remains durable. Docker verification remains a real gate, not replaceable by Compose config or unit tests. Publishing and public deployment are actions distinct from preparing a release.

## Verification required

Two stacks with separate credentials/volumes/networks/ports, graceful shutdown during run, upgrade old→new, restore to new environment and failure injection. Measure latency/CPU/RAM/queue before changing architecture.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.