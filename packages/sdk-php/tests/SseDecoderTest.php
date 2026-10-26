<?php

declare(strict_types=1);

namespace UniversalAIKit\Tests;

use PHPUnit\Framework\TestCase;
use UniversalAIKit\SseDecoder;

final class SseDecoderTest extends TestCase
{
    public function testDecodesFragmentAcrossChunks(): void
    {
        $decoder = new SseDecoder();
        $frame = "id: e1\nevent: response.delta\ndata: {\"text\":\"hello\"}\n\n";

        self::assertSame([], $decoder->push(substr($frame, 0, 23)));
        $events = $decoder->push(substr($frame, 23));

        self::assertCount(1, $events);
        self::assertSame('e1', $events[0]->id);
        self::assertSame('response.delta', $events[0]->event);
        self::assertSame('{"text":"hello"}', $events[0]->data);
    }

    public function testPreservesUnicodeSplitAcrossBytes(): void
    {
        $decoder = new SseDecoder();
        $frame = "data: {\"text\":\"caffè 😀\"}\n\n";
        $cut = strpos($frame, '😀') + 2;

        self::assertSame([], $decoder->push(substr($frame, 0, $cut)));
        $events = $decoder->push(substr($frame, $cut));

        self::assertCount(1, $events);
        self::assertSame('{"text":"caffè 😀"}', $events[0]->data);
    }

    public function testSupportsCrlfCommentsAndMultilineData(): void
    {
        $decoder = new SseDecoder();
        $events = $decoder->push(": keepalive\r\nevent: response.delta\r\ndata: first\r\ndata: second\r\n\r\n");

        self::assertCount(1, $events);
        self::assertSame('response.delta', $events[0]->event);
        self::assertSame("first\nsecond", $events[0]->data);
    }

    public function testDoesNotDispatchUnfinishedFrameAtEof(): void
    {
        $decoder = new SseDecoder();

        self::assertSame([], $decoder->push('data: unfinished'));
        self::assertSame([], $decoder->end());
    }
}
