import { fail, redirect } from '@sveltejs/kit';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals, url }) => {
  console.log('PLAYGROUND_URL', url.href);
  const client = clientFor(locals.session!.apiKey);
  try {
    const assistants = await client.assistants.list();
    const conversationId = url.searchParams.get('conversation') ?? '';
    let messages: Array<{ role: string; content: string }> = [];
    let conversationError: string | null = null;
    if (conversationId) {
      try {
        messages = await client.conversations.messages(conversationId);
      } catch (cause) {
        conversationError = gatewayMessage(cause);
      }
    }
    return {
      assistants,
      conversationId,
      messages,
      conversationError,
      principal: locals.session!.principal,
    };
  } catch (error) {
    return {
      assistants: [],
      conversationId: '',
      messages: [],
      conversationError: gatewayMessage(error),
      principal: locals.session!.principal,
    };
  }
};

export const actions = {
  create: async ({ request, locals }) => {
    const data = await request.formData();
    const assistantId = String(data.get('assistant_id') ?? '');
    if (!assistantId) return fail(422, { error: 'Seleziona un assistente.' });
    try {
      const conversation = await clientFor(locals.session!.apiKey).conversations.create({
        assistant_id: assistantId,
      });
      throw redirect(303, `/playground?conversation=${conversation.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },
};

function statusOf(error: unknown): number {
  const status = error && typeof error === 'object' && 'status' in error
    ? Number(error.status)
    : 0;
  return status >= 400 && status < 600 ? status : 400;
}

function isRedirect(value: unknown): boolean {
  return Boolean(value && typeof value === 'object' && 'status' in value && 'location' in value);
}
