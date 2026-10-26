<?php

declare(strict_types=1);

namespace UniversalAIKit\Tests;

use Illuminate\Config\Repository;
use Illuminate\Container\Container;
use Illuminate\Support\ServiceProvider;
use PHPUnit\Framework\TestCase;
use UniversalAIKit\Client;
use UniversalAIKit\Laravel\UniversalAiKitServiceProvider;

final class LaravelServiceProviderTest extends TestCase
{
    public function testProviderBindsConfiguredClient(): void
    {
        if (! class_exists(ServiceProvider::class)) {
            self::markTestSkipped('illuminate/support is not installed.');
        }
        $container = new Container();
        $container->instance('config', new Repository([
            'universal-ai-kit' => [
                'base_url' => 'http://gateway.test',
                'api_key' => 'server-side-key',
                'timeout_ms' => 5000,
            ],
        ]));
        $provider = new UniversalAiKitServiceProvider($container);
        $provider->register();

        self::assertInstanceOf(Client::class, $container->make(Client::class));
        self::assertInstanceOf(Client::class, $container->make('universal-ai-kit'));
    }
}
