<?php

declare(strict_types=1);

// Laravel dotenv does not enable putenv by default. Read its environment
// adapters first, with a process-environment fallback for other deployments.
$environment = static fn (string $name, mixed $default): mixed =>
    $_ENV[$name] ?? $_SERVER[$name] ?? (($value = getenv($name)) === false ? $default : $value);

return [
    'base_url' => $environment('UAI_BASE_URL', 'http://gateway:8080'),
    'api_key' => $environment('UAI_API_KEY', ''),
    'widget' => [
        'assistant_id' => $environment('UAI_WIDGET_ASSISTANT_ID', ''),
        'origin' => $environment('UAI_WIDGET_ORIGIN', ''),
        'public_base_url' => $environment('UAI_WIDGET_PUBLIC_BASE_URL', ''),
        'ttl_seconds' => (int) $environment('UAI_WIDGET_TTL_SECONDS', 900),
    ],
    'timeout_ms' => (int) $environment('UAI_TIMEOUT_MS', 30000),
];
