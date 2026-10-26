<?php

declare(strict_types=1);

namespace UniversalAIKit;

final class SseEvent
{
    public function __construct(
        public readonly ?string $id,
        public readonly ?string $event,
        public readonly string $data,
    ) {
    }
}
