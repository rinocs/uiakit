# Agents with calling tools and effects

## Read-only path

`ToolCallingAgent` exposes only `read_only` tools with executor to the model
`builtin`/`http`, after the intersection of assistant selection, grant del
principal, `tools:execute`, and allowlist connector of the host. The model produces
OpenAI-compatible tool call; a partial or malformed JSON never comes
executed. The tool result is returned as an inert `tool` message, not as
privileged education.

Each read-only execution passes through `ToolPolicyDirective`, input/output schema,
`RunBudget`, `DurableToolRunner` and journal gateway. Retry for codes only
read-only allowed; results and digests are bounded. Public SSE always terminates
with `response.completed`, `agent.failed` or `agent.cancelled`.

## Mutant effects and approval

A `write`/`destructive` tool is never executed from the loop until a `write`/`destructive` tool exists
Immutable approval binding. The route is:

authorization → digest topics → approval pending → human decision →
atomic consumption in reservation → HTTP executor → output validation →
audit → result.

`run.sh`/`check_approvals.py` cover approval, rejection, expiration and resumption
of the run. `check_tool_executions.py` covers replay, retry read-only, status
`unknown` and reconciliation. The M4-10 mutant gate performs a real HTTP POST
against `mock_tool.py` with an already approved approval and exact binding:
the second call with the same idempotent key returns the result
recorded without a second effect; the approval is `consumed`, the line
`tool_executions` is `completed`, audit contains tool/digest/run.

## What the E2E gate checks

`tests/e2e/check_agents.py`, run in the runtime container:

- real read-only tool `mocktool.read` → `mock_tool` is reached once,
  `response.completed` and audit `tool_execution.completed`;
- model tries `mocktool.write` unchecked → `agent.failed` with
  `tool_not_authorized`, server not reached;
- two tool calls with `max_tool_calls=1` → `tool_call_limit` before the effects;
- effective assistant limits (`max_steps`, `max_tool_calls`, `max_tokens`);
- SSE single terminal and readable audit without secrets.

`tests/e2e/run_mutating_tool.py` does real POST with journal gateway and
check replay without duplicate. `tests/e2e/check_agent_runs.py` checks the
SSE cancellation and replay. SQL assertions in `run.sh` link run,
consumed approval, `tool_executions` and `audit_events`.

## Current limits

The agent loop exposes only read-only tools to the model. Creation
automatic approval and loop resumption after a human decision
remain explicit in the administrative/gateway path; gate M4-10 validates the
binding, consumption and the real effect without introducing a model→effect channel
not approved. Approvals and effects remain confined by the journal and
from transactional audit.