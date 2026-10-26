import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APIError,
  AbortError,
  AgentCancelledError,
  AgentFailedError,
  StreamIncompleteError,
  UniversalAIKit,
  ValidationError,
} from '../src/index.ts';
import type { RuntimeEvent } from '../src/types.ts';

const encoder = new TextEncoder();

interface FetchCall {
  url: string;
  init: RequestInit;
}

function mockFetch(
  handler: (call: FetchCall) => Response | Promise<Response>,
): { calls: FetchCall[]; fetch: typeof globalThis.fetch } {
  const calls: FetchCall[] = [];
  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const call = { url, init: init ?? {} };
    calls.push(call);
    return handler(call);
  }) as typeof globalThis.fetch;
  return { calls, fetch: fetchImpl };
}

function sseResponse(
  frames: string[],
  chunks?: number[],
  headers: Record<string, string> = {},
): Response {
  const bytes = encoder.encode(frames.join(''));
  const cuts = chunks ?? [bytes.length];
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      let offset = 0;
      for (const cut of cuts) {
        controller.enqueue(bytes.slice(offset, cut));
        offset = cut;
      }
      if (offset < bytes.length) {
        controller.enqueue(bytes.slice(offset));
      }
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: {
      'content-type': 'text/event-stream',
      'x-run-id': 'run-1',
      'x-assistant-version': '2',
      ...headers,
    },
  });
}

function eventFrame(
  eventType: string,
  payload: Record<string, unknown>,
  id = 'e1',
): string {
  return `id: ${id}\nevent: ${eventType}\ndata: ${JSON.stringify({
    event_id: id,
    event_type: eventType,
    event_version: 1,
    timestamp: '2026-10-22T00:00:00Z',
    run_id: 'run-1',
    correlation_id: 'corr-1',
    payload,
  })}\n\n`;
}

