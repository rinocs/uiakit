import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals, url }) => {
  try {
    const runs = await clientFor(locals.session!.apiKey).agentRuns.list();
    const conversation = url.searchParams.get('conversation');
    return {
      runs: conversation ? runs.filter((run) => run.conversation_id === conversation) : runs,
      conversation,
      error: null,
    };
  } catch (error) {
    return { runs: [], conversation: null, error: gatewayMessage(error) };
  }
};
