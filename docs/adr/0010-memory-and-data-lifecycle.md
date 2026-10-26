# ADR 0010 — Memory and data lifecycle

**Status:** adopted for working memory and history authorized M2-06; adapter
mutant, retention and deletion policies remain planned in M6-01.
**Date:** 2026-10-22.
**Related tasks:** M2-01, M2-06, M6-01, M6-02, P-02. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

Persistent history already exists; an automatic semantic memory would introduce additional persistence and copies that are difficult to delete without explicit policies.

## Alternatives considered

A single store for all memories makes retention and deletion less visible. Three levels with separate ownership and policies meet the requirement of the specification.

## Proposed decision

Working memory limited to the life of the run; conversation memory persisted by the gateway, accessible through an authorized MemoryProvider and explicit contracts; semantic memory disabled by default. Define read/write/delete/retention without granting plugins indiscriminate DB access. Policy for messages, documents, vectors, jobs, audits and backups before production use. Tombstone deletion and repeatable cleanup of derivatives, preventing reindex or cache from reintroducing data. Any semantic memory requires opt-in, scope, provenance and verified deletion policy.

## Consequences and limits

Backed up data cannot be deleted retroactively from each copy: retention/expiration and restore with tombstone must be declared. Audit can have different retention than content, with minimization. No implicit saving of each output in vectors.

## Verification required

Memory isolation between run/principal, delete during ingestion, cache/stale vectors, reindex after delete, restore and retention expiration. No semantic memory activated before the relevant gate.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Incremental implementation — 2026-10-22

M2-01: WorkingMemory bounded and isolated, MemoryProvider contract; gateway maintains conversation persistence. Mutation/retention adapter M2-06 and policy M6-01 remain future. Evidence in the [progress log](../progress.md).

M2-06: ConversationMemoryDirective validates the history prepared by the gateway
against an original protected tuple in ExecutionContext. Allows trimming to
suffix and enforce memory.conversation=false without deleting persisted data.
The gateway remains the owner of existing PostgreSQL reads and commits. They don't come
simulate memory.read/write events nor implement no-op mutations in the runtime.
The previous mutant adapter referral to M2-06 is updated to M6-01:
the cancellation/retention policies of the same task are needed. Cost: the new one
Python conversation memory mutation API remains unavailable, while
the conversational persistence of the product continues in the gateway.