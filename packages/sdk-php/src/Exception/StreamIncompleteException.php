<?php

declare(strict_types=1);

namespace UniversalAIKit\Exception;

class StreamIncompleteException extends UaiException
{
    public function __construct(public readonly ?string $runId = null)
    {
        parent::__construct('The event stream ended without a terminal event.');
    }
}
