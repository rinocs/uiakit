import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

import type { ChatBackend, ChatStream } from '../src/chat-widget.ts';
import type { Citation, RuntimeEvent } from '@universal-ai-kit/sdk';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  pretendToBeVisual: true,
  url: 'https://host.example/',
});
const { window } = dom;
Object.assign(globalThis, {
  window,
  document: window.document,
  HTMLElement: window.HTMLElement,
  customElements: window.customElements,
  CustomEvent: window.CustomEvent,
  Event: window.Event,
  KeyboardEvent: window.KeyboardEvent,
  AbortController,
});

const { UaiChatElement } = await import('../src/chat-widget.ts');

const citation: Citation = {
  citation_id: 'citation-1',
  chunk_id: 'chunk-1',
  knowledge_base_id: 'kb-1',
  document_id: 'document-1',
  document_hash: 'a'.repeat(64),
  document_version: 1,
  page: 2,
  start: 0,
  end: 10,
};

function event(
  eventId: string,
  eventType: RuntimeEvent['event_type'],
  payload: Record<string, unknown>,
): RuntimeEvent {
  return {
    event_id: eventId,
    event_type: eventType,
    event_version: 1,
    timestamp: '2026-10-22T00:00:00Z',
    run_id: 'run-1',
    correlation_id: 'corr-1',
    payload,
  } as RuntimeEvent;
}

function streamOf(events: RuntimeEvent[]): ChatStream {
  return (async function* () {
    for (const item of events) yield item;
  })();
}

function backendOf(events: RuntimeEvent[]): ChatBackend {
  return { sendMessage: async () => streamOf(events) };
}

type Element = InstanceType<typeof UaiChatElement>;

function mount(config: Parameters<Element['setConfig']>[0]): Element {
  const element = window.document.createElement('uai-chat') as Element;
  element.setConfig({
    baseUrl: 'https://gateway.test',
    token: 'widget-token',
    conversationId: 'conversation-1',
    ...config,
  });
  window.document.body.append(element);
  return element;
}

function shadow(element: HTMLElement): ShadowRoot {
  assert.ok(element.shadowRoot);
  return element.shadowRoot;
}

async function waitFor(check: () => boolean, timeoutMs = 1500): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (check()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail('condition was not reached');
}

function submit(element: HTMLElement, text: string): void {
  const root = shadow(element);
  const textarea = root.querySelector('textarea');
  assert.ok(textarea);
  textarea.value = text;
  textarea.dispatchEvent(new window.Event('input', { bubbles: true }));
  const form = root.querySelector('form');
  assert.ok(form);
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
}

test('streams Markdown, renders authorized citations and deduplicates events', async () => {
  const element = mount({
    title: 'Supporto',
    backend: backendOf([
      event('e1', 'agent.started', {}),
      event('e2', 'response.delta', { text: 'Ciao **mondo** ' }),
      event('e2', 'response.delta', { text: 'Ciao **mondo** ' }),
      event('e3', 'response.delta', { text: '[fonte](https://example.com).' }),
      event('e4', 'response.completed', {
        text: 'Ciao **mondo** [fonte](https://example.com).',
        usage: {},
        citations: [citation, citation],
      }),
    ]),
  });
  const citations: Citation[] = [];
  element.setConfig({ onCitation: (value) => citations.push(value) });

  submit(element, 'ciao');
  await waitFor(() => shadow(element).textContent?.includes('Ciao mondo') ?? false);
  await waitFor(() => shadow(element).querySelectorAll('.citation').length === 1);

  const root = shadow(element);
  assert.equal(root.querySelector('strong')?.textContent, 'mondo');
  assert.equal(root.querySelector('a')?.getAttribute('href'), 'https://example.com/');
  assert.equal(root.querySelectorAll('.citation').length, 1);
  assert.equal(root.querySelector('.status')?.textContent, '');

  (root.querySelector('.citation') as HTMLButtonElement).click();
  assert.equal(citations.length, 1);
  assert.equal(citations[0]?.citation_id, 'citation-1');
});

