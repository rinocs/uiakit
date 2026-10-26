import { error } from '@sveltejs/kit';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ params, locals, url }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const [document, exported] = await Promise.all([
      client.documents.get(params.documentId),
      client.knowledgeBases.export(params.id),
    ]);
    if (document.knowledge_base_id !== params.id) {
      throw new Error('Document does not belong to this knowledge base.');
    }
    const chunks = exported.chunks.filter(
      (chunk) => chunk.document_id === document.id,
    );
    return {
      document,
      chunks,
      selectedChunk: url.searchParams.get('chunk'),
      knowledgeBaseID: params.id,
    };
  } catch (cause) {
    throw error(404, gatewayMessage(cause));
  }
};
