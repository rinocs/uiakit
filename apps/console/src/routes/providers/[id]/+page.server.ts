import { fail, redirect } from '@sveltejs/kit';
import { error } from '@sveltejs/kit';
import { clientFor } from '$lib/server/gateway';
import { canManage, providerMessage } from '$lib/server/provider-access';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, params, url }) => {
  const canRead = locals.session!.principal.role === 'admin' && locals.session!.principal.scopes.includes('providers:read');
  if (!canRead) return { profile: null, canManage: false, forbidden: true, error: null, saved: false };
  try {
    const profile = await clientFor(locals.session!.apiKey).providers.get(params.id);
    return { profile, canManage: canManage(locals), forbidden: false, error: null, saved: url.searchParams.get('saved') === '1' };
  } catch (e) {
    if ((e as { status?: number })?.status === 404) throw error(404, 'Not found');
    return { profile: null, canManage: false, forbidden: false, error: providerMessage(e), saved: false };
  }
};

export const actions: Actions = {
  save: async ({ request, locals, params }) => {
    if (!canManage(locals)) return fail(403, { error: 'forbidden' });
    const data = await request.formData();
    const name = String(data.get('name') ?? '').trim();
    const provider = String(data.get('provider') ?? '');
    const baseUrl = String(data.get('base_url') ?? '').trim();
    const maxOutputTokens = Number(data.get('max_output_tokens'));
    const models = JSON.parse(String(data.get('models') ?? '[]'));
    const ifMatch = `"${String(data.get('revision') ?? '0')}"`;
    try {
      await clientFor(locals.session!.apiKey).providers.update(params.id, { name, provider, base_url: baseUrl, max_output_tokens: maxOutputTokens, models }, { ifMatch } as never);
    } catch (e) {
      return fail(502, { error: providerMessage(e) });
    }
    throw redirect(303, `/providers/${params.id}?saved=1`);
  },
  saveSecret: async ({ request, locals, params }) => {
    if (!canManage(locals)) return fail(403, { error: 'forbidden' });
    const data = await request.formData();
    const value = String(data.get('value') ?? '').trim();
    const ref = String(data.get('ref') ?? '').trim();
    try {
      const client = clientFor(locals.session!.apiKey);
      if (value) {
        await (client.providers as any).setSecret(params.id, { source: 'stored', value });
      } else if (ref) {
        await (client.providers as any).setSecret(params.id, { source: 'env', ref });
      } else {
        return fail(422, { error: 'Inserisci una chiave oppure una variabile d\'ambiente.' });
      }
    } catch (e) {
      return fail(502, { error: providerMessage(e) });
    }
    throw redirect(303, `/providers/${params.id}?saved=secret`);
  },
  clearSecret: async ({ request, locals, params }) => {
    if (!canManage(locals)) return fail(403, { error: 'forbidden' });
    try {
      await (clientFor(locals.session!.apiKey).providers as any).clearSecret(params.id);
    } catch (e) {
      return fail(502, { error: providerMessage(e) });
    }
    throw redirect(303, `/providers/${params.id}?saved=secret`);
  },
};
