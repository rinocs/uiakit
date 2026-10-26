import { fail, redirect } from '@sveltejs/kit';
import type { KnowledgeBaseInput } from '@universal-ai-kit/sdk';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals }) => {
  try {
    return {
      knowledgeBases: await clientFor(locals.session!.apiKey).knowledgeBases.list(),
      principal: locals.session!.principal,
      error: null,
    };
  } catch (error) {
    return {
      knowledgeBases: [],
      principal: locals.session!.principal,
      error: gatewayMessage(error),
    };
  }
};

export const actions = {
  create: async ({ request, locals }) => {
    const data = await request.formData();
    const values = {
      name: String(data.get('name') ?? '').trim(),
      description: String(data.get('description') ?? ''),
      chunk_size: String(data.get('chunk_size') ?? '1000'),
      chunk_overlap: String(data.get('chunk_overlap') ?? '200'),
    };
    const chunkSize = Number(values.chunk_size);
    const chunkOverlap = Number(values.chunk_overlap);
    if (
      !values.name ||
      values.name.length > 200 ||
      !Number.isInteger(chunkSize) ||
      chunkSize < 100 ||
      chunkSize > 8000 ||
      !Number.isInteger(chunkOverlap) ||
      chunkOverlap < 0 ||
      chunkOverlap >= chunkSize
    ) {
      return fail(422, { error: 'Nome o configurazione di chunking non valida.', values });
    }
    const input: KnowledgeBaseInput = {
      name: values.name,
      description: values.description,
      config: { chunk_size: chunkSize, chunk_overlap: chunkOverlap },
    };
    try {
      const knowledgeBase = await clientFor(locals.session!.apiKey).knowledgeBases.create(input);
      throw redirect(303, `/knowledge-bases/${knowledgeBase.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause), values });
    }
  },
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
