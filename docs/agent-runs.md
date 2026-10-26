# Agent run state and deletion
Persistent run state in PostgreSQL, read/cancel API with ownership,
compare-and-set transitions and deletion propagation to runtime/provider.
SSE and replay maintain terminal semantics.

## States and transitions

```text
queued/running/waiting_approval ──cancel──> canceled
running ──success──> completed
running ──error──> failed
```

- Migration 010 allows `queued`, `running`, `waiting_approval`, `completed`,
  `failed`, `cancelled` and adds `updated_at`, `cancel_requested_at`.
- `Start` creates the `running` run; `Finish` uses compare-and-set on `status`.
- Deletion is only allowed by `queued`/`running`/`waiting_approval`;
  a terminal status returns 409.
- A hardened deletion before the stream closes allows a
  `Finish` to persist events while keeping `cancelled`.

## API

Scope `agent-runs:read` / `agent-runs:write`; ownership via conversation
(owner/admin), someone else's resource 404.

| Method | Path | Effect |
| --- | --- | --- |
| GET | `/v1/agent-runs` | Last 200 accessible runs |
| GET | `/v1/agent-runs/{id}` | Run metadata |
| POST | `/v1/agent-runs/{id}/cancel` | CAS to `cancelled`, cancel runtime/provider |

`AgentRun`: id, conversation, status, assistant/version, model, timestamp,
`cancel_requested_at`. The events remain in the conversation/SSE.

## Real deletion

1. The gateway runs the CAS DB and marks the run `canceled`.
2. Call `POST /internal/v1/runs/{run_id}/cancel` on the runtime.
3. The runtime reports the `RunStateRegistry`; the cancel-aware wrapper cancels
   agent iteration, closes provider/tool and issues `agent.cancelled`.
4. If the runtime is unavailable, the gateway cancels the active HTTP request;
   the flow synthesizes `agent.cancelled` and persists the terminal.
5. The SSE response ends with `agent.cancelled`; the replay with the same
   idempotency key returns persisted events.

`agent.cancelled` is a public terminal event (`payload.code=cancelled`) and a
lifecycle observation metadata-only. It is not issued for disconnection of the
client without explicit cancel; in that case the stream failure remains.

## Restart and limits

- The `running` run interrupted by restart gateway is marked `failed` by
  `OpenStore` with replayable `gateway_restarted` event; it is not re-executed
  automatically.
- Deletion is cooperative: cannot terminate blocking synchronous code in
  provider/tool. Runtime and gateway share only one process each; the
  registry cancel is in memory and not a distributed protocol.
- `waiting_approval` is allowed by the schema for M4-04; approval is not
  still implemented.
- Tool effects are not repeated by restart: their idempotence is M4-05.

## Evidence

- `apps/gateway/agent_runs_test.go`: list/get/cancel, ownership and 409 terminal.
- `apps/runtime/tests/test_run_state.py`: registry, cancel during stream, exit
  source, cancel before iteration.
- `tests/e2e/check_agent_runs.py`: real slow run, public cancel,
  `agent.cancelled`, DB status `cancelled`, 409 on second cancel and replay
  identical.
- Evidence: `make test` 221 runtime + 8 workers + 3 skipped, Go race/vet;
  `make e2e` 22 checks passed.