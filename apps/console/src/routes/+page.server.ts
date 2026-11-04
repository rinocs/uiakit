import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const [assistants, models, health] = await Promise.all([
      client.assistants.list(),
      client.models.list(),
      client.health().catch(() => null),
    ]);
    return { assistants, models, health, error: null };
  } catch (error) {
    return { assistants: [], models: [], health: null, error: gatewayMessage(error) };
  }
};
