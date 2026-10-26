import { PREFERENCES_COOKIE, readPreferences } from '$lib/server/preferences';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ locals, cookies }) => ({
  principal: locals.session?.principal ?? null,
  preferences: readPreferences(cookies.get(PREFERENCES_COOKIE)),
});
