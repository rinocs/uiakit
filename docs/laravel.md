# Laravel integration

The `packages/sdk-php` package exposes `UniversalAIKit\Client` and the service
provider `UniversalAIKit\Laravel\UniversalAiKitServiceProvider`, registered
automatically via `extra.laravel.providers`.

## Configuration

Publish the configuration:

```bash
php artisan vendor:publish --tag=universal-ai-kit-config
```

Server-side values:

```dotenv
UAI_BASE_URL=http://gateway:8080
UAI_API_KEY=uai_server_side_secret
UAI_TIMEOUT_MS=30000
```

`UAI_API_KEY` should never appear in `VITE_*` variables, JavaScript bundles or
browser responses. The client uses the key only in Laravel → gateway requests.

## Streaming endpoints

The example in `examples/laravel/routes/api.php` receives `conversation_id`,
`content` and `idempotency_key`, opens the stream with the PHP client and forwards it as
SSE. The browser does not speak directly to the gateway and does not see the key.

```php
$stream = $client->streamMessage(
    $data['conversation_id'],
    ['content' => $data['content']],
    $data['idempotency_key'],
);

return response()->stream(function () use ($stream): void {
    foreach ($stream as $event) {
        echo 'id: ' . $event['event_id'] . "\n";
        echo 'event: ' . $event['event_type'] . "\n";
        echo 'data: ' . json_encode($event, JSON_UNESCAPED_SLASHES) . "\n\n";
        @ob_flush();
        flush();
    }
}, 200, [
    'Content-Type' => 'text/event-stream',
    'Cache-Control' => 'no-cache',
    'X-Accel-Buffering' => 'no',
]);
```

## Test

`packages/sdk-php/tests/LaravelServiceProviderTest.php` tests the binding of the
containers and configuration; client tests use a mock HTTP gateway
local. Run:

```bash
cd packages/sdk-php && composer test
```