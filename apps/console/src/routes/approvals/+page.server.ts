import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals }) => {
  try {
    return {
      approvals: await clientFor(locals.session!.apiKey).approvals.list(),
      principal: locals.session!.principal,
      error: null,
    };
  } catch (error) {
    return {
      approvals: [],
      principal: locals.session!.principal,
      error: gatewayMessage(error),
    };
  }
};
