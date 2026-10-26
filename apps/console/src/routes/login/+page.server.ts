import { fail, redirect } from '@sveltejs/kit';
import { principalFor } from '$lib/server/gateway';
import { createSession, cookieOptions, SESSION_COOKIE } from '$lib/server/session';

export const actions = {
  default: async ({ request, cookies, url }) => {
    const data = await request.formData();
    const apiKey = String(data.get('apiKey') ?? '').trim();
    if (!apiKey) {
      return fail(400, { error: 'Inserisci una API key.' });
    }
    let principal;
    try {
      principal = await principalFor(apiKey);
    } catch {
      return fail(401, { error: 'Credenziale non valida o gateway non raggiungibile.' });
    }
    if (principal.role === 'widget') {
      return fail(403, { error: 'I token widget non possono accedere alla console.' });
    }
    const session = createSession(apiKey, principal);
    cookies.set(SESSION_COOKIE, session.id, cookieOptions(url));
    throw redirect(303, '/');
  },
};
