import { error } from '@sveltejs/kit';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const GET = async ({ params, locals }) => {
  try {
    const exported = await clientFor(locals.session!.apiKey).knowledgeBases.export(params.id);
    return new Response(JSON.stringify(exported, null, 2), {
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'content-disposition': `attachment; filename="knowledge-base-${params.id}.json"`,
        'cache-control': 'no-store',
      },
    });
  } catch (cause) {
    throw error(502, gatewayMessage(cause));
  }
};
