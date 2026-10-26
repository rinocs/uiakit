import { fail, redirect } from '@sveltejs/kit';
import type { AssistantInput } from '@universal-ai-kit/sdk';
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

export const load = async ({ locals }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const [assistants, models] = await Promise.all([
      client.assistants.list(),
      client.models.list(),
    ]);
    return { assistants, models, principal: locals.session!.principal, error: null };
  } catch (error) {
    return {
      assistants: [],
      models: [],
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
      model: String(data.get('model') ?? '').trim(),
      system_prompt: String(data.get('system_prompt') ?? ''),
      directives: String(data.get('directives') ?? ''),
    };
    const directives = directivesFrom(data.get('directives'));
    if (!values.name || values.name.length > 200 || !values.model || directives === null) {
      return fail(422, { error: 'Nome, modello o direttive non validi.', values });
    }
    const input: AssistantInput = {
      name: values.name,
      model: values.model,
      system_prompt: values.system_prompt,
      directives,
    };
    try {
      const assistant = await clientFor(locals.session!.apiKey).assistants.create(input);
      throw redirect(303, `/assistants/${assistant.id}`);
    } catch (error) {
      if (isRedirect(error)) throw error;
      return fail(statusOf(error), { error: gatewayMessage(error), values });
    }
  },
};

function statusOf(error: unknown): number {
  const status = error && typeof error === 'object' && 'status' in error
    ? Number(error.status)
    : 0;
  return status >= 400 && status < 600 ? status : 400;
}

function isRedirect(error: unknown): boolean {
  return Boolean(
    error &&
      typeof error === 'object' &&
      'status' in error &&
      'location' in error,
  );
}
