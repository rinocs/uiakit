# Directive pipeline — runtime integration

The core exposes `Directive`, `DirectiveRegistry` and `DirectivePipeline`. The runtime
receives a registry via `create_app(..., directive_registry=registry)` or
`from_env(directive_registry=registry)` in a trusted deployment factory;
this is trusted Python composition, not an installation endpoint.

Each directive declares its name, priority, dependencies, timeout in seconds, and policy
`fail` (default) or `continue`. The registry rejects duplicates; `build(selected)`
reject unknown names, unselected dependencies, and loops. Addictions
precede the priority; host guards always come after all middleware.
Among the ready nodes, the numerically lowest priority wins,
then the name. Dependencies are not implicitly enabled.

The selection is acquired per run by the assistant version. The host registry
always adds directives registered with `mandatory=True`; does not expose API's
removal or replacement. An already built pipeline does not change when the
register receives new directives. Instances are shared: run state must
live in ExecutionContext/WorkingMemory, not on directive attributes.

`before_model` can return `context.with_messages(...)`. Every return comes
rebuilt and validated, even if the plugin uses `model_copy(update=...)`.
Identity, authority, limits, assistant/version, model metadata, model,
prompt, initial authorized history and working memory identity must
remain unchanged. The budget of
input is rechecked before the provider. Validation errors break
always run, even for directives with `continue` policies.

`after_model` receives `context.model_output` without adding messages to the input:
even a history of 100 messages continues to work. This phase is valid
the outcome; it cannot rewrite output or messages. SSE deltas can already be
been delivered: a rejection produces `agent.failed`, never `response.completed`.
It is therefore not a filter that hides output before delivery.

Timeouts and failures of mandatory directives produce `directive_failed`.
The `continue` policy preserves the previous context after an ordinary error;
does not cancel any writes already made in the working memory. The logs
contain name/phase, not exception text. The overall timeout includes
both phases. The cancellation propagates to the caller; the runtime cleans the
working memory. Asyncio timeouts are cooperative: plugins that block the
thread or suppress deletion require process isolation, not offered
here. No hostile Python sandbox is declared.

## Status and compatibility

The gateway accepts `directives` in POST/PATCH servers: maximum 64 names
unique, format `[a-z][a-z0-9_.-]{0,99}`. The names indicate components already registered
from the host; they do not identify modules or code to import. The standard deployment
registers five mandatory [built-in guards](builtin-directives.md) and rejects
any unknown name.
A trusted factory can register deployments through the core contract.

Before saving a version with non-empty selection, the gateway sends
`POST /internal/v1/directives/validate` with `{"directives":["name"]}` and Bearer
internal. The runtime builds the pipeline without executing callbacks and returns
204, or 422 for invalid names/duplicates/graphs. The gateway normalizes the second
case to `invalid_configuration`. Network errors, service authentication,
redirect and other responses produce 503 `runtime_unavailable`; no version
is saved. The request has a limit of 5 seconds, without retry or redirect.
No details of private responses are propagated to the client.

An empty list disables optional directives and requires no validation
remote: Mandatory host directives are still preflighted
every run. PATCH replaces the entire list and creates a new version. The replay
uses the original events and does not invoke directives or providers. The register comes
checked again at the start of each new run: if the deployment has changed since
validation, the run fails without calling the provider. The snapshot includes the
selection, not a copy of the Python code; the distribution of implementations
the responsibility of the trusted deployment remains. Update the runtime first, then the
gateway. No additional SQL migrations are required.Built-ins and observation hooks are implemented (M2-06/M2-05); the loader plugin
stays in M2-09. Guards use register_guard and validate the final context
without modifying it. Don't depend on a guard in a middleware: it would introduce
one loop and the configuration would fail.

Local testing: `apps/runtime/tests/test_directives.py` e
`apps/gateway/directives_test.go`, including sorting, negative configurations,
escalation, error policy, cancellation, authenticated calls and SSE integration
through ASGI. `tests/e2e/check_directives.py` covers PostgreSQL, version,
after-model activation/deactivation, replay and rejection: included in `make e2e`,
run with real Docker/PostgreSQL. The factory with test prefix is mounted
only from the E2E override, without changing the production deployment.