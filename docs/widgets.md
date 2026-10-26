# Tokens and CORS widget

Browser widgets do not need to use an administrative API key. The gateway issues
temporary tokens, linked to an assistant, a conversation, a subject and a
origin, with message scope only.

## Configuration

```dotenv
# Exact origins, comma separated. Empty disables mint and CORS widgets.
UAI_WIDGET_ORIGINS=https://example.com,https://support.example.com
# Dedicated budget per token, per minute.
UAI_WIDGET_RATE_LIMIT=60
```

`UAI_WIDGET_ORIGINS` is an exact allowlist: schema and host/port, no path,
query or fragment. `http://` is only allowed for local development.

## Mint server-side

Requires `widget-tokens:write` scope (operator/admin). The request starts from
backend, never from the browser:

```bash
curl -sS http://localhost:8080/v1/widget/tokens \
  -H "Authorization: Bearer $UAI_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "…",
    "conversation_id": "…",
    "subject": "web-session-123",
    "origin": "https://example.com",
    "expires_in_seconds": 900
  }'
```

Response `201`:

```json
{
  "token": "uai_widget_…",
  "id": "...",
  "assistant_id": "…",
  "conversation_id": "…",
  "subject": "web-session-123",
  "scopes": ["messages:read", "messages:write"],
  "origin": "https://example.com",
  "expires_at": "2026-10-25T18:00:00Z",
  "created_at": "2026-10-25T17:45:00Z",
  "created_by": "operator-1"
}
```

The token is returned only once; the database only stores SHA-256. The
default expiry is 15 minutes, minimum 60 seconds, maximum 24 hours. The
conversation must belong to the assistant and the principal requesting the
token.

## Use from browser

The widget uses the token as a bearer:

```http
Authorization: Bearer uai_widget_…
Origin: https://example.com
```

Only:

- `GET /v1/conversations/{conversation_id}/messages`
- `POST /v1/conversations/{conversation_id}/messages`

The conversation must match the binding and the `Origin` must match
the registered one. Credentials, assistants, plugins, configuration, KB, tools and
run are not reachable: the `widget` role only has `messages:read` and
`messages:write`.

## CORS

The `OPTIONS` preflight on message routes responds `204` for one source only
in allowlist, with:

```http
Access-Control-Allow-Origin: https://example.com
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, Idempotency-Key
Access-Control-Max-Age: 600
Vary: Origin
```

An origin not in the allowlist receives `403 origin_forbidden` and no CORS header.
Preflight does not authenticate: the allowlist is the barrier; the actual request
also checks the token binding.

## Revocation and rate limits

```bash
curl -sS -X DELETE http://localhost:8080/v1/widget/tokens/$TOKEN_ID \
  -H "Authorization: Bearer $UAI_ADMIN_KEY"
```

Revocation is immediate (`401` on subsequent requests). Each token has a budget
dedicated `UAI_WIDGET_RATE_LIMIT` per minute, separate from global limit; beyond the
threshold the gateway responds `429` with `Retry-After: 60`.

## Safety notes

- Never enter `UAI_ADMIN_KEY`, `UAI_API_KEY_SHA256` or `INTERNAL_API_KEY`
  in the browser bundle.
- The widget token is a secret: keep it in session memory, not in URL,
  logs or analytics.
- Rotate/revoke token when browser session ends; the deadline
  short limits exposure.
- The token cannot create other tokens (`widget-tokens:write` is not in the role
  `widgets`).