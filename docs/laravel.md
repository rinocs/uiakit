# Laravel integration

The PHP SDK auto-discovers `UniversalAIKit\Laravel\UniversalAiKitServiceProvider`.
The provider binds `UniversalAIKit\Client` and registers Blade views; it exposes no
routes. Host applications own authentication, authorization and rate limiting.

## Install in an existing Laravel application

Adjust the local paths to your checkout:

```bash
composer config repositories.universal-ai-kit path ../../packages/sdk-php
composer require universal-ai-kit/sdk-php:@dev
npm install ../../packages/chat-widget
php artisan vendor:publish --tag=universal-ai-kit-config
```

The npm package is `@universal-ai-kit/chat-widget`. Build that package first with
`npm run build` from `packages/chat-widget`, then use your application's Vite
bundler. Copy `examples/laravel/resources/js/chat.js` to `resources/js/chat.js`
and include it in your Vite entry points, or import it from `resources/js/app.js`.

Set these values on the Laravel server (never use `VITE_*` for the key):

```dotenv
UAI_BASE_URL=http://gateway:8080
UAI_API_KEY=uai_server_side_secret
UAI_TIMEOUT_MS=30000
UAI_WIDGET_ASSISTANT_ID=11111111-1111-4111-8111-111111111111
UAI_WIDGET_ORIGIN=https://app.example.com
UAI_WIDGET_PUBLIC_BASE_URL=https://gateway.example.com
UAI_WIDGET_TTL_SECONDS=600
```

Use an existing assistant UUID. The public gateway URL must be reachable by the
browser; the private base URL is used by Laravel. The widget origin is an exact
scheme/host/optional-port origin without a trailing slash. Configure the gateway's
`UAI_WIDGET_ORIGINS=https://app.example.com` to allow the same origin. For local
HTTP development set both origins to the exact local application origin.

Use a scoped server credential with `conversations:write` and
`widget-tokens:write` permissions. Keep it out of markup, JavaScript, browser
storage and responses. The browser receives only a short-lived widget credential.
TTL must be 60–86400 seconds; 600 seconds is the default.

## Authenticated widget

Merge `examples/laravel/routes/web.php` into the host's `routes/web.php`. Laravel's
web route group provides session and CSRF middleware; the example adds `auth`
and `throttle:10,1`. Keep these protections and tune rate limits for your app.
The endpoint is private by default and derives the subject from
`$request->user()->getAuthIdentifier()`; no anonymous identity fallback exists.

In your Blade layout, render the CSRF meta tag and load the bundled entry after
the component markup (or use Vite's deferred module scripts):

```blade
<head>
    <meta name="csrf-token" content="{{ csrf_token() }}">
    @vite(['resources/js/app.js'])
</head>
<body>
    <x-universal-ai-kit::chat
        title="Support"
        theme="light"
        placeholder="Ask a question…"
        session-url="/uai/widget/session"
    />
</body>
```

Import `./chat.js` from `resources/js/app.js`, then run `npm run build` in the host
application. The example module imports `connectChat` and passes the CSRF header
through its `{sessionUrl, headers}` options. No server secrets appear in the view.

`POST /uai/widget/session` rejects missing, `null` and mismatched Origin headers.
It ignores browser-selected assistants and conversations, creates a new
conversation for the configured assistant, and issues a token bound to that
conversation, authenticated subject and exact origin. Its response contains only
`baseUrl`, `token`, `conversationId` and `expiresAt`, with `Cache-Control: no-store`.
Authentication failures return 401, origin failures 403, invalid configuration
503 and sanitized upstream failures 502. The session endpoint never reflects
upstream error details or administrative credentials.

Sessions remain in widget memory. After TTL expiry, reconnecting starts a fresh
conversation. Automatic renewal and history persistence are outside this adapter.

## Existing server-side streaming proxy

`examples/laravel/routes/api.php` remains a separate proxy example: the browser
calls `POST /api/uai/chat` with a conversation id, content and idempotency key;
Laravel streams gateway SSE using the PHP SDK. Apply your host authorization for
conversation access and rate limits when adopting it. This API remains unchanged.

## Verification

```bash
cd packages/sdk-php
composer test
```

Controller tests cover identity, exact origin, configuration, scoped token
payloads, fresh conversations, public response fields and sanitized errors.
Tests use a local TCP mock gateway. If `illuminate/http` is absent, a minimal HTTP
fixture exercises controller behavior; full Laravel middleware/rendering should
also be checked in the host application.
