import { randomBytes } from 'node:crypto';

export interface SessionPrincipal {
  principal_id: string;
  role: string;
  scopes: string[];
}

export interface Session {
  id: string;
  apiKey: string;
  principal: SessionPrincipal;
  expiresAt: number;
}

export const SESSION_COOKIE = 'uai_console_session';
export const SESSION_TTL_MS = 8 * 60 * 60 * 1000;

const sessions = new Map<string, Session>();

export function createSession(apiKey: string, principal: SessionPrincipal): Session {
  const session: Session = {
    id: randomBytes(32).toString('hex'),
    apiKey,
    principal,
    expiresAt: Date.now() + SESSION_TTL_MS,
  };
  sessions.set(session.id, session);
  return session;
}

export function getSession(id: string | undefined): Session | undefined {
  if (!id) return undefined;
  const session = sessions.get(id);
  if (!session) return undefined;
  if (session.expiresAt <= Date.now()) {
    sessions.delete(id);
    return undefined;
  }
  return session;
}

export function destroySession(id: string | undefined): void {
  if (id) sessions.delete(id);
}

export function cookieOptions(url: URL) {
  return {
    path: '/',
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: url.protocol === 'https:',
    maxAge: Math.floor(SESSION_TTL_MS / 1000),
  };
}

/** Test-only isolation. */
export function resetSessionsForTests(): void {
  sessions.clear();
}
