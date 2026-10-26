# Initial built-in directives

The runtime installs five mandatory guards in each BasicAgent, even when
the factory receives a custom register. They are distributed in the uai-core in wheel
`uai_core.builtin.directives`, without a plugin package or additional DB path.

| Registered Name | Implementation | Behavior |
| --- | --- | --- |
| builtin.system_prompt | SystemPromptDirective | Check the prompt against the assistant snapshot; he doesn't rewrite it. |
| builtin.conversation_memory | ConversationMemoryDirective | It only admits history authorized by the gateway, even after middleware. |
| builtin.tool_policy | ToolPolicyDirective | Requires active approval; BasicAgent remains text-only, while ToolCallingAgent uses the same object to intersect scope, grant, assistant snapshot, registry and connector policy. |
| builtin.output_validation | OutputValidationDirective | Requires non-empty, non-whitespace textual output and within budget. |
| builtin.observability | ObservabilityDirective | Record counts and correlation at INFO level, without prompts/text/history/credentials. |

The `directives` configuration selects optional components. The built-in names
they can appear explicitly, but omitting them or using `[]` does not disable them.
A custom register that attempts to occupy one of the five names causes the
factory. Installing the same built-in objects into the registry multiple times is safe;
Subsequent host registrations remain visible on future runs.

## Final guards

`DirectiveRegistry.register_guard(directive)` registers a host validator
mandatory. The graph construction adds implicit dependencies on all the
middleware to guards. Also a numerically very prioritized middleware
alta is then executed before the guards. Among guards they still apply
explicit dependencies, priority and name. A middleware that depends on a guard
creates a loop and is rejected in configuration.

Guards cannot transform messages, beyond the fields already protected by the
pipeline. It is not enough to call `register(..., mandatory=True)` to get it
this semantics: that remains a mandatory, possibly mutant middleware.
Policy guards must use register_guard. These constraints close the case
in which a middleware adds extraneous history after the security check.
Trusted Python code remains code in the process, without a hostile sandbox.

## Provenance of history

ExecutionContext acquires `authorized_history` from the run's initial messages,
excluding the last user message. It is an immutable tuple of Message and falls within the
pipeline protected fields; with_messages/with_output preserve it.
ConversationMemoryDirective allows the original history or a suffix thereof
to allow trimming. It does not allow additions, reordering or editing of messages
historians. The last message must remain user role; middleware can
transform its content, without expanding privileges.

With memory.conversation=false the history must be empty. The flag does not delete
persisted messages. Ownership checks, PostgreSQL reading and commit
of shifts remain in the gateway's existing paths: the guard does not simulate
retrieval, write, or retention, and does not emit dummy memory.read/write events.

The Python MemoryProvider contract exists; the mutant/retention adapter comes
linked back to M6-01 with cancellation policies. This updates the previous one
reference to M2-06 recorded in ADR 0010, without introducing no-op writes or a second
DB access from runtime. Semantic memory remains disabled.

## Output, tools and observability

OutputValidationDirective is a textual validation of the current profile, not
a structured output validator: the latter remains rejected in configuration
up to M4-07. Space-only output now ends with agent.failed/directive_failed.
Deltas already delivered cannot be collected; completed is not output.
Replays of old runs maintain the original events without revalidation.ToolPolicyDirective does not enable tool calling in the BasicAgent: BasicAgent
reject snapshot with tool and the adapter provider remains textual. `ToolCallingAgent`
use the same policy for snapshots with authorized tools. The same object is the policy
standalone executor mandatory: requires intersection between
`authority.allowed_tool_ids`, scope of principal, tools selected in
assistant version, registered definition and allowlist connector. The policy
it is re-evaluated after the validation of the arguments and immediately before
of the effect, so a grant revoked while waiting for approvals cannot
run the tool. Prompts, documents, tool output and plugins do not change
these data. No generated code executed.

ObservabilityDirective uses standard logging and counters/UUIDs only. It doesn't add
duplicate subscribers or new SSE events; the M2-05 lifecycle metadata remains the
observation contract. The RAG directive will arrive in M3-11 with real retrieval.

## Check

`test_builtin_directives.py` covers the five components, history snapshot,
authorized trimming, escalation attempts, end guards, name collisions,
reused registers and HTTP integration. Existing test cores remain in the suite.

`check_builtins.py`, included in make e2e, check public selection, output
whitespace with empty list, plugin attempting extraneous history and replay failed.
The mock provider fixture and whitespace case only exist in Docker tests.
The Docker/PostgreSQL gate was verified with `make e2e` on 2026-10-23.
No SQL migration or new dependencies needed.