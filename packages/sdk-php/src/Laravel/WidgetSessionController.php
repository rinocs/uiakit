<?php

declare(strict_types=1);

namespace UniversalAIKit\Laravel;

use Illuminate\Contracts\Config\Repository;
use Illuminate\Contracts\Container\Container;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use UniversalAIKit\Client;
use UniversalAIKit\Exception\UaiException;

final class WidgetSessionController
{
    public function __construct(private Repository $config, private Container $container) {}

    public function __invoke(Request $request): JsonResponse
    {
        $subject = $request->user()?->getAuthIdentifier();
        if ((!is_string($subject) && !is_int($subject)) || trim((string) $subject) === '' || strlen((string) $subject) > 200) {
            return $this->error(401, 'Authentication required.');
        }
        $config = $this->config->get('universal-ai-kit', []);
        $widget = $config['widget'] ?? [];
        $origin = $widget['origin'] ?? null;
        $publicUrl = $widget['public_base_url'] ?? null;
        $assistant = $widget['assistant_id'] ?? null;
        $ttl = $widget['ttl_seconds'] ?? null;
        if (!self::httpUrl($origin) || parse_url($origin, PHP_URL_PATH) !== null || parse_url($origin, PHP_URL_QUERY) !== null || parse_url($origin, PHP_URL_FRAGMENT) !== null ||
            !self::httpUrl($publicUrl) || parse_url($publicUrl, PHP_URL_QUERY) !== null || parse_url($publicUrl, PHP_URL_FRAGMENT) !== null ||
            !is_string($assistant) || preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i', $assistant) !== 1 ||
            !is_int($ttl) || $ttl < 60 || $ttl > 86400 || !self::httpUrl($config['base_url'] ?? null) ||
            !is_string($config['api_key'] ?? null) || trim($config['api_key']) === '' || !is_int($config['timeout_ms'] ?? null) || $config['timeout_ms'] <= 0) {
            return $this->error(503, 'Widget is unavailable.');
        }
        if ($request->header('Origin') !== $origin) {
            return $this->error(403, 'Origin is not allowed.');
        }
        try {
            $client = $this->container->make(Client::class);
            $conversation = $client->createConversation(['assistant_id' => $assistant]);
            if (!is_string($conversation['id'] ?? null) || $conversation['id'] === '') {
                return $this->error(502, 'Unable to start chat.');
            }
            $token = $client->createWidgetToken([
                'assistant_id' => $assistant,
                'conversation_id' => $conversation['id'],
                'subject' => (string) $subject,
                'origin' => $origin,
                'expires_in_seconds' => $ttl,
            ]);
            if (!is_string($token['token'] ?? null) || $token['token'] === '' || !is_string($token['expires_at'] ?? null) || strtotime($token['expires_at']) === false) {
                return $this->error(502, 'Unable to start chat.');
            }
            return new JsonResponse([
                'baseUrl' => rtrim($publicUrl, '/'), 'token' => $token['token'],
                'conversationId' => $conversation['id'], 'expiresAt' => $token['expires_at'],
            ], 200, ['Cache-Control' => 'no-store']);
        } catch (UaiException) {
            return $this->error(502, 'Unable to start chat.');
        }
    }

    private static function httpUrl(mixed $value): bool
    {
        return is_string($value) && filter_var($value, FILTER_VALIDATE_URL) !== false &&
            in_array(parse_url($value, PHP_URL_SCHEME), ['http', 'https'], true) &&
            parse_url($value, PHP_URL_USER) === null && parse_url($value, PHP_URL_PASS) === null;
    }

    private function error(int $status, string $message): JsonResponse
    {
        return new JsonResponse(['error' => $message], $status, ['Cache-Control' => 'no-store']);
    }
}
