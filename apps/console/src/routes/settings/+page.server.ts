import { fail, redirect } from '@sveltejs/kit';
import { PREFERENCES_COOKIE, preferencesFrom } from '$lib/server/preferences';
import { cookieOptions } from '$lib/server/session';
import type { Actions } from './$types';

export const actions: Actions = {
  appearance: async ({ request, cookies, url }) => {
    const preferences = preferencesFrom(await request.formData());
    if (!preferences) return fail(422, { error: 'Preferenze non valide. Seleziona tema e densità tra le opzioni disponibili.' });
    cookies.set(PREFERENCES_COOKIE, JSON.stringify(preferences), {
      ...cookieOptions(url), maxAge: 60 * 60 * 24 * 365,
    });
    throw redirect(303, '/settings?saved=1');
  },
};
