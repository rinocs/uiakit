<?php

declare(strict_types=1);

namespace UniversalAIKit\Exception;

class AgentCancelledException extends UaiException
{
    /** @param array<string, mixed> $event */
    public function __construct(public readonly array $event, public readonly string $agentCode = 'cancelled')
    {
        parent::__construct(sprintf('Agent run was cancelled (%s).', $agentCode));
    }
}
