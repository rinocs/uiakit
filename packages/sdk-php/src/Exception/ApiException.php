<?php

declare(strict_types=1);

namespace UniversalAIKit\Exception;

class ApiException extends UaiException
{
    public function __construct(
        public readonly int $status,
        public readonly string $errorCode,
        public readonly string $body,
        ?string $message = null,
    ) {
        parent::__construct($message ?? sprintf('Gateway request failed with status %d (%s).', $status, $errorCode));
    }

    public static function fromResponse(int $status, string $body): self
    {
        $decoded = json_decode($body, true);
        $code = is_array($decoded) && isset($decoded['error']) && is_string($decoded['error'])
            ? $decoded['error']
            : 'http_' . $status;

        return new self($status, $code, $body);
    }
}
