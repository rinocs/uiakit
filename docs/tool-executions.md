# Durable tool executions

A tool execution with effects is reserved in the gateway before invoking
the executor. The gateway is the authoritative source; the runtime preserves the binding
canonical and the internal client in `uai_runtime.tool_executor`.

## Order

The caller must apply: input validation → authorization policy → limits →
approval → **durable reservation** → executor → output validation → audit →
result. Durable auditing of transitions is implemented in M4-08 ([audit.md](audit.md)). The reservation does not replace the policy: a confidential execution
without grant/approval it remains a caller error.

`build_execution_request(context, tool, arguments, tool_call_id=..., approval_id=...)`
calculate:

- canonical `arguments_digest`;
- a stable `idempotency_key` from run, tool_call_id, tool/version, digest and
  ID approval;
- `max_attempts = 2` for read-only, `1` for write/destructive;
- mandatory approval for effects.

## States

`tool_executions` (migration 012) holds run, tool/version, digest, approval,
risk, idempotent key, attempt, result/error code and timestamp.
`UNIQUE(run_id,idempotency_key)` prevents duplicate runs.

- `reserved → running → completed|failed|unknown`;
- `completed` is played without calling the executor again;
- a `failed` read-only can be resumed up to `max_attempts`;
- a `failed` mutant is not retried;
- a timeout/mutant error or crash with unknown outcome becomes `unknown`, never
  automatically retried;
- a `reserved/running` reservation that has been held for more than 60 seconds becomes `unknown`
  (`execution_lease_expired`);
- an `unknown` can be explicitly reconciled to `completed` or `failed`.

An approval is consumed atomically in the same transaction as the
reservation; tool/version/digest/run must match and approval must
be `approved` and not expired.

## Runtime

`DurableToolRunner` runs reserve/start/invoke/complete and applies retries:

- read-only: `tool_timeout` and `connector_unavailable` only, within the limit;
- mutant: any error after start produces `unknown`, no retry;
- `CancelledError` produces `unknown/cancelled` and propagates the cancellation;
- invalid output is `failed` for read-only and `unknown` for mutant, because
  the effect may have already occurred.

`GatewayExecutionJournal` uses internal endpoints with Bearer internal key,
timeout, no redirect and `trust_env=False`.

## Internal API

| Method | Path |
| --- | --- |
| POST | `/internal/v1/tool-executions/reserve` |
| GET | `/internal/v1/tool-executions/{id}` |
| POST | `/internal/v1/tool-executions/{id}/start` |
| POST | `/internal/v1/tool-executions/{id}/complete` |
| POST | `/internal/v1/tool-executions/{id}/fail` |
| POST | `/internal/v1/tool-executions/{id}/unknown` |
| POST | `/internal/v1/tool-executions/{id}/reconcile` |

They are not exposed to the public client. The reserve body is
`ToolExecutionRequest`; complete accepts `{"result": ...}`; fail/unknown
accept `{"error_code": "..."}`; reconcile accepts
`{"status":"completed|failed","result":...,"error_code":...}`.

Results limited to 128 KiB. The runner does not promise exactly-once over HTTP
external: server, proxy and timeouts can leave an unknown outcome; for this
`unknown` state and explicit reconciliation exist.

Tests: `apps/runtime/tests/test_tool_idempotency.py`, `apps/gateway/tool_executions_test.go`,
E2E `tests/e2e/check_tool_executions.py` (reserve/replay/retry/unknown/reconcile
on real PostgreSQL).