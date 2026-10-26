<?php

declare(strict_types=1);
namespace UniversalAIKit\Tests;
require_once __DIR__ . '/fixtures/laravel-http.php';
use Illuminate\Config\Repository;
use Illuminate\Container\Container;
use Illuminate\Http\Request;
use PHPUnit\Framework\TestCase;
use UniversalAIKit\Client;
use UniversalAIKit\Laravel\WidgetSessionController;
final class WidgetSessionControllerTest extends TestCase
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

    private function request(mixed $subject, ?string $origin): Request
    {
        $user = $subject === null ? null : new class($subject) {
            public function __construct(private mixed $id) {}
            public function getAuthIdentifier(): mixed { return $this->id; }
        };
        if (method_exists(Request::class, 'create')) {
            $request = Request::create('/', 'POST', ['assistant_id' => 'attacker'], [], [], $origin === null ? [] : ['HTTP_ORIGIN' => $origin]);
            $request->setUserResolver(fn () => $user);
            return $request;
        }
        return new Request($user, $origin);
    }
    private function controller(array $overrides = [], bool $upstream = false): WidgetSessionController
    {
        $container = new Container();
        $container->bind(Client::class, fn () => $upstream ? new Client(self::$baseUrl, 'test-key') : throw new \RuntimeException('Upstream must not be called'));
        return new WidgetSessionController(new Repository(['universal-ai-kit' => array_replace_recursive([
            'base_url' => 'http://gateway.test', 'api_key' => 'secret', 'timeout_ms' => 30000,
            'widget' => ['assistant_id' => '11111111-1111-4111-8111-111111111111', 'origin' => 'https://app.test', 'public_base_url' => 'https://gateway.test', 'ttl_seconds' => 600],
        ], $overrides)]), $container);
    }
    public function testRejectsMissingAndInvalidIdentityBeforeUpstream(): void
    {
        foreach ([null, '', '   ', str_repeat('x', 201), []] as $subject) {
            self::assertSame(401, ($this->controller())($this->request($subject, 'https://app.test'))->getStatusCode());
        }
    }
    public function testRequiresExactOrigin(): void
    {
        foreach ([null, 'null', 'https://evil.test', 'https://app.test/'] as $origin) {
            self::assertSame(403, ($this->controller())($this->request('user-1', $origin))->getStatusCode());
        }
    }
    public function testRejectsInvalidConfigurationBeforeUpstream(): void
    {
        foreach ([['ttl_seconds' => 0], ['ttl_seconds' => 86401], ['public_base_url' => 'javascript:alert(1)'], ['assistant_id' => ''], ['origin' => 'https://app.test/path']] as $widget) {
            self::assertSame(503, ($this->controller(['widget' => $widget]))($this->request('user-1', 'https://app.test'))->getStatusCode());
        }
    }
    public function testStartsScopedFreshSessionsWithOnlyPublicFields(): void
    {
        $controller = $this->controller([], true);
        $first = $controller($this->request('user-1', 'https://app.test'));
        $second = $controller($this->request('user-1', 'https://app.test'));
        self::assertSame(200, $first->getStatusCode());
        $data = $first->getData(true);
        self::assertSame(['baseUrl', 'token', 'conversationId', 'expiresAt'], array_keys($data));
        self::assertSame('https://gateway.test', $data['baseUrl']);
        self::assertNotSame($data['conversationId'], $second->getData(true)['conversationId']);
        self::assertSame([
            'assistant_id' => '11111111-1111-4111-8111-111111111111',
            'conversation_id' => $data['conversationId'], 'subject' => 'user-1',
            'origin' => 'https://app.test', 'expires_in_seconds' => 600,
        ], json_decode(base64_decode($data['token']), true));
        self::assertSame('no-store', is_array($first->headers) ? $first->headers['Cache-Control'] : $first->headers->get('Cache-Control'));
    }
    public function testSanitizesUpstreamFailures(): void
    {
        $response = ($this->controller(['widget' => ['assistant_id' => '22222222-2222-4222-8222-222222222222']], true))($this->request('user-1', 'https://app.test'));
        self::assertSame(502, $response->getStatusCode());
        self::assertSame(['error' => 'Unable to start chat.'], $response->getData(true));
    }
    public function testSanitizesTokenFailuresAndMalformedResponses(): void
    {
        foreach (['token-failure', 'invalid-token-response'] as $subject) {
            $response = ($this->controller([], true))($this->request($subject, 'https://app.test'));
            self::assertSame(502, $response->getStatusCode());
            self::assertSame(['error' => 'Unable to start chat.'], $response->getData(true));
        }
    }
}
