# ADR 0008 — Durable jobs and optional services

**Status:** proposed for future milestones. The explicit constraints of PROJECT_SPEC.md
remain mandatory; this document does not declare the proposed capabilities implemented.
**Date:** 2026-10-22.
**Related tasks:** M3-06, M3-09, M6-04, M6-06, P-10. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

Ingestion requires recoverable asynchronous work. Starting Redis without a concrete case increases the minimum services and does not solve the loss of state after a crash by itself.

## Alternatives considered

Redis-only queue conflicts with authoritative PostgreSQL; synchronous execution blocks upload. PostgreSQL transactional job table with dedicated worker covers the initial requirement.

## Proposed decision

Authoritative job in PostgreSQL, created along with accepted metadata. Separate worker claims work with short transaction, lease/heartbeat, limited retries, backoff and inspectable terminal state. Parsing/embedding/HTTP out of long transactions. Repeatable operations by phase and version; completion publishes active index only after verification. Worker uses DB role restricted to data ingestion, without credentials/conversations privileges. Redis is added as an optional cache/limiter/transport only with measured need; never the only place where a job exists.

## Consequences and limits

It is necessary to plan recovery of expired leases and distinguish between canceled and failed jobs. We do not promise exactly-once execution of the worker; idempotent commits and index published once are guaranteed. Redis is not a core prerequisite.

## Verification required

Crash before/after commit phase, lease expired, two concurrent workers, deletion during embedding and Redis lost if enabled. Measure capacity before introducing an additional broker.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.