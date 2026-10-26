import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';
import { connectChat } from '../src/session.ts';

const document = new JSDOM('<!doctype html>', { url: 'https://host.example/support' }).window.document;
const session = {
  baseUrl: 'https://gateway.example', token: 'uai_widget_test-token',
  conversationId: '00000000-0000-4000-8000-000000000001', expiresAt: '2026-10-26T12:00:00Z',
};
function target() {
  const configs: unknown[] = [];
  return { ownerDocument: document, setConfig(config: unknown) { configs.push(config); }, configs };
}

test('connects using a same-origin session with CSRF headers and exposes only widget config', async (t) => {
  const element = target();
  t.mock.method(globalThis, 'fetch', async (url: URL, init: RequestInit) => {
    assert.equal(url.href, 'https://host.example/widget/session');
    assert.equal(init.method, 'POST');
    assert.equal(init.credentials, 'same-origin');
    assert.equal(init.redirect, 'error');
    assert.equal(new Headers(init.headers).get('X-CSRF-TOKEN'), 'csrf-test');
    assert.equal(new Headers(init.headers).get('Content-Type'), 'application/json');
    return Response.json({ ...session, api_key: 'must-not-propagate', theme: 'untrusted' });
  });
  const connected = await connectChat(element, { sessionUrl: '/widget/session', headers: { 'X-CSRF-TOKEN': 'csrf-test' } });
  assert.deepEqual(connected, session);
  assert.deepEqual(element.configs, [{ baseUrl: session.baseUrl, token: session.token, conversationId: session.conversationId }]);
});

test('rejects cross-origin or credential-bearing bootstrap URLs before making any request', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => { throw new Error('must not fetch'); });
  for (const sessionUrl of ['https://evil.example/session', 'https://user:secret@host.example/session']) {
    await assert.rejects(connectChat(target(), { sessionUrl }), /same origin/i);
  }
  assert.equal(fetch.mock.callCount(), 0);
});

test('rejects bad server responses and never applies partial configuration or leaks upstream bodies', async (t) => {
  const element = target();
  for (const response of [
    new Response('server-key-secret', { status: 500 }),
    Response.json({ ...session, token: 'admin-key-secret' }),
    Response.json({ ...session, baseUrl: 'javascript:alert(1)' }),
    Response.json({ ...session, conversationId: '' }),
    Response.json({ ...session, expiresAt: 'invalid' }),
    Response.json(null),
  ]) {
    const mocked = t.mock.method(globalThis, 'fetch', async () => response);
    await assert.rejects(connectChat(element, { sessionUrl: '/widget/session' }), (error: Error) => {
      assert.doesNotMatch(error.message, /server-key-secret|admin-key-secret/);
      return true;
    });
    mocked.mock.restore();
  }
  assert.deepEqual(element.configs, []);
});

test('passes cancellation to the session request and leaves configuration untouched', async (t) => {
  const controller = new AbortController();
  controller.abort();
  const element = target();
  t.mock.method(globalThis, 'fetch', async (_url: URL, init: RequestInit) => {
    assert.equal(init.signal, controller.signal);
    throw controller.signal.reason;
  });
  await assert.rejects(connectChat(element, { sessionUrl: '/widget/session', signal: controller.signal }), { name: 'AbortError' });
  assert.deepEqual(element.configs, []);
});
