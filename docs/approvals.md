# Constrained human approvals

Approvals are immutable records between tool requests and requests
human decision. The gateway is the authoritative source; the runtime produces the binding
canonical in `uai_runtime.approvals`.

## Bindings

`Approval.create` binds:

- `run_id`, `tool_id` and `tool_version`;
- `arguments_digest`, SHA-256 of the canonical JSON of the arguments (sorted keys,
  compact separators, no unfinished values);
- `policy_digest` and `policy_snapshot`, which include principal/scopes/grant,
  server version and tool, tool permissions/risk/executor and
  allowlist connector host;
- `requested_by`, `created_at` and `expires_at` (maximum 24 hours).

Full arguments are not persisted - only the digest. The policy snapshot
it is JSON bounded to 8 KiB and contains no prompts or user text. Edit
arguments, tool version, scopes, grant, assistant version or policy makes the
binding no longer matches (including a change to the allowlist connector).

States: `pending → approved|rejected|expired|invalidated`; an `approved` can
become `consumed` only once. Approve twice, reuse an approval
consumed or consuming an expired/unapproved one fails with stable code.

## API

| Method | Path | Roles |
| --- | --- | --- |
| GET | `/v1/approvals` | `approvals:read` |
| GET | `/v1/approvals/{id}` | `approvals:read` |
| POST | `/v1/approvals/{id}/approve` | `approvals:write` |
| POST | `/v1/approvals/{id}/reject` | `approvals:write` |

Only operator/admin can receive these scopes; a key reader doesn't get them
automatically. The list is sorted by creation and limited to 200 items. Le
answers expose bindings and snapshots, never arguments or secrets.

## Decision and run

The decision uses a transaction with approval and run locks:

- an expired approval is persisted as `expired` and the decision is
  rejected with 409;
- a competing decision loses with 409 after the first;
- if the run is no longer `waiting_approval` (deleted or already terminated),
  the approval is invalidated and the decision is rejected;
- `approve` takes the run from `waiting_approval` to `running`;
- `reject` makes the run `failed`;
- each decision writes an `approval.approved`/`approval.rejected` audit event
  with run, correlation, topic digest, tool/version and outcome
  ([audit.md](audit.md)).

The run does not restart before the decision has been committed. The recovery of
loop and atomic consumption of approval after effect are integrated into
M4-06/M4-05; M4-04 provides binding, persistence and decision contract.

Migration: `apps/gateway/migrations/011_approvals.sql`.
Runtime tests: `apps/runtime/tests/test_approvals.py`; gateway tests:
`apps/gateway/approvals_test.go`; E2E: `tests/e2e/check_approvals.py`
(concurrent decision, deadline, reject, scope and resume on real PostgreSQL).