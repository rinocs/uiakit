# API overview

The public API is versioned under `/v1` and documented by the OpenAPI contract in
`packages/api-contract/public.openapi.json`. All authenticated requests use a
bearer key.

```http
Authorization: Bearer <api-key>
Content-Type: application/json
```

`GET /v1/health` is public. `GET /v1/me` returns the effective role and scopes.

## API groups

| Group | Endpoints |
|---|---|
| Health/identity | `GET /v1/health`, `GET /v1/me` |
| Assistants | `GET/POST /v1/assistants`, `GET/PATCH /v1/assistants/{id}`, `GET /v1/assistants/{id}/versions` |
| Models | `GET /v1/models` |
| Conversations | `POST /v1/conversations`, `DELETE /v1/conversations/{id}` |
| Messages/SSE | `GET/POST /v1/conversations/{id}/messages` |
| Runs | `GET /v1/agent-runs`, `GET /v1/agent-runs/{id}`, `POST /v1/agent-runs/{id}/cancel` |
| Credentials | `GET/POST /v1/credentials`, `POST /v1/credentials/{id}/rotate`, `POST /v1/credentials/{id}/revoke` |
| Knowledge bases | `GET/POST /v1/knowledge-bases`, `GET/PATCH/DELETE /v1/knowledge-bases/{id}`, versions, export |
| Documents/jobs | `GET/POST /v1/documents`, `GET/DELETE /v1/documents/{id}`, job status/cancel |
| Tools | `GET /v1/tools` |
| Approvals | `GET /v1/approvals`, `GET /v1/approvals/{id}`, approve/reject |
| Plugins | `GET /v1/plugins`, `PUT/DELETE /v1/plugins/{id}`, health |
| Audit | `GET /v1/audit-events` |
| Widget tokens | `POST /v1/widget/tokens`, `DELETE /v1/widget/tokens/{id}` |

The OpenAPI file is authoritative for request/response schemas and required
headers. The TypeScript, Go and PHP SDKs are checked against the same contract.

## Creating an assistant

```bash
curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Support assistant",
    "model": "llama3.2:3b",
    "system_prompt": "Answer clearly and cite sources."
  }'
```

Required fields are `name`, `model` and `system_prompt`. Optional fields include
`description`, `knowledge_base_ids`, `directives`, `memory`, `limits` and
`policy`. Updates require `If-Match` with the current revision and create an
immutable version.

## SSE contract

`POST /v1/conversations/{id}/messages` requires an `Idempotency-Key` and returns
`text/event-stream`:

```text
id: <event-id>
event: response.delta
data: {"event_id":"...","event_type":"response.delta","event_version":1,...}

id: <event-id>
event: response.completed
data: {"event_id":"...","event_type":"response.completed","event_version":1,...}
```

Event types:

| Type | Meaning |
|---|---|
| `agent.started` | Run accepted; first event |
| `response.delta` | Incremental assistant text |
| `response.completed` | Success; final text and optional citations/usage |
| `agent.failed` | Terminal failure with a stable code |
| `agent.cancelled` | Terminal cancellation |

An EOF without a terminal event is **not** success. Reusing the same
`Idempotency-Key` and content replays the persisted events; a different body or an
active run returns `409`. The gateway persists the terminal state before exposing
success.

## Cancellation

```bash
curl -X POST "$UAI_BASE_URL/v1/agent-runs/<run-id>/cancel" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

The run becomes `cancelled`, the runtime closes the provider/tool resources and
the stream emits `agent.cancelled`. A second cancel is a conflict.

## Errors

Non-2xx responses use a stable JSON code:

```json
{"error":"invalid_id_or_idempotency_key"}
```

| Status | Typical cause |
|---|---|
| 401 | Missing/invalid/revoked credential or wrong bootstrap key |
| 403 | Authenticated but missing scope/ownership/origin |
| 404 | Resource not found or not visible to the principal |
| 409 | Idempotency conflict or invalid state transition |
| 412 | Stale `If-Match` revision |
| 422 | Invalid body, ID, configuration or capability |
| 429 | Installation/principal/widget rate limit |
| 502/503 | Runtime, provider or storage unavailable |

Branch on the stable `error`/event code, not on provider text. Retry only
transient failures and reuse the same idempotency key.

## Limits

Default limits include 120 requests/min per process and per principal, 128 KiB
JSON body, 32,000-byte message, 64,000-byte context/output, 100 history messages,
120 s run duration and 30 s provider timeout. See
[configuration](configuration.md) and [capacity](capacity.md).

## Examples and SDKs

- [Examples](examples.md) — curl, TypeScript, Go and PHP.
- [SDK integration](integrations.md) — contract matrix and package links.
- [Authentication](auth.md) — roles, scopes and credentials.
