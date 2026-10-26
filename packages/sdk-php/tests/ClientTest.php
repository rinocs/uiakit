<?php

declare(strict_types=1);

namespace UniversalAIKit\Tests;

use PHPUnit\Framework\TestCase;
use UniversalAIKit\Client;
use UniversalAIKit\Exception\AgentFailedException;
use UniversalAIKit\Exception\ApiException;
use UniversalAIKit\Exception\StreamIncompleteException;
use UniversalAIKit\Exception\TimeoutException;
use UniversalAIKit\Exception\ValidationException;

final class ClientTest extends TestCase
{
    private static mixed $process = null;
    /** @var list<resource> */
    private static array $pipes = [];
    private static string $baseUrl = '';

    public static function setUpBeforeClass(): void
    {
        $socket = stream_socket_server('tcp://127.0.0.1:0');
        self::assertNotFalse($socket);
        $name = stream_socket_get_name($socket, false);
        fclose($socket);
        $port = (int) substr((string) $name, strrpos((string) $name, ':') + 1);
        self::$baseUrl = 'http://127.0.0.1:' . $port;
        self::$process = proc_open(
            [PHP_BINARY, '-S', '127.0.0.1:' . $port, __DIR__ . '/fixtures/server.php'],
            [
                0 => ['pipe', 'r'],
                1 => ['pipe', 'w'],
                2 => ['pipe', 'w'],
            ],
            self::$pipes,
        );
        self::assertIsResource(self::$process);
        $deadline = microtime(true) + 5;
        do {
            $probe = @fsockopen('127.0.0.1', $port, $errorCode, $errorMessage, 0.1);
            if (is_resource($probe)) {
                fclose($probe);
                return;
            }
            usleep(50_000);
        } while (microtime(true) < $deadline);
        self::fail('mock gateway did not start: ' . $errorMessage);
    }

    public static function tearDownAfterClass(): void
    {
        foreach (self::$pipes as $pipe) {
            if (is_resource($pipe)) {
                fclose($pipe);
            }
        }
        self::$pipes = [];
        if (is_resource(self::$process)) {
            proc_terminate(self::$process);
            proc_close(self::$process);
        }
        self::$process = null;
    }

    private function client(int $timeoutMs = 30000): Client
    {
        return new Client(self::$baseUrl, 'test-key', $timeoutMs);
    }

    public function testCreatesResourcesAndStreamsMessages(): void
    {
        $client = $this->client();
        $assistant = $client->createAssistant([
            'name' => 'support',
            'model' => 'test-model',
            'system_prompt' => 'Be helpful.',
        ]);
        self::assertSame('assistant-1', $assistant['id']);

        $conversation = $client->createConversation(['assistant_id' => $assistant['id']]);
        self::assertSame('conversation-1', $conversation['id']);

        $stream = $client->streamMessage($conversation['id'], ['content' => 'ciao'], 'idem-1');
        self::assertSame('run-1', $stream->runId);
        self::assertSame(2, $stream->assistantVersion);

        $events = [];
        foreach ($stream as $event) {
            $events[] = $event;
        }
        self::assertSame(
            ['agent.started', 'response.delta', 'response.completed'],
            array_column($events, 'event_type'),
        );
        self::assertSame('caffè 😀', $events[1]['payload']['text']);
    }

    public function testAgentFailureIsTerminal(): void
    {
        $stream = $this->client()->streamMessage('conversation-failed', ['content' => 'x'], 'idem-failed');
        $events = [];
        $failure = null;
        try {
            foreach ($stream as $event) {
                $events[] = $event;
            }
        } catch (AgentFailedException $exception) {
            $failure = $exception;
        }

        self::assertNotNull($failure);
        self::assertSame('provider_error', $failure->agentCode);
        self::assertSame(['agent.started', 'agent.failed'], array_column($events, 'event_type'));
    }

    public function testEofWithoutTerminalIsIncomplete(): void
    {
        $stream = $this->client()->streamMessage('conversation-incomplete', ['content' => 'x'], 'idem-eof');
        $this->expectException(StreamIncompleteException::class);
        foreach ($stream as $event) {
            // drain
        }
    }

    public function testApiErrorsAreNormalized(): void
    {
        try {
            $this->client()->listModels();
            self::fail('expected ApiException');
        } catch (ApiException $exception) {
            self::assertSame(403, $exception->status);
            self::assertSame('forbidden', $exception->errorCode);
        }
    }

    public function testTimeoutIsMapped(): void
    {
        $this->expectException(TimeoutException::class);
        $this->client(200)->listTools();
    }

    public function testIdempotencyKeyIsRequired(): void
    {
        $this->expectException(ValidationException::class);
        $this->client()->streamMessage('conversation-1', ['content' => 'x'], '  ');
    }

    public function testUploadsMultipartDocument(): void
    {
        $document = $this->client()->uploadDocument('kb-1', 'notes.txt', 'hello', 'Notes');
        self::assertSame('doc-1', $document['id']);
        self::assertSame('notes.txt', $document['filename']);
        self::assertSame('Notes', $document['title']);
    }
}
