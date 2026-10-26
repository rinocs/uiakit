# Tool and executor registry

The runtime uses only one ToolRegistry per deployment-approved catalog and callable.
ToolDefinition in core exposes id, name, description, version, input_schema,
output_schema, permissions, risk_level, timeout, retry_policy and executor. The
callable and module paths are not serialized in the catalog.

The current profile allows `builtin`, `http` and `isolated` (external HTTP plugin) executors;
`mcp` is the contract
reserved for the next phase. Tool calling is described in
[agent-loop.md](agent-loop.md); limits, usage and structured output in
[budgets.md](budgets.md). The retry_policy remains `never`. The categories of
risk are read_only, write and destructive; the executor only executes read_only.
Write/destructive ends with approval_required, without calling the code: there is no
public flag or template string that simulates human approval. Durable approvals are tied to run, tool/version, canonical digest, and policy
snapshot ([approvals.md](approvals.md)); executions with effects are reserved
with an idempotent key and reconcilable `unknown` state
([tool-executions.md](tool-executions.md)). HTTP tools use connectors
administrative, not template URL; SSRF details and policies in
[http-tools.md](http-tools.md) and [plugins.md](plugins.md).

## Registration and patterns

The deployment passes a ToolDefinition, two Pydantic BaseModel classes to the registry
input/output with extra=forbid and an async def handler. The patterns must match
exactly to model_json_schema of the two models; inconsistencies, synchronous handlers e
Duplicate IDs are rejected. Additional Python validations of the models are
trusted host code; you do not install validators or code from the template.

This is the supported form of schema validation for the built-in profile: not
There is no arbitrary JSON Schema interpreter nor resolution of remote $refs. Models
Python and custom serializer are part of the deployment approved code. Inputs
extras and coercions not allowed by the strict model are rejected. The result
it is reconstructed from plain data and revalidated even if the handler returns
an instance built via model_copy without validation.

Maximum 64 tools per registry and 8 KiB UTF-8 per descriptor. The catalog schemes
they are JSON snapshots separated from the caller's dicts. Edit a descriptor
returned does not modify registry, handler or policy. An ID identifies a version
for deployment; the future loader will have to manage compatibility and updates.

## Initial tool

`builtin.text_stats`, version 1.0.0, requires tools:execute. Accept an item
with `text` string, maximum 32000 characters, and returns characters, words and lines.
Counts Unicode code points, words according to str.split, and lines according to str.splitlines;
empty text has three zero counters. It does not use model, eval, shell, network or files.
All text, including strings that look like code, remains inert data.

The implementation lives in uai_core.builtin.tools and is deployed from the wheel
core already installed in the runtime. A custom register passed to the factory replaces it
the host catalog; the factory does not install packages or import from HTTP metadata.

## Trusted invocation

ToolExecutor runs the following path:

1. Observe tool.requested with normalized ID only.
2. Resolve definition from registry and apply `ToolPolicyDirective`: requires
   tools:execute, all permissions declared and the exact ID in
   authority.allowed_tool_ids. No implied wildcards. If there is a snapshot
   assistant, his tools selection must also include the ID. The permissions
   `connector:<id>` also requires the ID in the host allowlist (empty by default).
   No authority objects within the arguments grant permissions.
3. The policy denies risks with side effects (approval_required); observe
   tool.authorized.
4. Verify finished JSON data, strict schema and budget input, even after normalization.
5. Reevaluate the same policy immediately before the effect: a revoked grant
   during a wait it does not start the handler. Look at tool.started, invoke once and
   apply timeout.
6. Validate result, JSON and budget even after normalization; returns detached data.
7. View tool.completed and record metadata. Every failure produces tool.failed
   and normalized code, without private exceptions or logs.The policy only reads caller authority, assistant snapshot, definition
registered and allowlist connector. Prompt, retrieved text, tool output or
Plugin registrations cannot add scope or grants; a plugin definition
that requires permissions not granted fails before any effect. The policy
is mandatory in the BasicAgent and is reevaluated by the executor before each
invocation, so integration with human approvals and expectations cannot be reused
an obsolete permission. For connector tools the `connector:<id>` permission
  is a statement checked against the host allowlist; remain mandatory
  `tools:execute`, the principal grant and the server selection.

The allowlist connector is injected by the host (`ToolPolicyDirective(allowed_connectors=...)`);
the runtime factory reads `TOOL_ALLOWED_CONNECTORS` as a CSV list and empty part.
A tool with `connector:<id>` permission therefore remains denied until deployment
does not explicitly approve that ID.

Authorization precedes parameter parsing, to deny requests immediately
without grants. The maximum size for input/output is 128 KiB UTF-8 and the
context character limit, applied to JSON. The handler timeout is
minimum between its timeout (maximum 120 seconds) and the context's duration_seconds.
The limits apply to a single call; they are not aggregate quotas or token budgeting
of the future agent loop.

Canceling the task clears the handler, registers tool.failed/cancelled and propagates
CancelledError. There are no automatic retries. Timeout and asyncio cancellation
are cooperative: trusted code that blocks the thread or suppresses deletion
requires process isolation, which is not offered by this profile.

Logs and hooks are metadata-only. Observational callbacks reuse HookRegistry, with
Immutable snapshots and notification budgets per standalone single invocation. Not
they are PostgreSQL transactional audits or durable receipts for external effects.

A Python host can use the factory executor, which shares the registry
catalogue:

```python
result = await app.state.tool_executor.execute(
    authorized_context, 'builtin.text_stats', {'text': 'hello world'}
)
```

The context must be produced by a trusted caller with scope and grant
explicit; the plugin receives only the validated parameters, not the ExecutionContext.
This Python API is not an execution HTTP endpoint.

## API and scope

GET /v1/tools requires tools:read. The gateway queries GET /internal/v1/tools with
Internal bearer, 5 second deadline, no redirects and JSON response limited to 1 MiB.
Check descriptors, duplicates and unknown fields before replying. A runtime
unavailable or an invalid catalog produces 503 runtime_unavailable; they don't come
forward private details. No SQL copy of the catalog or additional migration.

Reader, operator and admin can receive tools:read. Only operator/admin can
receive tools:execute. Explicit scopes are always needed in addition to the role. Existing persisted credentials do not automatically receive new scopes. The
key bootstrap uses updated admin privileges.

BasicAgent remains a textual profile: non-empty assistant.tools and tool call del
providers are still rejected. The gateway still passes empty allowed_tool_ids
in model runs. ToolPolicyDirective remains deny-by-default for that path.
Trusted standalone execution uses the M4-02 policy but does not enable tool calling or
approval in model; the relevant integration is in M4-06. Update runtime first
of the gateway to make the new catalog available.

## Check

Local suites: test_tool_registry.py, test_contract.py and tools_test.go; they cover
logging, patterns and hostile data, grant/scope, limits after normalization,
errors/deletion/timeout, single invocation and catalog without secrets.
The run_tools.py fixture was executed locally without calling the provider.make e2e includes check_tools.py on the public catalog and an SDK call inside the
container runtime, with tool events in the test metadata sink. Docker/PostgreSQL
real ones have been verified with `make e2e`.