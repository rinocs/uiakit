# Widget integrations implementation plan

**Goal:** Mount the existing chat UI safely in Laravel and FastAPI applications.
**Spec:** docs/superpowers/specs/2026-10-26-widget-integrations-design.md
**Architecture:** Existing Web Component/SSE SDK; shared connectChat helper; server-side conversation and scoped token minting.

- [x] Shared browser helper: write failure/credential-isolation tests, implement same-origin session bootstrap, run widget check.
- [x] Laravel: extend existing provider/config, add controller and Blade view, executable frontend and route examples, targeted tests/docs.
- [x] FastAPI: add small installable router package requiring host auth dependency, no-store session response, validation/error tests and runnable example/docs.
- [x] Integrate docs/build/test entrypoints; review security boundaries and run focused verification across all three surfaces.

Invariants: no administrative key in browser; no client-selected assistants/conversations; exact-origin POST checks; authenticated subject; bounded TTL; sanitized errors; no new chat implementation; no Django/Flask.

## Verification
- Shared helper: observed missing-module failure before implementation; 4 direct bootstrap tests pass. Existing widget check (typecheck, tests, build) passes.
- FastAPI: 29 router tests pass; wheel built and imported from an isolated /tmp installation. Real authenticated FastAPI repository example verified in Chromium with a local fake gateway: static asset imports, session minting, scoped-token SSE response, foreign-origin rejection and no server-key exposure all pass.
- Laravel: 20 tests / 245 assertions pass. Added a regression for dotenv-only $_ENV/$_SERVER values; observed empty origin before the fix and a passing test afterward. Configuration remains compatible with process env without adding optional Laravel dotenv dependencies.
- Release: 8 tests and source/version check pass; new Python package included in release wheels, version checks and CI tests. Diff whitespace check clean.
- Independent review identified only the Laravel dotenv blocker; correction reviewed clean.

Material limit: no complete Laravel host is present. Controller tests use real installed SDK/config/container and a local HTTP gateway, with a minimal Illuminate HTTP fixture when that optional host dependency is absent. Blade rendering and actual web/auth/CSRF/throttle middleware still require verification in the consuming Laravel application. Session expiry starts a fresh conversation after page/widget reload; automatic renewal/history restoration is outside the agreed first integration.
