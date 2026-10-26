# Universal AI Kit PHP SDK

Client server-side PHP 8.2+ per la Public API e per lo stream SSE. Usa cURL per
le richieste JSON e gli stream HTTP nativi per l'SSE; nessuna dipendenza runtime
oltre alle estensioni `curl` e `json`.

## Installazione

```bash
composer require universal-ai-kit/sdk-php
```

## Uso

```php
use UniversalAIKit\Client;

$client = new Client(
    baseUrl: getenv('UAI_BASE_URL') ?: 'http://localhost:8080',
    apiKey: getenv('UAI_API_KEY') ?: throw new RuntimeException('missing key'),
    timeoutMs: 30000,
);

$assistant = $client->createAssistant([
    'name' => 'support',
    'model' => 'gpt-test',
    'system_prompt' => 'Be helpful.',
]);
$conversation = $client->createConversation(['assistant_id' => $assistant['id']]);

$stream = $client->streamMessage(
    $conversation['id'],
    ['content' => 'Riassumi i documenti.'],
    idempotencyKey: bin2hex(random_bytes(16)),
);

foreach ($stream as $event) {
    if ($event['event_type'] === 'response.delta') {
        echo $event['payload']['text'];
    }
}
```

`streamMessage` richiede una idempotency key esplicita. `response.completed` è
l'unico esito di successo; EOF senza terminale lancia
`StreamIncompleteException`, mentre `agent.failed` e `agent.cancelled` lanciano
`AgentFailedException` / `AgentCancelledException` dopo aver emesso l'evento.

## Errori

- `ApiException`: status HTTP, `errorCode`, body.
- `ValidationException`: input/header obbligatorio mancante.
- `TimeoutException`, `TransportException`, `ResponseException`.
- `StreamProtocolException`, `StreamIncompleteException`.
- `AgentFailedException`, `AgentCancelledException`.

## Laravel

Il service provider è auto-discovered. Config in
`config/universal-ai-kit.php`; esempio completo in `examples/laravel/` e
[guida Laravel](../../docs/laravel.md). La key resta server-side: il browser
riceve solo lo stream SSE del backend Laravel.

## Sviluppo

```bash
cd packages/sdk-php
composer install
composer test
```

`ContractTest` confronta `Operations::ALL` con
`packages/api-contract/public.openapi.json`.
