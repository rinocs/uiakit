# Audit of sensitive operations

The audit is an append-only trail in PostgreSQL (`audit_events`, migration 013).
Record permissions, configuration, approval decisions, and transitions
of tool executions. It is not an application log: the details are projections
explicit and redacted, never raw HTTP requests.

## Camps and reconstruction

Each event holds `actor_principal_id`, `action`, `target_id`, `target_type`,
`run_id`, `correlation_id`, `digest`, `outcome`, `details` and `created_at`.
`run_id` connects the run, `correlation_id` is stable even after restart (column
`agent_runs.correlation_id`), `digest` is SHA-256 of contents/configuration
canons, not the content.

Main actions:

| Action | Target | Useful details |
| --- | --- | --- |
| `agent_run.started` | run | assistant/version/model; digest input |
| `agent_run.cancelled` | run | previous state |
| `assistant.created` / `assistant.updated` | assistant | model, tool count, structured output; digest config |
| `credential.created` / `rotated` / `revoked` | credentials | principal, role, scopes |
| `approval.approved` / `rejected` / `expired` / `invalidated` | approval | tool/version, policy digest; digest topics |
| `tool_execution.reserved` / `started` / `completed` / `failed` / `unknown` / `retried` / `reconciled` | execution | tool/version, risk, attempt, error code; digest topics |

Bodies, arguments, results, prompts, and headers are not saved.
An execution can be reconstructed from run + digest + approval + transitions; one
decision from run + approval + digest + outcome.

## Centralized editorial staff

`redactAuditValue` in `apps/gateway/audit.go` and `redact_details` in
`apps/runtime/uai_runtime/audit.py` apply the same list of sensitive keys
(headers, authorization, cookie, token, password, secret, api key, key digest,
policy snapshot, prompt, messages, arguments, result, body). The editorial team is
recursive and is applied both in writing and reading. Unknown fields
they are not serialized. The runtime only records bindings (tool/version/risk,
digest, run/correlation) before the effect; if the recorder fails, the runner
ends with `audit_unavailable` and does not invoke the executor.

## Transactionality and effect blocking

Writes occur in the same transaction as mutation:

- run creation: audit `agent_run.started` before commit, then runtime
  is not called if the audit fails;
- reservation/start tool: transition audit before commit; an error
  cancel reservation and consumption of approval and block the effect;
- approval decision: audit before commit, along with run status;
- assistant/credentials configuration: audit in the existing transaction.

## Protected reading

`GET /v1/audit-events` requires `audit:read`, granted only to the admin role.
Filters: `run_id`, `action`, `target_id`, `limit` (1–200, default 100). The details
they are redacted again on release. No public endpoints allow writing.

## Retention

`retention_class` is `security` by default; the duration, cancellation policy and
minimization is defined in M6-01. The audit is not implicitly canceled
with the run (`run_id ON DELETE SET NULL`), so the trail remains available.

## Checks

`apps/gateway/audit_test.go`, `apps/runtime/tests/test_audit.py`,
`tests/e2e/check_approvals.py` and SQL assertions in `tests/e2e/run.sh`
verify editorial staff, scope, run/correlation/digest binding, absence of secrets
and presence of tool transitions.