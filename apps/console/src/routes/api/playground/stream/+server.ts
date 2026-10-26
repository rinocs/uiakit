import { error } from '@sveltejs/kit';
import { gatewayUrl } from '$lib/server/gateway';

export const POST = async ({ request, locals }) => {
  const session = locals.session;
  if (!session) throw error(401, 'Unauthorized');

  let input: unknown;
  try {
    input = await request.json();
  } catch {
    throw error(422, 'Invalid JSON body');
  }
  if (!input || typeof input !== 'object') throw error(422, 'Invalid request');
  const body = input as Record<string, unknown>;
  const conversationId = typeof body.conversation_id === 'string' ? body.conversation_id : '';
  const content = typeof body.content === 'string' ? body.content : '';
  const idempotencyKey = typeof body.idempotency_key === 'string' ? body.idempotency_key : '';
  if (!conversationId || !content.trim() || content.length > 32_000 || !idempotencyKey || idempotencyKey.length > 128) {
    throw error(422, 'Invalid streaming request');
  }

  const upstream = await fetch(
    `${gatewayUrl()}/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.apiKey}`,
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({ content }),
      signal: request.signal,
    },
  );
  if (!upstream.ok) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'content-type': upstream.headers.get('content-type') ?? 'application/json',
        'cache-control': 'no-store',
      },
    });
  }
  const headers = new Headers({
    'content-type': 'text/event-stream',
    'cache-control': 'no-store',
    'x-accel-buffering': 'no',
  });
  const runId = upstream.headers.get('x-run-id');
  if (runId) headers.set('x-run-id', runId);
  return new Response(upstream.body, { status: 200, headers });
};
