import { error, fail, redirect } from '@sveltejs/kit';
import type { AssistantPatch } from '@universal-ai-kit/sdk';
import { clientFor, gatewayMessage } from '$lib/server/gateway';
import { assistantSettingsFrom } from '$lib/server/assistant-settings';

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
    const catalogs = await Promise.allSettled([client.tools.list(), client.knowledgeBases.list()]);
    const tools = catalogs[0].status === 'fulfilled' ? catalogs[0].value : [];
    const knowledgeBases = catalogs[1].status === 'fulfilled' ? catalogs[1].value : [];
    const catalogWarning = catalogs.some((result) => result.status === 'rejected')
      ? 'Alcuni cataloghi non sono disponibili. Le selezioni esistenti vengono mantenute; puoi modificare gli altri parametri.' : null;
    return { assistant, versions, models, tools, knowledgeBases, catalogWarning, principal: locals.session!.principal };
  } catch (cause) {
    throw error(404, gatewayMessage(cause));
  }
};

export const actions = {
  update: async ({ request, params, locals }) => {
    if (locals.session!.principal.role === 'reader') throw error(403, 'Accesso in sola lettura.');
    const data = await request.formData();
    const settings = assistantSettingsFrom(data);
    const ifMatch = String(data.get('ifMatch') ?? '');
    const values = {
      ...settings.values,
      name: String(data.get('name') ?? '').trim(),
      model: String(data.get('model') ?? '').trim(),
      system_prompt: String(data.get('system_prompt') ?? ''),
      directives: String(data.get('directives') ?? ''),
    };
    const directives = directivesFrom(data.get('directives'));
    if (!values.name || values.name.length > 200 || !values.model || values.system_prompt.length > 16000 || directives === null) {
      return fail(422, { error: 'Nome, modello o direttive non validi.', values });
    }
    if (settings.error) return fail(422, { error: settings.error, values });
    const patch: AssistantPatch = {
      ...settings.patch,
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
