import type { Handle } from '@sveltejs/kit';
import { redirect } from '@sveltejs/kit';
import { getSession, SESSION_COOKIE } from '$lib/server/session';

export const handle: Handle = async ({ event, resolve }) => {
  const session = getSession(event.cookies.get(SESSION_COOKIE));
  if (session) event.locals.session = session;

  const path = event.url.pathname;
  if (!session && path !== '/login') {
    throw redirect(303, '/login');
  }
  if (session && path === '/login') {
    throw redirect(303, '/');
  }

  const response = await resolve(event);
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('Referrer-Policy', 'no-referrer');
  response.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  return response;
};
