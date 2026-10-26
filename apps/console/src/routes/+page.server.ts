import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const [assistants, models] = await Promise.all([
      client.assistants.list(),
      client.models.list(),
    ]);
    return { assistants, models, error: null };
  } catch (error) {
    return { assistants: [], models: [], error: gatewayMessage(error) };
  }
};