test('never interprets model HTML or unsafe links', async () => {
  const element = mount({
    backend: backendOf([
      event('e1', 'response.delta', {
        text: '<img src=x onerror=alert(1)> [x](javascript:alert(1))',
      }),
      event('e2', 'response.completed', {
        text: '<img src=x onerror=alert(1)> [x](javascript:alert(1))',
        usage: {},
      }),
    ]),
  });
  submit(element, 'render');
  await waitFor(() => shadow(element).textContent?.includes('<img src=x') ?? false);

  const root = shadow(element);
  assert.equal(root.querySelector('img'), null);
  assert.equal(
    [...root.querySelectorAll('a')].some((link) =>
      (link.getAttribute('href') ?? '').includes('javascript'),
    ),
    false,
  );
});

test('handles cancel, failure and incomplete EOF states', async () => {
  const cancelBackend: ChatBackend = {
    sendMessage: async (_content, signal) =>
      (async function* () {
        yield event('e1', 'agent.started', {});
        await new Promise<never>((_resolve, reject) => {
          const fail = () => {
            const error = new Error('aborted');
            error.name = 'AbortError';
            reject(error);
          };
          if (signal.aborted) fail();
          else signal.addEventListener('abort', fail, { once: true });
        });
      })(),
  };
  const cancelled = mount({ backend: cancelBackend });
  submit(cancelled, 'stop');
  await waitFor(() => (shadow(cancelled).querySelector('.messages')?.children.length ?? 0) === 2);
  (shadow(cancelled).querySelector('button.secondary') as HTMLButtonElement).click();
  await waitFor(() => shadow(cancelled).textContent?.includes('annullata') ?? false);

  const failed = mount({
    backend: backendOf([
      event('f1', 'agent.started', {}),
      event('f2', 'agent.failed', { code: 'provider_error' }),
    ]),
  });
  submit(failed, 'fail');
  await waitFor(() => shadow(failed).textContent?.includes('provider_error') ?? false);

  const incomplete = mount({
    backend: backendOf([event('i1', 'agent.started', {})]),
  });
  submit(incomplete, 'eof');
  await waitFor(() => shadow(incomplete).textContent?.includes('incompleta') ?? false);
});

test('supports keyboard submit, Escape cancel and accessible roles', async () => {
  let observedSignal: AbortSignal | undefined;
  const backend: ChatBackend = {
    sendMessage: async (_content, signal) => {
      observedSignal = signal;
      return (async function* () {
        yield event('k1', 'agent.started', {});
        await new Promise<never>((_resolve, reject) => {
          const fail = () => {
            const error = new Error('aborted');
            error.name = 'AbortError';
            reject(error);
          };
          if (signal.aborted) fail();
          else signal.addEventListener('abort', fail, { once: true });
        });
      })();
    },
  };
  const element = mount({ backend });
  const root = shadow(element);
  assert.equal(root.querySelector('.messages')?.getAttribute('role'), 'log');
  assert.equal(root.querySelector('.status')?.getAttribute('role'), 'status');
  assert.equal(root.querySelector('textarea')?.getAttribute('aria-label'), 'Messaggio');

  const textarea = root.querySelector('textarea') as HTMLTextAreaElement;
  textarea.value = 'keyboard';
  textarea.dispatchEvent(
    new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
  );
  await waitFor(() => observedSignal !== undefined);
  assert.equal(observedSignal?.aborted, false);
  textarea.dispatchEvent(
    new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
  );
  await waitFor(() => observedSignal?.aborted === true);
  await waitFor(() => shadow(element).textContent?.includes('annullata') ?? false);
});

test('renders dark theme and responsive host markup', () => {
  const element = mount({ theme: 'dark' });
  assert.equal(element.getAttribute('theme'), 'dark');
  const style = shadow(element).querySelector('style');
  assert.match(style?.textContent ?? '', /@media \(max-width: 480px\)/);
});
