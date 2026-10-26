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
    public function testReadsDotenvValuesWithoutPutenv(): void
    {
        $previous = $_ENV;
        $previousServer = $_SERVER;
        try {
            // Laravel's default dotenv adapter writes these globals, not putenv.
            $_ENV['UAI_WIDGET_ORIGIN'] = 'https://dotenv-only.test';
            $_ENV['UAI_WIDGET_ASSISTANT_ID'] = '11111111-1111-4111-8111-111111111111';
            $_ENV['UAI_WIDGET_TTL_SECONDS'] = '900';
            $_ENV['UAI_API_KEY'] = 'dotenv-server-key';
            unset($_ENV['UAI_WIDGET_PUBLIC_BASE_URL']);
            $_SERVER['UAI_WIDGET_PUBLIC_BASE_URL'] = 'https://public-gateway.test';
            $config = require __DIR__ . '/../config/universal-ai-kit.php';
            self::assertSame('https://dotenv-only.test', $config['widget']['origin']);
            self::assertSame('https://public-gateway.test', $config['widget']['public_base_url']);
            self::assertSame('11111111-1111-4111-8111-111111111111', $config['widget']['assistant_id']);
            self::assertSame(900, $config['widget']['ttl_seconds']);
            self::assertSame('dotenv-server-key', $config['api_key']);
        } finally {
            $_ENV = $previous;
            $_SERVER = $previousServer;
        }
    }

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