function openSseResponse(firstFrame: string): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(firstFrame));
    },
  });
  return new Response(body, {
    status: 200,
    headers: {
      'content-type': 'text/event-stream',
      'x-run-id': 'run-1',
      'x-assistant-version': '2',
    },
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function clientWith(fetchImpl: typeof globalThis.fetch): UniversalAIKit {
  return new UniversalAIKit({
    baseUrl: 'https://gateway.test/',
    apiKey: 'uai_test',
    fetch: fetchImpl,
  });
}

test('sends a typed streaming message and handles terminal completion', async () => {
  const { calls, fetch } = mockFetch(() =>
    sseResponse(
      [
        eventFrame('agent.started', {}, 'e1'),
        eventFrame('response.delta', { text: 'caffè 😀' }, 'e2'),
        eventFrame(
          'response.completed',
          {
            text: 'caffè 😀',
            usage: { input_tokens: 1, output_tokens: 2 },
          },
          'e3',
        ),
      ],
      [13, 57, 91],
    ),
  );
  const client = clientWith(fetch);

  const stream = await client.conversations.sendMessage(
    'conversation-1',
    { content: 'ciao' },
    { idempotencyKey: 'idem-1' },
  );

  assert.equal(stream.runId, 'run-1');
  assert.equal(stream.assistantVersion, 2);

  const events: RuntimeEvent[] = [];
  for await (const event of stream) {
    events.push(event);
  }

  assert.deepEqual(
    events.map((event) => event.event_type),
    ['agent.started', 'response.delta', 'response.completed'],
  );
  assert.equal(
    (events[1]?.payload as { text: string }).text,
    'caffè 😀',
  );

  assert.equal(calls.length, 1);
  assert.equal(
    calls[0]?.url,
    'https://gateway.test/v1/conversations/conversation-1/messages',
  );
  const headers = new Headers(calls[0]?.init.headers);
  assert.equal(headers.get('authorization'), 'Bearer uai_test');
  assert.equal(headers.get('idempotency-key'), 'idem-1');
  assert.equal(headers.get('content-type'), 'application/json');
});

test('requires an explicit idempotency key for sendMessage', async () => {
  const { calls, fetch } = mockFetch(() => sseResponse([]));
  const client = clientWith(fetch);

  await assert.rejects(
    client.conversations.sendMessage(
      'conversation-1',
      { content: 'ciao' },
      { idempotencyKey: '' },
    ),
    (error: unknown) => {
      assert.ok(error instanceof ValidationError);
      assert.match(error.message, /idempotency/i);
      return true;
    },
  );
  assert.equal(calls.length, 0);
});

test('surfaces agent.failed after yielding the terminal event', async () => {
  const { fetch } = mockFetch(() =>
    sseResponse([
      eventFrame('agent.started', {}, 'e1'),
      eventFrame('agent.failed', { code: 'provider_error' }, 'e2'),
    ]),
  );
  const client = clientWith(fetch);
  const stream = await client.conversations.sendMessage(
    'conversation-1',
    { content: 'ciao' },
    { idempotencyKey: 'idem-failed' },
  );

  const events: RuntimeEvent[] = [];
  await assert.rejects(
    (async () => {
      for await (const event of stream) {
        events.push(event);
      }
    })(),
    (error: unknown) => {
      assert.ok(error instanceof AgentFailedError);
      assert.equal(error.code, 'provider_error');
      return true;
    },
  );
  assert.deepEqual(
    events.map((event) => event.event_type),
    ['agent.started', 'agent.failed'],
  );
});

test('surfaces agent.cancelled as a terminal cancellation', async () => {
  const { fetch } = mockFetch(() =>
    sseResponse([
      eventFrame('agent.started', {}, 'e1'),
      eventFrame('agent.cancelled', { code: 'cancelled' }, 'e2'),
    ]),
  );
  const client = clientWith(fetch);
  const stream = await client.conversations.sendMessage(
    'conversation-1',
    { content: 'ciao' },
    { idempotencyKey: 'idem-cancelled' },
  );

  await assert.rejects(
    (async () => {
      for await (const _event of stream) {
        // drain
      }
    })(),
    (error: unknown) => {
      assert.ok(error instanceof AgentCancelledError);
      assert.equal(error.code, 'cancelled');
      return true;
    },
  );
});

test('treats EOF without a terminal event as incomplete', async () => {
  const { fetch } = mockFetch(() =>
    sseResponse([eventFrame('agent.started', {}, 'e1')]),
  );
  const client = clientWith(fetch);
  const stream = await client.conversations.sendMessage(
    'conversation-1',
    { content: 'ciao' },
    { idempotencyKey: 'idem-eof' },
  );

  await assert.rejects(
    (async () => {
      for await (const _event of stream) {
        // drain
      }
    })(),
    (error: unknown) => {
      assert.ok(error instanceof StreamIncompleteError);
      return true;
    },
  );
});

test('aborting a stream rejects and asks the gateway to cancel the run', async () => {
  const { calls, fetch } = mockFetch((call) => {
    if (call.url.endsWith('/v1/agent-runs/run-1/cancel')) {
      return jsonResponse({ id: 'run-1', status: 'cancelled' });
    }
    return openSseResponse(eventFrame('agent.started', {}, 'e1'));
  });
  const client = clientWith(fetch);
  const controller = new AbortController();
  const stream = await client.conversations.sendMessage(
    'conversation-1',
    { content: 'ciao' },
    { idempotencyKey: 'idem-abort', signal: controller.signal },
  );
  const iterator = stream[Symbol.asyncIterator]();

  const first = await iterator.next();
  assert.equal(first.done, false);

  controller.abort();
  await assert.rejects(iterator.next(), (error: unknown) => {
    assert.ok(error instanceof AbortError);
    return true;
  });

  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.ok(
    calls.some((call) =>
      call.url.endsWith('/v1/agent-runs/run-1/cancel'),
    ),
  );
});

test('normalizes non-2xx responses into APIError', async () => {
  const { fetch } = mockFetch(() =>
    jsonResponse({ error: 'forbidden' }, 403),
  );
  const client = clientWith(fetch);

  await assert.rejects(
    client.assistants.create({
      name: 'support',
      model: 'gpt-test',
      system_prompt: 'Be helpful.',
    }),
    (error: unknown) => {
      assert.ok(error instanceof APIError);
      assert.equal(error.status, 403);
      assert.equal(error.code, 'forbidden');
      return true;
    },
  );
});

test('requires If-Match for optimistic updates', async () => {
  const { calls, fetch } = mockFetch(() => jsonResponse({}));
  const client = clientWith(fetch);

  await assert.rejects(
    client.assistants.update('assistant-1', { name: 'renamed' }, { ifMatch: '' }),
    (error: unknown) => {
      assert.ok(error instanceof ValidationError);
      assert.match(error.message, /if-match/i);
      return true;
    },
  );
  assert.equal(calls.length, 0);
});

test('uploads documents as multipart form data', async () => {
  const { calls, fetch } = mockFetch(() =>
    jsonResponse({ id: 'doc-1' }, 201),
  );
  const client = clientWith(fetch);

  await client.documents.upload({
    knowledge_base_id: 'kb-1',
    title: 'Notes',
    file: new Blob(['hello'], { type: 'text/plain' }),
  });

  assert.equal(calls.length, 1);
  const body = calls[0]?.init.body;
  assert.ok(body instanceof FormData);
  assert.equal(body.get('knowledge_base_id'), 'kb-1');
  assert.equal(body.get('title'), 'Notes');
  assert.equal(new Headers(calls[0]?.init.headers).get('content-type'), null);
});
