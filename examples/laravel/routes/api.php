<?php

declare(strict_types=1);

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use UniversalAIKit\Client;

Route::post('/uai/chat', function (Request $request, Client $client) {
    $data = $request->validate([
        'conversation_id' => ['required', 'string'],
        'content' => ['required', 'string', 'max:32000'],
        'idempotency_key' => ['required', 'string', 'max:128'],
    ]);

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
})->middleware('auth');
