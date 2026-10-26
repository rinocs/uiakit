import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals }) => {
  try {
    return { models: await clientFor(locals.session!.apiKey).models.list(), error: null };
  } catch (error) {
    return { models: [], error: gatewayMessage(error) };
  }
};
