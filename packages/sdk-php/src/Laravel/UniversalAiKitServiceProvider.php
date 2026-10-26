<?php

declare(strict_types=1);

namespace UniversalAIKit\Laravel;

use Illuminate\Support\ServiceProvider;
use UniversalAIKit\Client;

final class UniversalAiKitServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        $this->mergeConfigFrom(__DIR__ . '/../../config/universal-ai-kit.php', 'universal-ai-kit');

        $this->app->singleton(Client::class, function ($app): Client {
            $config = $app['config']->get('universal-ai-kit');

            return new Client(
                (string) ($config['base_url'] ?? ''),
                (string) ($config['api_key'] ?? ''),
                (int) ($config['timeout_ms'] ?? 30000),
            );
        });
        $this->app->alias(Client::class, 'universal-ai-kit');
    }

    public function boot(): void
    {
        if ($this->app->runningInConsole()) {
            $this->publishes([
                __DIR__ . '/../../config/universal-ai-kit.php' => config_path('universal-ai-kit.php'),
            ], 'universal-ai-kit-config');
        }
    }
}
