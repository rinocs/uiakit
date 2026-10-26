import assert from 'node:assert/strict';
import test from 'node:test';

import { SSEDecoder, parseSSE } from '../src/sse.ts';

const encoder = new TextEncoder();

test('decodes a frame split across chunks at an arbitrary boundary', () => {
  const decoder = new SSEDecoder();
  const bytes = encoder.encode(
    'id: evt-1\nevent: response.delta\ndata: {"text":"hello"}\n\n',
  );
  const cut = 23;

  assert.deepEqual(decoder.push(bytes.slice(0, cut)), []);
  assert.deepEqual(decoder.push(bytes.slice(cut)), [
    { id: 'evt-1', event: 'response.delta', data: '{"text":"hello"}' },
  ]);
});

test('preserves Unicode split across byte boundaries', () => {
  const decoder = new SSEDecoder();
  const frame = encoder.encode('data: {"text":"caffè 😀"}\n\n');
  const emoji = encoder.encode('😀');
  const cut = frame.indexOf(emoji[0]!) + 2;

  assert.deepEqual(decoder.push(frame.slice(0, cut)), []);
  const messages = decoder.push(frame.slice(cut));

  assert.equal(messages.length, 1);
  assert.equal(messages[0]?.data, '{"text":"caffè 😀"}');
});

test('supports CRLF, comments and multi-line data', () => {
  const decoder = new SSEDecoder();
  const messages = decoder.push(
    encoder.encode(': keepalive\r\nevent: response.delta\r\ndata: first\r\ndata: second\r\n\r\n'),
  );

  assert.deepEqual(messages, [
    { event: 'response.delta', data: 'first\nsecond' },
  ]);
});

test('does not dispatch an unfinished frame at EOF', () => {
  const decoder = new SSEDecoder();

  assert.deepEqual(decoder.push(encoder.encode('data: unfinished')), []);
  assert.deepEqual(decoder.end(), []);
});

test('parseSSE yields frames from a fragmented stream', async () => {
  const frame = encoder.encode(
    'id: a\nevent: agent.started\ndata: {}\n\n' +
      'id: b\nevent: response.completed\ndata: {"text":"ok","usage":{}}\n\n',
  );
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(frame.slice(0, 7));
      controller.enqueue(frame.slice(7, 41));
      controller.enqueue(frame.slice(41));
      controller.close();
    },
  });

  const messages = [];
  for await (const message of parseSSE(body)) {
    messages.push(message);
  }

  assert.deepEqual(messages, [
    { id: 'a', event: 'agent.started', data: '{}' },
    { id: 'b', event: 'response.completed', data: '{"text":"ok","usage":{}}' },
  ]);
});

test('parseSSE rejects with a normalized abort error', async () => {
  const controller = new AbortController();
  const body = new ReadableStream<Uint8Array>({
    start(value) {
      value.enqueue(encoder.encode('id: a\nevent: agent.started\ndata: {}\n\n'));
    },
  });
  const iterator = parseSSE(body, controller.signal);

  const first = await iterator.next();
  assert.equal(first.done, false);
  controller.abort();

  await assert.rejects(iterator.next(), (error: unknown) => {
    assert.equal((error as { name?: string }).name, 'AbortError');
    return true;
  });

});
