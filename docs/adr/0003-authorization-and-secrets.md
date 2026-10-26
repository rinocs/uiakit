# ADR 0003 — Authority, credentials and ownership

**Status:** proposed for future milestones. The explicit constraints of PROJECT_SPEC.md
remain mandatory; this document does not declare the proposed capabilities implemented.
**Date:** 2026-10-22.
**Related tasks:** M2-02, M2-03, M3-01, M4-02, M5-04, M6-04. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

The M1 uses a single hashed operator key. Plugins, RAGs and browsers introduce identities and resources with different permissions; the generated text is not a source of authority.

## Alternatives considered

Auth left to plugins or template does not protect data. Centralized Auth in the gateway with final policy in the tool executor maintains a single public boundary and defense against the effect.

## Proposed decision

The gateway authenticates and constructs principals, scopes and authorized resources; runtimes/plugins receive only the necessary context. Deny-by-default authorization and verify ownership on each resource. Credentials persist only as high-entropy key digests, with revocation, expiration and rotation; provider/connector secrets via references, never in the model or responses. Administrative RBAC and limited widget tokens are distinct credentials. Approval does not grant missing privileges. Draw the concrete roles/scopes matrix in task M2-02 before migration.

## Consequences and limits

The M1 bootstrap requires a compatible and revocable migration. We do not introduce a system of organizations, billings or tenants external to the specification. Isolation for principal/resource must still be verified. The internal bearer authenticates a trusted service, it does not transform model inputs into authorizations.

## Verification required

Allow/deny matrix, resources belonging to another principal, rotation/revocation and expired widget token. Test that prompt, document, plugin and tool results cannot extend the authorized context.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Incremental implementation — 2026-10-22

M2-02: credentials, roles/scopes, ownership, key management audit and principal propagation implemented. Open SQL/Docker testing; widget tokens and future connector secrets. Evidence in the [progress log](../progress.md).