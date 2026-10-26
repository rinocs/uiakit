<?php

declare(strict_types=1);

namespace UniversalAIKit\Tests;

use PHPUnit\Framework\TestCase;
use UniversalAIKit\Operations;

final class ContractTest extends TestCase
{
    public function testOperationsMatchPublicOpenApi(): void
    {
        $raw = file_get_contents(dirname(__DIR__) . '/../api-contract/public.openapi.json');
        self::assertNotFalse($raw);
        $document = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
        $expected = [];
        foreach ($document['paths'] as $path => $item) {
            foreach ($item as $method => $operation) {
                if ($method === 'parameters') {
                    continue;
                }
                $id = $operation['operationId'];
                $headers = array_merge($item['parameters'] ?? [], $operation['parameters'] ?? []);
                $expected[$id] = [
                    'method' => strtoupper($method),
                    'path' => $path,
                    'idempotency' => $this->hasRequiredHeader($headers, 'Idempotency-Key'),
                    'ifMatch' => $this->hasRequiredHeader($headers, 'If-Match'),
                ];
            }
        }
        ksort($expected);
        $actual = Operations::ALL;
        ksort($actual);
        self::assertSame(array_keys($expected), array_keys($actual));
        foreach ($expected as $id => $operation) {
            self::assertSame($operation['method'], $actual[$id]['method'], $id);
            self::assertSame($operation['path'], $actual[$id]['path'], $id);
            self::assertSame($operation['idempotency'], $actual[$id]['idempotency'] ?? false, $id);
            self::assertSame($operation['ifMatch'], $actual[$id]['ifMatch'] ?? false, $id);
        }
    }

    /** @param list<array<string, mixed>> $headers */
    private function hasRequiredHeader(array $headers, string $name): bool
    {
        foreach ($headers as $header) {
            if (($header['in'] ?? null) === 'header'
                && ($header['name'] ?? null) === $name
                && ($header['required'] ?? false) === true) {
                return true;
            }
        }

        return false;
    }
}
