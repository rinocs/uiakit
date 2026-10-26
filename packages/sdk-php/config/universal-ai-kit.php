<?php

declare(strict_types=1);

return [
    'base_url' => getenv('UAI_BASE_URL') ?: 'http://gateway:8080',
    'api_key' => getenv('UAI_API_KEY') ?: '',
    'timeout_ms' => (int) (getenv('UAI_TIMEOUT_MS') ?: 30000),
];
