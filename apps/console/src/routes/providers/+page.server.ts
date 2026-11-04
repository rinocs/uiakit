import { fail, redirect } from '@sveltejs/kit';
import { clientFor } from '$lib/server/gateway';
import { canManage, denied, providerMessage } from '$lib/server/provider-access';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
  const principal = locals.session!.principal;
  const canRead = principal.role === 'admin' && principal.scopes.includes('providers:read');
  if (!canRead) {
    return { profiles: [], canManage: false, forbidden: true, error: null };
  }
  try {
    const profiles = await clientFor(locals.session!.apiKey).providers.list();
    return { profiles, canManage: canManage(locals), forbidden: false, error: null };
  } catch (error) {
    return { profiles: [], canManage: false, forbidden: false, error: providerMessage(error) };
  }
};

export const actions: Actions = {
  create: async ({ request, locals }) => {
    if (!canManage(locals)) return denied() as never;
    const data = await request.formData();
    const id = String(data.get('id') ?? '').trim();
    if (!/^[a-z0-9][a-z0-9-]{0,31}$/.test(id)) {
      return fail(422, { error: 'Identificativo non valido.' });
    }
    const name = String(data.get('name') ?? '').trim();
    if (!name) return fail(422, { error: 'Inserisci il nome.' });
    const provider = String(data.get('provider') ?? '');
    const baseUrl = String(data.get('base_url') ?? '').trim();
    if (!baseUrl) return fail(422, { error: 'Inserisci il base URL.' });
    const maxOutputTokens = Number(data.get('max_output_tokens'));
    if (!Number.isInteger(maxOutputTokens) || maxOutputTokens < 1 || maxOutputTokens > 8192) {
      return fail(422, { error: 'Max output tokens deve essere compreso tra 1 e 8192.' });
    }
    const modelsRaw = String(data.get('models') ?? '[]');
    let models: unknown[];
    try { models = JSON.parse(modelsRaw); } catch { models = []; }
    if (!Array.isArray(models) || models.length === 0) {
      return fail(422, { error: 'Aggiungi almeno un modello.' });
    }
    try {
      await clientFor(locals.session!.apiKey).providers.create({
        id, name, provider, base_url: baseUrl, max_output_tokens: maxOutputTokens, models,
      } as never);
    } catch (error) {
      return fail(502, { error: providerMessage(error) });
    }
    throw redirect(303, '/providers');
  },
  remove: async ({ request, locals }) => {
    if (!canManage(locals)) return denied() as never;
    const data = await request.formData();
    const id = String(data.get('id') ?? '');
    try {
      await clientFor(locals.session!.apiKey).providers.remove(id);
    } catch (error) {
      const code = (error as { code?: string })?.code;
      if (code === 'profile_in_use') {
        return fail(409, { error: 'Questo provider è usato da almeno un assistente: aggiorna quegli assistenti prima di eliminarlo.' });
      }
      return fail(502, { error: providerMessage(error) });
    }
    throw redirect(303, '/providers');
  },
};
