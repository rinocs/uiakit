# Admin console

The SvelteKit console in `apps/console` covers the first block of section 16
of the specification: administrative access, assistants/versions, system prompt,
models, directives and actual roles.

## Access

1. Open `/login`.
2. Enter an `admin`, `operator` or `reader` API key.
3. The console calls `GET /v1/me` on the gateway and creates an opaque session
   server-side. Widget tokens are rejected.

The key remains in the memory of the SvelteKit process; the cookie contains only a
Random ID. It is never placed in HTML, localStorage, sessionStorage, or URL.

## Roles

- `admin`: all console operations.
- `operator`: write assistants/models, without credentials, audit or provider configuration.
- `reader`: read only; edit forms are disabled/hidden.
- `widget`: access denied.

Loads and actions use the server-side client SDK with the session key; not
there is a proxy browser that receives the key. The API remains the final authority: a
missing UI control does not grant scope.

## Available functions

- Dashboard with counts.
- Assistant list and creation.
- Assistant detail: name, model, system prompt, directives and versions.
  Each save creates a new version with `If-Match`; a conflict of
  version is shown without overwriting.
- Public model catalog.
- Provider configuration for admins: provider kind, base URL, secret reference,
  max output tokens and the model catalog used by assistants. Model discovery
  queries the provider through the runtime; secrets are never stored or shown.
- Credential management for admins: list, create, rotate and revoke. The new
  key is shown once in the action response and never in the URL; role and scopes
  remain validated by the gateway, and the current credential cannot be rotated
  or revoked.
- Audit log for admins with action, run and target filters plus a bounded limit.
- Gateway health and version on the dashboard.

Also available are KB/documents (upload, job, reindex, export, source),
read-only tools, installed plugins, and immutable binding approvals.
Conversations, runs and playgrounds with SSE/cancel/quotes are available in
M5-09; the playground uses a server-side SSE proxy and does not expose the key.

## Deployment

`deploy/docker/console.Dockerfile` builds the Node adapter; the service
`console` in `compose.yaml` uses `UAI_GATEWAY_URL=http://gateway:8080`,
`ORIGIN` (required for SvelteKit CSRF protection) e
`BODY_SIZE_LIMIT=24M` for document uploads up to 20 MiB. Set
`CONSOLE_ORIGIN` to the public URL of the console.

Sessions are in memory: only one instance is supported until M6
introduces a shared store. The container is read-only, non-root and with
`cap_drop:ALL`.

## Test

```bash
make test-console # svelte-check, unit test session, build
make test-console-browser # Playwright (Chromium)
```

The browser tests verify assistant creation/version, absence of the key
in the browser, reader role and rejection of widget tokens.