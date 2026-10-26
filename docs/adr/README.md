# Architecture Decision Records

[ADR 0001](0001-functional-core.md) describes the choices implemented in the M1 core.
Subsequent ADRs distinguish adopted parts and proposals for future work,
as indicated in the status and implementation notes. They do not constitute endorsements
implicit deployment or publishing.
The constraints prescribed by the [specification](../project-spec.md) remain mandatory.

| ADR | Decision | Status | Tasks |
|---|---|---|---|
| [0001](0001-functional-core.md) | Functional Core, Go/Python boundaries, persistence and SSE | Adopted in M1; Docker/E2E verified | M1-01…M1-06 |
| [0002](0002-api-contracts-and-events.md) | API, SSE and Compatibility Agreements | Partially adopted (M2-05/M4-01); Future SDKs | M1-01, M1-04, M2-05, M4-01, M5-10, M6-07 |
| [0003](0003-authorization-and-secrets.md) | Authority, credentials and ownership | Partially adopted (M2-02/M2-03); future secret stores | M2-02, M2-03, M3-01, M4-02, M5-04, M6-04 |
| [0004](0004-directive-and-hook-lifecycle.md) | Directives, hooks and protected context | Partially adopted (M2-01…M2-06) | M2-01, M2-04, M2-05, M2-06, M3-11, M4-02 |
| [0005](0005-plugin-trust-and-lifecycle.md) | Trusted and isolated plugin | Adopted (trusted M2-08/M2-09); Docker verified | M2-08, M2-09, M4-09, P-01 |
| [0006](0006-tool-effects-and-approvals.md) | Tools, approvals and effect idempotence | Partially adopted (M2-07) | M2-07, M4-02, M4-03, M4-04, M4-05, M4-08 |
| [0007](0007-rag-data-and-provenance.md) | RAG data, isolation and citations | Adopted (M3-01…M3-11) | M3-01…M3-11, M6-01, M6-02 |
| [0008](0008-durable-jobs-and-optional-redis.md) | Durable jobs and optional services | Proposed | M3-06, M3-09, M6-04, M6-06, P-10 |
| [0009](0009-providers-and-model-capabilities.md) | Provider, capability and budget model | Partially adopted (M1-03/M2-03/M3-07); future budgets | M1-03, M2-03, M3-07, M4-06, M4-07, P-03, P-08, P-09 |
| [0010](0010-memory-and-data-lifecycle.md) | Memory and data lifecycle | Partially adopted (M2-01/M2-06) | M2-01, M2-06, M6-01, M6-02, P-02 |
| [0011](0011-sdks-widget-and-console.md) | SDK, widgets and administrative console | Proposed | M5-01…M5-10 |
| [0012](0012-deployment-upgrades-and-recovery.md) | Deployment, observability and recovery | Partially adopted (M1-05/M1-06); future upgrades/recoveries | M1-05, M1-06, M6-02…M6-09 |
| [0013](0013-assistant-version-snapshots.md) | Assistant and snapshot versions | Adopted in the code; SQL/restart verified | M2-03, M4-01, M6-08 |

Each ADR contains context, alternatives, proposed decision, consequences/limitations and
tests required. A task applies the relevant decision, checks its invariants
and update the status; if a substantial architectural change emerges, a new one
ADR explicitly states which precedent it replaces. No ADR needed for
every local detail: record only choices with impact between components,
trust boundaries, contracts, data or operations.

Work Index: [TASKS.md](../TASKS.md).