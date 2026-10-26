<?php

declare(strict_types=1);

namespace UniversalAIKit;

/**
 * Incremental Server-Sent Events decoder. It accepts arbitrary byte chunks;
 * UTF-8 code points may be split because parsing only interprets complete
 * lines and never rewrites the data bytes.
 */
final class SseDecoder
{
    private string $buffer = '';
    /** @var list<string> */
    private array $data = [];
    private ?string $event = null;
    private ?string $id = null;
    private ?string $lastEventId = null;
    private bool $started = false;

    /** @return list<SseEvent> */
    public function push(string $chunk): array
    {
        $this->buffer .= $chunk;
        if (! $this->started) {
            $this->started = true;
            if (str_starts_with($this->buffer, "\xEF\xBB\xBF")) {
                $this->buffer = substr($this->buffer, 3);
            }
        }

        return $this->drain(false);
    }

    /** @return list<SseEvent> */
    public function end(): array
    {
        $events = $this->drain(true);
        $this->data = [];
        $this->event = null;
        $this->id = null;

        return $events;
    }

    /** @return list<SseEvent> */
    private function drain(bool $atEnd): array
    {
        $events = [];
        while (true) {
            $length = strlen($this->buffer);
            $index = strcspn($this->buffer, "\r\n");
            if ($index >= $length) {
                break;
            }
            $character = $this->buffer[$index];
            if ($character === "\r" && $index === $length - 1 && ! $atEnd) {
                break;
            }
            $next = $index + 1;
            if ($character === "\r" && $next < $length && $this->buffer[$next] === "\n") {
                $next++;
            }
            $line = substr($this->buffer, 0, $index);
            $this->buffer = substr($this->buffer, $next);
            $event = $this->consumeLine($line);
            if ($event !== null) {
                $events[] = $event;
            }
        }
        if ($atEnd && $this->buffer !== '') {
            $line = $this->buffer;
            $this->buffer = '';
            $event = $this->consumeLine($line);
            if ($event !== null) {
                $events[] = $event;
            }
        }

        return $events;
    }

    private function consumeLine(string $line): ?SseEvent
    {
        if ($line === '') {
            $data = implode("\n", $this->data);
            $event = $this->event;
            $id = $this->id ?? $this->lastEventId;
            $this->data = [];
            $this->event = null;
            $this->id = null;
            if ($data === '') {
                return null;
            }

            return new SseEvent($id, $event, $data);
        }
        if (str_starts_with($line, ':')) {
            return null;
        }

        $separator = strpos($line, ':');
        if ($separator === false) {
            $field = $line;
            $value = '';
        } else {
            $field = substr($line, 0, $separator);
            $value = substr($line, $separator + 1);
            if (str_starts_with($value, ' ')) {
                $value = substr($value, 1);
            }
        }

        match ($field) {
            'data' => $this->data[] = $value,
            'event' => $this->event = $value,
            'id' => $this->setId($value),
            default => null,
        };

        return null;
    }

    private function setId(string $value): void
    {
        if (str_contains($value, "\0")) {
            return;
        }
        $this->id = $value;
        $this->lastEventId = $value;
    }
}
