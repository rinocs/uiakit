import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals }) => {
  try {
    return {
      tools: await clientFor(locals.session!.apiKey).tools.list(),
      principal: locals.session!.principal,
      error: null,
    };
  } catch (error) {
    return { tools: [], principal: locals.session!.principal, error: gatewayMessage(error) };
  }
};
