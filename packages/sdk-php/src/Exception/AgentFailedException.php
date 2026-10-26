<?php

declare(strict_types=1);

namespace UniversalAIKit\Exception;

class AgentFailedException extends UaiException
{
    /** @param array<string, mixed> $event */
    public function __construct(public readonly array $event, public readonly string $agentCode)
    {
        parent::__construct(sprintf('Agent run failed (%s).', $agentCode));
    }
}
