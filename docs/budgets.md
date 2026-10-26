# Execution budget, usage and structured output

## Limits per run

`ExecutionLimits` adds:

| Field | Default | Limit |
| --- | --- | --- |
| `max_steps` | 4 | 0…16; 0 uses the default |
| `max_tool_calls` | 8 | 0…32; 0 uses the default |
| `max_tokens` | 8192 | 0…1,000,000; 0 uses the default |

Values ​​of 0 retain the default for assistants that persisted before M4-07.
`max_input_chars`, `max_output_chars` and `duration_seconds` remain unchanged.
The duration is applied with `asyncio.timeout`; step and tool calls are consumed
before generation or effect. A loop that goes beyond the steps, a tool
storm over limit or token budget exceeded ends with `agent.failed`
(`step_limit`, `tool_call_limit`, `token_limit`) without automatic retries.

## Usage and costs

`UsageAccumulator` aggregates `prompt_tokens`, `completion_tokens` and `total_tokens`
only when the provider reports them as non-negative integers. A generation
without usage does not produce invented zeros: the field is omitted. If the total does not
it is known, the budget uses a conservative estimate `ceil(chars/4)`; the usage
returned remains distinct from the estimate. Zero reported by the provider remains zero.

The cost is only calculated if both rates per million tokens are known
and input/output tokens; otherwise it is `None`. No prices are invented either
deduced from the model name.

## Context window

If `ModelDefinition.context_window` is known, before each generation it is estimated
input (system, messages, tool results, and tool schemas) plus maximum output
(`max_output_tokens` or `max_tokens`). Exceeding produces `context_window`.
Without `context_window` the limit is not simulated; the budgets remain
existing characters.

## Structured output

`structured_output` is allowed if the model declares the capability
`structured_output` (`MODEL_STRUCTURED_OUTPUT=true` in factory). The pattern is
JSON Schema Draft 2020-12, bounded to 16 KiB and validated on creation
of the assistant. The provider receives `response_format: json_schema` and the text
final is however revalidated locally. `OutputValidationDirective` verifies the final text with
`jsonschema==4.26.0`; non-JSON, unfinished, or non-compliant text fails with
`directive_failed` after streaming, without rewriting deltas already issued.

## Guarantees

- Provider retries do not exist: an error after a delta ends the run.
- Budgets do not reintroduce effects: retry tools remain the limited ones
  M4-05 is read-only.
- Approval waits do not consume tokens; the weather remains covered by
  run timeout.
- Test: `apps/runtime/tests/test_execution_limits.py`.