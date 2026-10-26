import type { UaiChatElement } from './chat-widget.ts';

/** Only scoped widget credentials cross the server/browser boundary. */
export interface WidgetSession {
  baseUrl: string;
  token: string;
  conversationId: string;
  expiresAt: string;
}

export interface ConnectChatOptions {
  sessionUrl: string;
  headers?: HeadersInit;
  signal?: AbortSignal;
}

function sessionFrom(value: unknown): WidgetSession {
  if (!value || typeof value !== 'object') throw new Error('Invalid widget session.');
  const { baseUrl, token, conversationId, expiresAt } = value as Record<string, unknown>;
  if (typeof baseUrl !== 'string' || typeof token !== 'string' ||
      !/^uai_widget_[A-Za-z0-9_-]+$/.test(token) ||
      typeof conversationId !== 'string' || !conversationId.trim() ||
      typeof expiresAt !== 'string' || !Number.isFinite(Date.parse(expiresAt))) {
    throw new Error('Invalid widget session.');
  }
  const gateway = new URL(baseUrl);
  if (!['http:', 'https:'].includes(gateway.protocol) || gateway.username || gateway.password || gateway.search || gateway.hash) {
    throw new Error('Invalid widget session.');
  }
  return { baseUrl, token, conversationId, expiresAt };
}

/** Start a fresh conversation using a host application's authenticated endpoint.
 * Existing component styles, callbacks and custom backends remain host-owned.
 */
export async function connectChat(
  element: Pick<UaiChatElement, 'setConfig' | 'ownerDocument'>,
  options: ConnectChatOptions,
): Promise<Readonly<WidgetSession>> {
  const page = element.ownerDocument.location;
  const endpoint = new URL(options.sessionUrl, page.href);
  if (endpoint.origin !== page.origin || endpoint.username || endpoint.password) {
    throw new Error('The widget session endpoint must use the same origin as the page.');
  }
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');
  let session: WidgetSession;
  try {
    const response = await fetch(endpoint, {
      method: 'POST', credentials: 'same-origin', mode: 'same-origin',
      cache: 'no-store', redirect: 'error', headers, body: '{}', signal: options.signal,
    });
    if (!response.ok) throw new Error('Session request failed.');
    session = sessionFrom(await response.json());
  } catch {
    if (options.signal?.aborted) throw options.signal.reason;
    // Never expose gateway bodies, redirects, credentials or internal URLs.
    throw new Error('Unable to start chat. Please try again.');
  }
  element.setConfig({ baseUrl: session.baseUrl, token: session.token, conversationId: session.conversationId });
  return session;
}
