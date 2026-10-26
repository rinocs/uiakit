<?php

declare(strict_types=1);

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$headers = [];
foreach ($_SERVER as $key => $value) {
    if (str_starts_with($key, 'HTTP_')) {
        $headers[strtolower(str_replace('_', '-', substr($key, 5)))] = $value;
    }
}

function json_response(int $status, array $body): void
{
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($body, JSON_UNESCAPED_SLASHES);
}

if (($headers['authorization'] ?? '') !== 'Bearer test-key') {
    json_response(401, ['error' => 'unauthorized']);
    return;
}

if ($method === 'GET' && $path === '/v1/health') {
    json_response(200, ['status' => 'ok', 'version' => 'test']);
    return;
}

if ($method === 'GET' && $path === '/v1/models') {
    json_response(403, ['error' => 'forbidden']);
    return;
}

if ($method === 'GET' && $path === '/v1/tools') {
    usleep(2_000_000);
    json_response(200, []);
    return;
}

if ($method === 'POST' && $path === '/v1/assistants') {
    $body = json_decode((string) file_get_contents('php://input'), true);
    json_response(201, [
        'id' => 'assistant-1',
        'version' => 1,
        'name' => $body['name'] ?? 'support',
        'model' => $body['model'] ?? 'test-model',
        'system_prompt' => $body['system_prompt'] ?? '',
    ]);
    return;
}

if ($method === 'POST' && $path === '/v1/conversations') {
    $body = json_decode((string) file_get_contents('php://input'), true);
    json_response(201, ['id' => 'conversation-1', 'assistant_id' => $body['assistant_id'] ?? 'assistant-1']);
    return;
}

if ($method === 'POST' && preg_match('#^/v1/conversations/([^/]+)/messages$#', $path, $matches) === 1) {
    if (($headers['idempotency-key'] ?? '') === '') {
        json_response(422, ['error' => 'idempotency_key_required']);
        return;
    }
    $conversation = $matches[1];
    header('Content-Type: text/event-stream');
    header('Cache-Control: no-cache');
    header('X-Run-ID: run-1');
    header('X-Assistant-Version: 2');
    @ob_end_clean();
    @ob_implicit_flush(true);

    $emit = static function (string $id, string $type, array $payload): void {
        echo "id: {$id}\nevent: {$type}\ndata: " . json_encode([
            'event_id' => $id,
            'event_type' => $type,
            'event_version' => 1,
            'timestamp' => '2026-10-22T00:00:00Z',
            'run_id' => 'run-1',
            'correlation_id' => 'corr-1',
            'payload' => $payload,
        ], JSON_UNESCAPED_SLASHES) . "\n\n";
        flush();
    };

    $emit('e1', 'agent.started', []);
    if ($conversation === 'conversation-failed') {
        $emit('e2', 'agent.failed', ['code' => 'provider_error']);
        return;
    }
    if ($conversation !== 'conversation-incomplete') {
        $emit('e2', 'response.delta', ['text' => 'caffè 😀']);
        $emit('e3', 'response.completed', ['text' => 'caffè 😀', 'usage' => ['input_tokens' => 1, 'output_tokens' => 2]]);
    }
    return;
}

if ($method === 'POST' && $path === '/v1/documents') {
    if (empty($_FILES['file'])) {
        json_response(422, ['error' => 'file_required']);
        return;
    }
    json_response(201, [
        'id' => 'doc-1',
        'knowledge_base_id' => $_POST['knowledge_base_id'] ?? 'kb-1',
        'filename' => $_FILES['file']['name'],
        'title' => $_POST['title'] ?? '',
        'mime_type' => 'text/plain',
        'size_bytes' => $_FILES['file']['size'],
        'sha256' => hash('sha256', (string) file_get_contents($_FILES['file']['tmp_name'])),
        'created_at' => '2026-10-22T00:00:00Z',
        'ingestion_state' => 'queued',
    ]);
    return;
}

json_response(404, ['error' => 'not_found']);
