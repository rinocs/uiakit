import { error, fail, redirect } from '@sveltejs/kit';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const actions = {
  delete: async ({ params, locals }) => {
    try {
      await clientFor(locals.session!.apiKey).conversations.delete(params.id);
      throw redirect(303, '/runs');
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },
};

export const load = async ({ params, locals }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const [messages, runs] = await Promise.all([
      client.conversations.messages(params.id),
      client.agentRuns.list(),
    ]);
    return {
      conversationId: params.id,
      messages,
      runs: runs.filter((run) => run.conversation_id === params.id),
      principal: locals.session!.principal,
    };
  } catch (cause) {
    throw error(404, gatewayMessage(cause));
  }
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
