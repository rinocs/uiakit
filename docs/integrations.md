# Integrations: SDK, Laravel, widgets and console

The M5 gate validates the same public contract across four surfaces:

- TypeScript, Go and PHP SDK generated/verified by
  `packages/api-contract/public.openapi.json`;
- Laravel server-side integration;
- Web Component chatbot;
- SvelteKit console and server-side SSE proxy.

The readable matrix is in
[`tests/contracts/sdk-matrix.json`](`tests/contracts/sdk-matrix.json`).

## SDK Array

| SDK | Runtime | Command | Contract |
|---|---|---|---|
| TypeScript | Node 20+ / browser | `make test-typescript` | 45 operations, 17 tests |
| Go | Go 1.23+ | `make test-go-sdk` | 45 operations, race/vet |
| PHP | PHP 8.2+ | `make test-php` | 45 operations, 13 tests |

```bash
make test-contracts # Go/TS/PHP unique array against public OpenAPI
make build-packages # build TypeScript/Go/PHP/widget/console
```

Individual SDK tests check for behavior, SSE, errors, idempotency, and
mandatory headers; `test-contracts` checks that no SDK can diverge
silently by the public contract.

## SSE and terminals

All SDKs expose the same model:

- `response.completed` is the only successful outcome;
- `agent.failed` and `agent.cancelled` are terminal and produce typed errors;
- EOF without terminal is an error (`StreamIncompleteError` /
  `StreamIncompleteException`), never a success;
- the idempotency key is explicit;
- abort/cancel interrupts the connection and requests the cancellation of the run.

The console uses a SvelteKit SSE proxy: the browser never receives the API key
administrative, which remains in the server process.

## Laravel

`packages/sdk-php` includes the auto-discovered service provider, configuration
`UAI_BASE_URL`/`UAI_API_KEY`/`UAI_TIMEOUT_MS` and the SSE route example in
`examples/laravel/`. The `LaravelServiceProviderTest` test checks the binding of the
containers; `ClientTest` checks assistant/conversation creation, streaming,
errors and uploads with a mock HTTP gateway. The complete guide is
[laravel.md](laravel.md).

The key remains in the Laravel server-side variables and does not appear in the payload
browser, URL, localStorage or bundle.

## Widgets

`packages/chat-widget` is a framework-agnostic Web Component. Use widget tokens
short, not an admin key. The contract includes:

- Markdown built with DOM nodes, never template HTML;
- link only `http`/`https`/`mailto` with `noopener noreferrer`;
- quotes authorized by the `response.completed` payload, opened via
  callbacks;
- cancel via button/Escape, event deduplication, incomplete/failed states;
- a11y (`role=log`, `aria-live`, focus, keyboard) and responsive theme.

Unforked demo in `examples/widget/` (vanilla, React, Svelte).

## Console and section 16

The console covers the operations required by section 16:

| Operation | Implementation |
|---|---|
| Create assistants | `/assistants` + server action |
| System prompts and templates | assistant detail |
| Directives | validated directive field |
| Knowledge base | `/knowledge-bases` |
| Upload documents | multipart upload, job and status |
| Register HTTP tools | read-only catalog of connectors registered by the deployment; no URLs/arbitrary code from the UI |
| Enable plugins | installed plugins, configuration and health |
| Conversations | history and completed messages |
| Executions and logs | run detail, usage in the playground, audit written |
| Test the chatbot | SSE playground with replay/cancel/quotes |

HTTP tool registration remains **deployment-owned**: the connector, the
destination, headers and secrets are defined in the runtime/allowlist
operational, not from the console. This is the security boundary requested by
“no arbitrary installation of code or URLs via API”; the console allows
to inspect tools, connectors and risks, and to only use already approved tools.## Gate

```bash
make test # contracts + unit Go/Python/TS/Go/Widget/Console/PHP
make build-packages # packages and console builds
make e2e # gateway/PostgreSQL/runtime/RAG/agents + E2E widget
make test-console-browser # Playwright: roles, KB, extensions, run, a11y, CSP
```

`tests/e2e/check_integrations.py` checks on the real gateway:

- mint, binding, widget token expiration/revocation;
- CORS preflight allowed/denied and constrained origin;
- access allowed only to the token conversation;
- credential and mint block with token widget;
- complete SSE message and persisted history;
- immediate revocation with `401`.

The Playwright browser test checks roles, absence of the key from the browser, CSP with
hash (without `unsafe-inline` on scripts), header `X-Frame-Options`/
`X-Content-Type-Options`, no serious/critical ax violations and flows
KB/plugins/approvals/run/playground.

## Known limitations

- Console sessions and rate limit widgets are in memory: single-instance up to
  M6 (distributed store).
- Browser tests require Chromium and system dependencies; CI uses
  `npx playwright install --with-deps chromium`, locally can be run
  the same command or a Playwright container.
- The console does not install plugins/tools: it only configures already installed resources.
## Ready-to-mount chat widgets

Laravel and FastAPI share `packages/chat-widget`; `connectChat` bootstraps it
through the host application's authenticated session endpoint. Laravel provides
a namespaced Blade component and an explicit web route example. The optional
`packages/fastapi` package supplies `create_widget_router` without introducing
a full Python SDK. Both adapters keep administrative credentials on the server,
fix assistant/origin bindings in server configuration, return no-store responses
and sanitize upstream failures. See [Laravel](laravel.md) and [FastAPI](fastapi.md).

```bash
make test-widget test-php test-fastapi
```
