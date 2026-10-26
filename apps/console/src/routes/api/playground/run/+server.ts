import { error, json } from '@sveltejs/kit';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const GET = async ({ url, locals }) => {
  const id = url.searchParams.get('id') ?? '';
  if (!id) throw error(422, 'Missing run id');
  try {
    return json(await clientFor(locals.session!.apiKey).agentRuns.get(id));
  } catch (cause) {
    throw error(502, gatewayMessage(cause));
  }
};
