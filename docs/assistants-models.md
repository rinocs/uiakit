# Versioned assistants and model catalog
## Source of configurations

The runtime describes its adapter via the protected `/internal/v1/models`
with the service bearer. At startup the gateway imports the description into PostgreSQL
before opening the public door; no model calls are necessary.
`GET /v1/models` requires `models:read` and returns only id, provider, capability,
max_output_tokens and context_window. URL, secret value and secret reference are not
public. The current adapter exposes OpenAI-compatible chat/streaming; the others
capabilities are absent until the respective adapter implements them.

The model is selected via MODEL_NAME, MODEL_BASE_URL and MODEL_API_KEY already
existing. Only one active, usable backend per runtime is supported at this stage
by multiple assistants. Capabilities are properties of the configured adapter, not one
certification of the remote model: if it refuses streaming/tool, the error is
normalized. Unknown context window is null, not a made up capability;
token-aware budget and additional models belong to M3-07/M4-07.
`configs/models/example.json` is format documentation, not an uploaded file
implicitly; changing an example file does not change the active provider.

## Assistant API

- `POST /v1/assistants`: initial configuration, without id/version/owner_id.
  Keep the minimal body M1: name, model, system_prompt.
- `GET /v1/assistants`: accessible current configurations.
- `GET /v1/assistants/{id}`: current configuration and `ETag: "N"`.
- `GET /v1/assistants/{id}/versions`: all accessible versions, sorted.
- `PATCH /v1/assistants/{id}`: Partial update with `If-Match: "N"`.
  Without header: 428. Version outdated: 412. Unknown fields, null, id/version
  client-side or feature unavailable: 422. Nested objects preserve fields
  omitted; array replaced entirely. Each accepted PATCH creates N+1, even if the
  resulting value coincides. No in-place changes to previous versions.

Scope: assistants:read for reads/versions, assistants:write for creation/PATCH.
Ownership also applies to version history: other people's resource is 404. `models:read`
it's a new explicit scope: existing credentials don't acquire it on their own.

Example, with ID and credential already available:

```bash
curl -s "http://localhost:8080/v1/assistants/$ASSISTANT_ID" \
  -H "Authorization: Bearer $UAI_API_KEY"
curl -s -X PATCH "http://localhost:8080/v1/assistants/$ASSISTANT_ID" \
  -H "Authorization: Bearer $UAI_API_KEY" -H 'Content-Type: application/json' \
  -H 'If-Match: "1"' -d '{"description":"Updated","limits":{"max_output_chars":1000}}'
```

## Snapshot per run

Under transactional lock the gateway sets assistant_id/version, configuration
complete and model description in agent_runs before invoking Python. PATCH
does not modify the snapshot of an already created run. The lock on the head precedes the reading
version: two PATCHES of the same version produce a hit and a 412.
The gateway releases the locks before the HTTP call to the provider.

The runtime receives immutable snapshots and verifies that top-level template/prompt v1
coincide. The model description must match that of the runtime
active; a changed configuration is rejected, not executed with new ones
parameters silently. We keep the top-level fields for v1 compatibility.
Version limits can reduce global runtime limits, never increase them.
The gateway applies a conservative input budget in bytes, the runtime in characters.

The public stream includes X-Run-ID and X-Assistant-Version. Retry with the same
Idempotency-Key rereads snapshots and original events, even if the assistant has been
updated in the meantime. A new turn uses the current version.## Fields and future activations

The configuration includes descriptions, directives, tools, skills,
knowledge_base_ids, memory, limits and policy. `directives` accepts registered names
in the trusted runtime, validate before saving the version: see
[directives contract](directives.md). The five built-in guards remain active
even with empty directives. Other extension lists remain empty,
semantic memory remains false and require_tool_approval remains true.
Structured output, tool, skill and RAG cannot be activated until their respective ones are missing
task: the server replies 422, without pretending to have applied the configuration.

`memory.conversation=false` omits history from the model input of new runs. Le
interactions remain persistent and visible in the API history for audits; this flag
it is not equivalent to data retention/deletion. The cancellation policy remains M6-01.
`configs/assistants/default.json` is a POST example, without ID/version/credentials.

## Migration and checks

003 creates assistant_versions and model_configurations and assigns version 1 to the data
existing without deleting them. A trigger prevents UPDATE of versions; every new one
run references the exact version with FK and keeps the JSON. Old runs are backfilled to the initial version; historical model_snapshot remains null, because
you don't invent past metadata providers. The replay does not invoke the model.

Local unit tests check PATCH/ETag, prohibited fields, shared Go/Python fixture,
capabilities, immutable snapshots, and limits. Real scenarios are in
`tests/e2e/check_versions.py`, called by `make e2e`: model, versions, replay,
If-Match concurrency and memory disabled. PostgreSQL migration and lock were
verified with `make e2e`; tests with in-memory stores remain complementary.

Upgrade order: runtime before the gateway, because the new gateway requires the
catalog endpoint. The new runtime still accepts v1 requests without snapshots.
After 003 migration, a legacy gateway rejects the future scheme: do not bypass
control. Full rollback requires compatible backup/restore (M6-08 runbook).

## Embedding

Embedding templates have a separate contract in
[embeddings.md](embeddings.md): Ollama or OpenAI-compatible provider, size,
stable version and `index_version`. The chat catalog `/v1/models` remains limited
to models with chat/streaming capabilities; an embedding is not selected as
assistant model. Ollama native chat is selectable with
`MODEL_PROVIDER=ollama`; the default remains OpenAI-compatible.