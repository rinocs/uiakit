# Laravel example

1. Add the package to the Laravel application (path repository while developing):

```json
{
  "repositories": [
    { "type": "path", "url": "../../packages/sdk-php" }
  ],
  "require": {
    "universal-ai-kit/sdk-php": "*"
  }
}
```

2. Publish the config (optional) and set server-side environment values:

```bash
php artisan vendor:publish --tag=universal-ai-kit-config
```

```dotenv
UAI_BASE_URL=http://gateway:8080
UAI_API_KEY=uai_server_side_secret
UAI_TIMEOUT_MS=30000
```

3. Copy `routes/api.php` into the application's API routes (or merge the route).

The browser calls `POST /api/uai/chat` with the conversation id, content and an
idempotency key. It never receives `UAI_API_KEY`; the Laravel server holds the
credential and opens the gateway SSE stream server-side.
