import { error, fail, redirect } from '@sveltejs/kit';
import type { AssistantPatch } from '@universal-ai-kit/sdk';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

const directivePattern = /^[a-z][a-z0-9_.-]{0,99}$/;

function directivesFrom(value: FormDataEntryValue | null): string[] | null {
  const names = String(value ?? '')
    .split(/[,\s]+/)
    .map((name) => name.trim())
    .filter(Boolean);
  if (names.length > 64) return null;
  if (names.some((name) => !directivePattern.test(name))) return null;
  return [...new Set(names)];
}

export const load = async ({ params, locals }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const [assistant, versions, models] = await Promise.all([
      client.assistants.get(params.id),
      client.assistants.versions(params.id),
      client.models.list(),
    ]);
    return { assistant, versions, models, principal: locals.session!.principal };
  } catch (cause) {
    throw error(404, gatewayMessage(cause));
  }
};

export const actions = {
  update: async ({ request, params, locals }) => {
    const data = await request.formData();
    const ifMatch = String(data.get('ifMatch') ?? '');
    const values = {
      name: String(data.get('name') ?? '').trim(),
      model: String(data.get('model') ?? '').trim(),
      system_prompt: String(data.get('system_prompt') ?? ''),
      directives: String(data.get('directives') ?? ''),
    };
    const directives = directivesFrom(data.get('directives'));
    if (!values.name || !values.model || directives === null) {
      return fail(422, { error: 'Nome, modello o direttive non validi.', values });
    }
    const patch: AssistantPatch = {
      name: values.name,
      model: values.model,
      system_prompt: values.system_prompt,
      directives,
    };
    try {
      await clientFor(locals.session!.apiKey).assistants.update(params.id, patch, {
        ifMatch,
      });
      throw redirect(303, `/assistants/${params.id}`);
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
  return Boolean(
    value &&
      typeof value === 'object' &&
      'status' in value &&
      'location' in value,
  );
}
