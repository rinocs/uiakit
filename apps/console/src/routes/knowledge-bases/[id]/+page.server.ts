import { error, fail, redirect } from '@sveltejs/kit';
import type {
  KnowledgeBasePatch,
  KnowledgeBaseVersionInput,
} from '@universal-ai-kit/sdk';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

const MAX_FILE_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ['.txt', '.md', '.markdown', '.html', '.htm', '.pdf', '.docx'];
const ALLOWED_MIME = new Set([
  'text/plain',
  'text/markdown',
  'text/html',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

export const load = async ({ params, locals, url }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const [kb, versions, documents, assistants] = await Promise.all([
      client.knowledgeBases.get(params.id),
      client.knowledgeBases.versions(params.id),
      client.documents.list(params.id),
      client.assistants.list(),
    ]);
    const jobs = await Promise.all(
      documents.map((document) => client.documents.job(document.id).catch(() => null)),
    );
    return {
      knowledgeBase: kb,
      versions,
      documents: documents.map((document, index) => ({ document, job: jobs[index] })),
      assistants,
      principal: locals.session!.principal,
      uploaded: url.searchParams.get('uploaded'),
      reindexed: url.searchParams.get('reindexed') === '1',
    };
  } catch (cause) {
    throw error(404, gatewayMessage(cause));
  }
};

export const actions = {
  update: async ({ request, params, locals }) => {
    const data = await request.formData();
    const ifMatch = String(data.get('ifMatch') ?? '');
    const name = String(data.get('name') ?? '').trim();
    const description = String(data.get('description') ?? '');
    if (!name || name.length > 200) {
      return fail(422, { error: 'Nome non valido.' });
    }
    const patch: KnowledgeBasePatch = { name, description };
    try {
      await clientFor(locals.session!.apiKey).knowledgeBases.update(params.id, patch, { ifMatch });
      throw redirect(303, `/knowledge-bases/${params.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },

  reindex: async ({ request, params, locals }) => {
    const data = await request.formData();
    const ifMatch = String(data.get('ifMatch') ?? '');
    const chunkSize = Number(data.get('chunk_size'));
    const chunkOverlap = Number(data.get('chunk_overlap'));
    if (
      !Number.isInteger(chunkSize) ||
      chunkSize < 100 ||
      chunkSize > 8000 ||
      !Number.isInteger(chunkOverlap) ||
      chunkOverlap < 0 ||
      chunkOverlap >= chunkSize
    ) {
      return fail(422, { error: 'Configurazione chunk non valida.' });
    }
    const input: KnowledgeBaseVersionInput = {
      config: { chunk_size: chunkSize, chunk_overlap: chunkOverlap },
    };
    try {
      await clientFor(locals.session!.apiKey).knowledgeBases.createVersion(params.id, input, { ifMatch });
      throw redirect(303, `/knowledge-bases/${params.id}?reindexed=1`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },

  delete: async ({ request, params, locals }) => {
    const data = await request.formData();
    if (String(data.get('confirm') ?? '') !== 'yes') {
      return fail(400, { error: 'Conferma la cancellazione.' });
    }
    try {
      await clientFor(locals.session!.apiKey).knowledgeBases.delete(params.id, {
        ifMatch: String(data.get('ifMatch') ?? ''),
      });
      throw redirect(303, '/knowledge-bases');
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },

  upload: async ({ request, params, locals }) => {
    const data = await request.formData();
    const file = data.get('file');
    const title = String(data.get('title') ?? '').trim();
    if (!(file instanceof Blob) || file.size === 0) {
      return fail(422, { uploadError: 'Seleziona un file.' });
    }
    if (file.size > MAX_FILE_BYTES) {
      return fail(422, { uploadError: 'Il file supera il limite di 20 MiB.' });
    }
    const filename = 'name' in file && typeof file.name === 'string' ? file.name : 'document';
    const extension = filename.slice(filename.lastIndexOf('.')).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      return fail(422, { uploadError: 'Formato non supportato: usa TXT, Markdown, HTML, PDF o DOCX.' });
    }
    if (file.type && !ALLOWED_MIME.has(file.type)) {
      return fail(422, { uploadError: 'Tipo MIME non supportato dal gateway.' });
    }
    try {
      const document = await clientFor(locals.session!.apiKey).documents.upload({
        knowledge_base_id: params.id,
        title: title || undefined,
        file,
        filename,
      });
      throw redirect(303, `/knowledge-bases/${params.id}?uploaded=${document.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { uploadError: gatewayMessage(cause) });
    }
  },

  associate: async ({ request, params, locals }) => {
    const data = await request.formData();
    const selected = new Set(data.getAll('assistant_ids').map(String));
    const client = clientFor(locals.session!.apiKey);
    try {
      const assistants = await client.assistants.list();
      const changed = assistants.filter((assistant) => {
        const current = assistant.knowledge_base_ids ?? [];
        const desired = selected.has(assistant.id)
          ? [...new Set([...current, params.id])]
          : current.filter((id) => id !== params.id);
        return desired.length !== current.length || desired.some((id, index) => id !== current[index]);
      });
      for (const assistant of changed) {
        const current = assistant.knowledge_base_ids ?? [];
        const desired = selected.has(assistant.id)
          ? [...new Set([...current, params.id])]
          : current.filter((id) => id !== params.id);
        await client.assistants.update(
          assistant.id,
          { knowledge_base_ids: desired },
          { ifMatch: JSON.stringify(String(assistant.version)) },
        );
      }
      throw redirect(303, `/knowledge-bases/${params.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { associationError: gatewayMessage(cause) });
    }
  },

  cancelJob: async ({ request, params, locals }) => {
    const data = await request.formData();
    const documentId = String(data.get('document_id') ?? '');
    try {
      await clientFor(locals.session!.apiKey).documents.cancelJob(documentId);
      throw redirect(303, `/knowledge-bases/${params.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },

  deleteDocument: async ({ request, params, locals }) => {
    const data = await request.formData();
    if (String(data.get('confirm') ?? '') !== 'yes') {
      return fail(400, { error: 'Conferma la cancellazione del documento.' });
    }
    try {
      await clientFor(locals.session!.apiKey).documents.delete(String(data.get('document_id') ?? ''));
      throw redirect(303, `/knowledge-bases/${params.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
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
