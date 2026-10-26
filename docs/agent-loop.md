# Agent loop with tool calling

`BasicAgent` remains the text profile and rejects tool assistants. When the
assistant version select tool, the runtime uses `ToolCallingAgent`
(`uai_runtime.tool_loop`) and requires the model's `tool_calling` capability.
In `from_env` the capability is enabled with `MODEL_TOOL_CALLING=true`; without of
it a run with tool ends with 422 `tool_calling_unsupported`.

## Authorization and providers

The gateway sends `allowed_tool_ids` only if the principal has `tools:execute`:
are the IDs selected in the assistant version. The runtime still intersects:

- tools selected in the assistant version;
- `authority.allowed_tool_ids`;
- permissions declared against `authority.scopes`;
- effective registry, connector allowlist and `ToolPolicyDirective` policy.

Only `read_only` tools with `builtin`/`http` executors are offered to the model
at this stage. The mutant tools stay out of the loop until M4-10 connects
approval and resumption of the run; they are never performed for a simple
model request.

The provider receives `tools` with native schema input and messages. The deltas
OpenAI-compatible adapter `tool_calls` are accumulated by index:
`id`, name and JSON fragments. JSON is executed only after complete stream,
parse strict in object and verify authorized name. partial JSON,
malformed, unfinished or an unknown tool produces `agent.failed` without
invoke the executor.

## Cycle

1. `before_model` and constructing provider messages.
2. Streaming generation; textual deltas remain SSE `response.delta`.
3. If there is no tool call, the response is terminal.
4. Otherwise add the assistant message with `tool_calls`, execute i
   authorized tools and add results with `tool` role.
5. New generation, up to 4 steps and 8 tool calls overall.

The result of a tool is inert data: it is never inserted as a system prompt
and the model cannot gain privileges from its content. Policy errors,
input/output schema or executor fail closed with `agent.failed` and code
normalized.

If `GATEWAY_URL` is configured, each tool goes through `DurableToolRunner` and the
M4-05 reservation: replays of completed runs, limited read-only retries and
`unknown` for uncertain effects. Without journal (test or standalone runtime) the loop
can only do read-only in-process.

## Test

`apps/runtime/tests/test_agent_loop.py` covers direct response, tool call →
result → new generation, partial/malformed JSON, unknown tool, result
not privileged, missing capability and executor failure.
`tests/test_provider.py` covers the accumulation of delta tools.

Step, tool call, token and context window are limited by `RunBudget`; usage e
structured outputs are described in [budgets.md](budgets.md).

The full E2E gate (real read-only, approval and mutant replay) is in
[agents.md](agents.md).