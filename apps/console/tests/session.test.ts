import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SESSION_TTL_MS,
  cookieOptions,
  createSession,
  destroySession,
  getSession,
  resetSessionsForTests,
} from '../src/lib/server/session';

describe('console session store', () => {
  beforeEach(() => {
    resetSessionsForTests();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-25T10:00:00Z'));
  });
  afterEach(() => {
    vi.useRealTimers();
    resetSessionsForTests();
  });

  it('keeps the API key server-side and expires sessions', () => {
    const session = createSession('secret', {
      principal_id: 'user-1',
      role: 'admin',
      scopes: ['assistants:read'],
    });
    expect(session.id).toHaveLength(64);
    expect(getSession(session.id)?.apiKey).toBe('secret');

    vi.advanceTimersByTime(SESSION_TTL_MS + 1);
    expect(getSession(session.id)).toBeUndefined();
  });

  it('destroys sessions and uses hardened cookie options', () => {
    const session = createSession('secret', {
      principal_id: 'user-1',
      role: 'admin',
      scopes: [],
    });
    destroySession(session.id);
    expect(getSession(session.id)).toBeUndefined();
    expect(cookieOptions(new URL('https://console.example'))).toMatchObject({
      httpOnly: true,
      sameSite: 'lax',
      secure: true,
      path: '/',
    });
  });
});
