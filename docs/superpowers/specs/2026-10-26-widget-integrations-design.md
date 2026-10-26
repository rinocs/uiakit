# Laravel and FastAPI widget integrations

User scope: reusable chat widgets for Laravel and Python; Python narrowed explicitly to FastAPI. Reuse existing packages/chat-widget Web Component and gateway conversation/widget-token APIs. Django and Flask are outside scope.

Approach: one browser widget and a shared connectChat bootstrap helper, backed by small framework adapters. Separate frontend implementations would duplicate SSE, sanitization and accessibility; a general Python SDK is unnecessary for this integration.

Both adapters expose a same-origin authenticated POST session endpoint. Assistant, public gateway URL, allowed origin and token TTL come from server configuration, never browser input. The endpoint creates a fresh conversation and mints a short-lived widget token bound to the authenticated subject and exact configured origin. It returns only baseUrl, token, conversationId and expiresAt with Cache-Control: no-store. Upstream errors return a sanitized error. Host applications own authentication and rate limiting; Laravel examples also use web CSRF middleware. FastAPI router requires an explicit subject dependency. Origin checks remain mandatory in both. Do not accept client-selected conversation IDs or assistants.

The browser helper POSTs JSON with same-origin credentials, accepts host CSRF headers, rejects redirects/cross-origin session URLs and validates the returned configuration before setting it. It preserves component callbacks and styling. No administrative credential in markup, browser bundles, storage or responses. The session lives in widget memory, expires after its configured TTL and is renewed by starting a new widget session (a fresh conversation); automatic renewal/history persistence is outside this first integration.

Deliver Laravel controller/config/Blade component and Vite entry example, plus an installable FastAPI router package and runnable authenticated FastAPI example serving the shared browser assets. Keep application authentication explicit; no default anonymous public endpoint. Existing console/Docker behavior is unrelated and must remain unchanged.
