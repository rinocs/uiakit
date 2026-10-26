import { redirect } from '@sveltejs/kit';
import { destroySession, SESSION_COOKIE } from '$lib/server/session';

export const POST = ({ cookies }) => {
  destroySession(cookies.get(SESSION_COOKIE));
  cookies.delete(SESSION_COOKIE, { path: '/' });
  throw redirect(303, '/login');
};
