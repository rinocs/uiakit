<?php

declare(strict_types=1);

namespace UniversalAIKit;

use Generator;
use IteratorAggregate;
use JsonException;
use UniversalAIKit\Exception\AgentCancelledException;
use UniversalAIKit\Exception\AgentFailedException;
use UniversalAIKit\Exception\StreamIncompleteException;
use UniversalAIKit\Exception\StreamProtocolException;
use UniversalAIKit\Exception\TimeoutException;
use UniversalAIKit\Exception\TransportException;

/**
 * One-pass SSE message stream. Iterate with foreach; the generator closes the
 * underlying HTTP stream when it returns or throws.
 *
 * @implements IteratorAggregate<int, array<string, mixed>>
 */
final class MessageStream implements IteratorAggregate
{
    private bool $closed = false;
    private bool $terminal = false;

    /** @param resource $handle */
    public function __construct(
        private $handle,
        public readonly string $runId,
        public readonly ?int $assistantVersion = null,
    ) {
    }

    /** @return Generator<int, array<string, mixed>> */
    public function getIterator(): Generator
    {
        $decoder = new SseDecoder();
        try {
            while (! $this->terminal) {
                $line = fgets($this->handle);
                if ($line === false) {
                    $meta = stream_get_meta_data($this->handle);
                    if (! empty($meta['timed_out'])) {
                        throw new TimeoutException('SSE stream timed out.');
                    }
                    foreach ($decoder->end() as $raw) {
                        $event = $this->parseEvent($raw);
                        yield $event;
                        $this->terminalState($event);
                        if ($this->terminal) {
                            return;
                        }
                    }
                    if (feof($this->handle)) {
                        throw new StreamIncompleteException($this->runId);
                    }
                    throw new TransportException('SSE stream read failed.');
                }
                foreach ($decoder->push($line) as $raw) {
                    $event = $this->parseEvent($raw);
                    yield $event;
                    $this->terminalState($event);
                    if ($this->terminal) {
                        return;
                    }
                }
            }
        } finally {
            $this->close();
        }
    }

    public function close(): void
    {
        if ($this->closed) {
            return;
        }
        $this->closed = true;
        if (is_resource($this->handle)) {
            fclose($this->handle);
        }
    }

    /** @param array<string, mixed> $event */
    private function terminalState(array $event): void
    {
        $type = $event['event_type'];
        if ($type === 'response.completed') {
            $this->terminal = true;
            return;
        }
        if ($type === 'agent.failed') {
            $this->terminal = true;
            $code = is_string($event['payload']['code'] ?? null) ? $event['payload']['code'] : 'agent_failed';
            throw new AgentFailedException($event, $code);
        }
        if ($type === 'agent.cancelled') {
            $this->terminal = true;
            $code = is_string($event['payload']['code'] ?? null) ? $event['payload']['code'] : 'cancelled';
            throw new AgentCancelledException($event, $code);
        }
    }

    /** @return array<string, mixed> */
    private function parseEvent(SseEvent $raw): array
    {
        try {
            $event = json_decode($raw->data, true, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException $exception) {
            throw new StreamProtocolException('SSE data is not valid JSON.', 0, $exception);
        }
        if (! is_array($event)) {
            throw new StreamProtocolException('SSE data must be a JSON object.');
        }
        $type = $event['event_type'] ?? null;
        if (! is_string($type) || ! in_array($type, [
            'agent.started',
            'response.delta',
            'response.completed',
            'agent.failed',
            'agent.cancelled',
        ], true)) {
            throw new StreamProtocolException('SSE event has an unknown event_type.');
        }
        if ($raw->event !== null && $raw->event !== $type) {
            throw new StreamProtocolException('SSE event name does not match event_type.');
        }
        $payload = $event['payload'] ?? null;
        if (! is_array($payload)) {
            throw new StreamProtocolException('SSE event payload must be an object.');
        }
        if (in_array($type, ['response.delta', 'response.completed'], true)
            && ! is_string($payload['text'] ?? null)) {
            throw new StreamProtocolException($type . ' payload.text is required.');
        }
        if ($type === 'agent.failed' && ! is_string($payload['code'] ?? null)) {
            throw new StreamProtocolException('agent.failed payload.code is required.');
        }
        if ($type === 'agent.cancelled' && isset($payload['code']) && ! is_string($payload['code'])) {
            throw new StreamProtocolException('agent.cancelled payload.code must be a string.');
        }

        return $event;
    }
}
