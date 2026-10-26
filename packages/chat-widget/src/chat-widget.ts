import {
  AgentCancelledError,
  AgentFailedError,
  StreamIncompleteError,
  UniversalAIKit,
} from '@universal-ai-kit/sdk';
import type { Citation, RuntimeEvent } from '@universal-ai-kit/sdk';
import { renderMarkdown } from './markdown.ts';

export interface ChatStream extends AsyncIterable<RuntimeEvent> {
  readonly runId?: string;
}

export interface ChatBackend {
  sendMessage(content: string, signal: AbortSignal): Promise<ChatStream>;
}

export interface UaiChatConfig {
  baseUrl?: string;
  token?: string;
  conversationId?: string;
  title?: string;
  placeholder?: string;
  theme?: 'light' | 'dark' | Record<string, string>;
  backend?: ChatBackend;
  idempotencyKey?: () => string;
  onEvent?: (event: RuntimeEvent) => void;
  onCitation?: (citation: Citation) => void;
  onError?: (error: unknown) => void;
}

type MessageStatus =
  | 'streaming'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'incomplete';

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  status?: MessageStatus;
  error?: string;
  citations?: Citation[];
}

const DEFAULT_TITLE = 'Assistente';
const DEFAULT_PLACEHOLDER = 'Scrivi un messaggio…';

const STYLES = `
  :host {
    --uai-bg: #ffffff;
    --uai-fg: #172033;
    --uai-muted: #5b667a;
    --uai-border: #d8deea;
    --uai-accent: #155eef;
    --uai-accent-fg: #ffffff;
    --uai-user-bg: #eef4ff;
    --uai-assistant-bg: #f7f8fb;
    --uai-error: #b42318;
    --uai-radius: 16px;
    display: block;
    contain: content;
    color: var(--uai-fg);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  :host([theme="dark"]) {
    --uai-bg: #111827;
    --uai-fg: #f3f4f6;
    --uai-muted: #a7b0c0;
    --uai-border: #344054;
    --uai-accent: #84adff;
    --uai-accent-fg: #0b1220;
    --uai-user-bg: #1d2b4b;
    --uai-assistant-bg: #1a2233;
    --uai-error: #fda29b;
  }
  * { box-sizing: border-box; }
  .root {
    display: flex;
    flex-direction: column;
    min-height: 320px;
    max-height: min(720px, 90vh);
    background: var(--uai-bg);
    border: 1px solid var(--uai-border);
    border-radius: var(--uai-radius);
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.9rem 1rem;
    border-bottom: 1px solid var(--uai-border);
  }
  h2 { margin: 0; font-size: 1rem; line-height: 1.3; }
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .message {
    max-width: 92%;
    padding: 0.7rem 0.85rem;
    border-radius: 12px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
  .message[data-role="user"] {
    align-self: flex-end;
    background: var(--uai-user-bg);
  }
  .message[data-role="assistant"] {
    align-self: flex-start;
    background: var(--uai-assistant-bg);
    border: 1px solid var(--uai-border);
  }
  .message p { margin: 0 0 0.6rem; }
  .message p:last-child { margin-bottom: 0; }
  .message pre {
    overflow-x: auto;
    padding: 0.65rem;
    border-radius: 8px;
    background: rgba(0, 0, 0, 0.08);
  }
  .message code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .message a { color: var(--uai-accent); }
  .message blockquote {
    margin: 0.4rem 0;
    padding-left: 0.7rem;
    border-left: 3px solid var(--uai-border);
    color: var(--uai-muted);
  }
  .citations {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin: 0.55rem 0 0;
    padding: 0;
    list-style: none;
  }
  .citation {
    border: 1px solid var(--uai-border);
    border-radius: 999px;
    background: transparent;
    color: var(--uai-fg);
    padding: 0.2rem 0.55rem;
    font: inherit;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .citation:focus-visible,
  button:focus-visible,
  textarea:focus-visible {
    outline: 2px solid var(--uai-accent);
    outline-offset: 2px;
  }
  .message[data-status="failed"] .error,
  .message[data-status="incomplete"] .error {
    color: var(--uai-error);
    font-size: 0.85rem;
    margin-top: 0.4rem;
  }
  .status {
    min-height: 1.25rem;
    padding: 0 1rem 0.4rem;
    color: var(--uai-muted);
    font-size: 0.8rem;
  }
  form {
    display: flex;
    gap: 0.5rem;
    padding: 0.75rem 1rem 1rem;
    border-top: 1px solid var(--uai-border);
  }
  textarea {
    flex: 1;
    min-height: 2.5rem;
    max-height: 8rem;
    resize: vertical;
    border: 1px solid var(--uai-border);
    border-radius: 10px;
    padding: 0.55rem 0.7rem;
    color: var(--uai-fg);
    background: var(--uai-bg);
    font: inherit;
  }
  button {
    border: 0;
    border-radius: 10px;
    padding: 0.55rem 0.9rem;
    font: inherit;
    cursor: pointer;
    background: var(--uai-accent);
    color: var(--uai-accent-fg);
  }
  button.secondary {
    background: transparent;
    color: var(--uai-fg);
    border: 1px solid var(--uai-border);
  }
  button:disabled { opacity: 0.55; cursor: not-allowed; }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
  @media (max-width: 480px) {
    .root { max-height: 100vh; border-radius: 0; min-height: 100vh; }
    .message { max-width: 100%; }
    form { flex-wrap: wrap; }
    textarea { flex-basis: 100%; }
    form button { flex: 1; }
  }
  @media (prefers-reduced-motion: no-preference) {
    .message { animation: uai-in 120ms ease-out; }
    @keyframes uai-in { from { opacity: 0; transform: translateY(2px); } to { opacity: 1; transform: none; } }
  }
`;

export class UaiChatElement extends HTMLElement {
  static get observedAttributes(): string[] {
    return ['base-url', 'token', 'conversation-id', 'title', 'placeholder', 'theme'];
  }

  readonly #root: ShadowRoot;
  #config: UaiChatConfig = {};
  #backend: ChatBackend | undefined;
  #messages: ChatMessage[] = [];
  #controller: AbortController | undefined;
  #sending = false;
  #shell: {
    root: HTMLDivElement;
    title: HTMLHeadingElement;
    messages: HTMLDivElement;
    status: HTMLDivElement;
    textarea: HTMLTextAreaElement;
    send: HTMLButtonElement;
    cancel: HTMLButtonElement;
  } | undefined;

  constructor() {
    super();
    this.#root = this.attachShadow({ mode: 'open' });
  }

  connectedCallback(): void {
    this.#ensureShell();
    this.#render();
  }

  attributeChangedCallback(name: string, _old: string | null, value: string | null): void {
    if (!this.isConnected) return;
    switch (name) {
      case 'base-url':
        this.setConfig({ baseUrl: value ?? undefined });
        break;
      case 'token':
        this.setConfig({ token: value ?? undefined });
        break;
      case 'conversation-id':
        this.setConfig({ conversationId: value ?? undefined });
        break;
      case 'title':
        this.setConfig({ title: value ?? undefined });
        break;
      case 'placeholder':
        this.setConfig({ placeholder: value ?? undefined });
        break;
      case 'theme':
        this.setConfig({ theme: value === 'dark' ? 'dark' : value === 'light' ? 'light' : undefined });
        break;
    }
  }

  setConfig(config: UaiChatConfig): void {
    const resetBackend =
      config.baseUrl !== undefined && config.baseUrl !== this.#config.baseUrl ||
      config.token !== undefined && config.token !== this.#config.token ||
      config.backend !== undefined && config.backend !== this.#config.backend;
    this.#config = { ...this.#config, ...config };
    if (resetBackend) this.#backend = undefined;
    if (this.#shell) this.#render();
  }

  getConfig(): Readonly<UaiChatConfig> {
    return { ...this.#config };
  }

  #ensureShell(): void {
    if (this.#shell) return;
    const document = this.ownerDocument;
    const style = document.createElement('style');
    style.textContent = STYLES;

    const root = document.createElement('div');
    root.className = 'root';

    const header = document.createElement('header');
    const title = document.createElement('h2');
    title.id = 'uai-title';
    header.append(title);

    const messages = document.createElement('div');
    messages.className = 'messages';
    messages.setAttribute('role', 'log');
    messages.setAttribute('aria-live', 'polite');
    messages.setAttribute('aria-relevant', 'additions text');
    messages.setAttribute('aria-labelledby', 'uai-title');

    const status = document.createElement('div');
    status.className = 'status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');

    const form = document.createElement('form');
    form.noValidate = true;
    const textarea = document.createElement('textarea');
    textarea.rows = 2;
    textarea.setAttribute('aria-label', 'Messaggio');
    textarea.setAttribute('autocomplete', 'off');
    const send = document.createElement('button');
    send.type = 'submit';
    send.textContent = 'Invia';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'secondary';
    cancel.textContent = 'Annulla';
    cancel.hidden = true;
    form.append(textarea, send, cancel);

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.#send();
    });
    textarea.addEventListener('input', () => {
      if (this.#shell && !this.#sending) {
        this.#shell.send.disabled = !this.#shell.textarea.value.trim();
      }
    });
    textarea.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        void this.#send();
      } else if (event.key === 'Escape') {
        this.#cancel();
      }
    });
    cancel.addEventListener('click', () => this.#cancel());

    root.append(header, messages, status, form);
    this.#root.replaceChildren(style, root);
    this.#shell = { root, title, messages, status, textarea, send, cancel };
  }

  async #send(): Promise<void> {
    if (this.#sending || !this.#shell) return;
    const content = this.#shell.textarea.value.trim();
    if (!content) return;
    const config = this.#config;
    if (!config.backend && (!config.baseUrl || !config.token || !config.conversationId)) {
      this.#setStatus('Configurazione mancante: baseUrl, token e conversationId sono obbligatori.');
      return;
    }

    this.#shell.textarea.value = '';
    this.#messages.push({ role: 'user', text: content });
    const assistant: ChatMessage = { role: 'assistant', text: '', status: 'streaming' };
    this.#messages.push(assistant);
    this.#sending = true;
    this.#controller = new AbortController();
    this.#shell.send.disabled = true;
    this.#shell.textarea.disabled = true;
    this.#shell.cancel.hidden = false;
    this.#setStatus('Sto rispondendo…');
    this.#render();

    const controller = this.#controller;
    try {
      const backend = this.#getBackend();
      const stream = await backend.sendMessage(content, controller.signal);
      const seen = new Set<string>();
      for await (const event of stream) {
        if (controller.signal.aborted) {
          assistant.status = 'cancelled';
          assistant.error = 'Risposta annullata.';
          this.#setStatus(assistant.error);
          break;
        }
        if (seen.has(event.event_id)) continue;
        seen.add(event.event_id);
        this.#emitEvent(event);
        if (event.event_type === 'response.delta') {
          assistant.text += event.payload.text;
          this.#render();
        } else if (event.event_type === 'response.completed') {
          assistant.text = event.payload.text || assistant.text;
          assistant.citations = event.payload.citations ?? [];
          assistant.status = 'completed';
          this.#setStatus('');
          break;
        } else if (event.event_type === 'agent.failed') {
          assistant.status = 'failed';
          assistant.error = `Errore del modello (${event.payload.code}).`;
          this.#setStatus(assistant.error);
          break;
        } else if (event.event_type === 'agent.cancelled') {
          assistant.status = 'cancelled';
          assistant.error = 'Risposta annullata.';
          this.#setStatus(assistant.error);
          break;
        }
      }
      if (assistant.status === 'streaming') {
        assistant.status = 'incomplete';
        assistant.error = 'La risposta è incompleta: è terminata senza un evento finale.';
        this.#setStatus(assistant.error);
      }
    } catch (error) {
      if (controller.signal.aborted) {
        assistant.status = 'cancelled';
        assistant.error = 'Risposta annullata.';
        this.#setStatus(assistant.error);
      } else if (error instanceof StreamIncompleteError) {
        assistant.status = 'incomplete';
        assistant.error = 'La risposta è incompleta. Riprova.';
        this.#setStatus(assistant.error);
      } else if (error instanceof AgentFailedError || error instanceof AgentCancelledError) {
        assistant.status = error instanceof AgentCancelledError ? 'cancelled' : 'failed';
        assistant.error = error.message;
        this.#setStatus(assistant.error);
      } else {
        assistant.status = 'failed';
        assistant.error = 'Impossibile completare la risposta.';
        this.#setStatus(assistant.error);
        this.#emitError(error);
      }
    } finally {
      this.#sending = false;
      this.#controller = undefined;
      if (this.#shell) {
        this.#shell.send.disabled = false;
        this.#shell.textarea.disabled = false;
        this.#shell.cancel.hidden = true;
        this.#render();
        this.#shell.textarea.focus();
      }
    }
  }

  #getBackend(): ChatBackend {
    if (this.#config.backend) return this.#config.backend;
    if (this.#backend) return this.#backend;
    const { baseUrl, token, conversationId } = this.#config;
    if (!baseUrl || !token || !conversationId) {
      throw new Error('Missing widget configuration.');
    }
    const client = new UniversalAIKit({ baseUrl, apiKey: token });
    this.#backend = {
      sendMessage: (content, signal) =>
        client.conversations.sendMessage(
          conversationId,
          { content },
          {
            idempotencyKey: this.#config.idempotencyKey?.() ?? defaultIdempotencyKey(),
            signal,
          },
        ),
    };
    return this.#backend;
  }

  #cancel(): void {
    this.#controller?.abort();
  }

  #emitEvent(event: RuntimeEvent): void {
    try {
      this.#config.onEvent?.(event);
    } catch {
      // Consumer callbacks must not break the chat.
    }
    this.dispatchEvent(
      new CustomEvent('uai:event', { detail: event, bubbles: true, composed: true }),
    );
  }

  #emitError(error: unknown): void {
    try {
      this.#config.onError?.(error);
    } catch {
      // Consumer callbacks must not break the chat.
    }
    this.dispatchEvent(
      new CustomEvent('uai:error', { detail: error, bubbles: true, composed: true }),
    );
  }

  #citation(citation: Citation): void {
    try {
      this.#config.onCitation?.(citation);
    } catch {
      // Consumer callbacks must not break the chat.
    }
    this.dispatchEvent(
      new CustomEvent('uai:citation', {
        detail: citation,
        bubbles: true,
        composed: true,
      }),
    );
  }

  #setStatus(message: string): void {
    if (this.#shell) this.#shell.status.textContent = message;
  }

  #render(): void {
    if (!this.#shell) return;
    const { title, messages, textarea, send } = this.#shell;
    title.textContent = this.#config.title ?? DEFAULT_TITLE;
    textarea.placeholder = this.#config.placeholder ?? DEFAULT_PLACEHOLDER;
    const theme = this.#config.theme;
    if (theme === 'dark' || theme === 'light') {
      if (this.getAttribute('theme') !== theme) this.setAttribute('theme', theme);
    } else if (theme && typeof theme === 'object') {
      if (this.hasAttribute('theme')) this.removeAttribute('theme');
      for (const [name, value] of Object.entries(theme)) {
        if (/^--uai-[a-z-]+$/.test(name)) this.style.setProperty(name, value);
      }
    }
    if (!this.#sending) send.disabled = !textarea.value.trim();

    messages.replaceChildren();
    for (const message of this.#messages) {
      const article = this.ownerDocument.createElement('article');
      article.className = 'message';
      article.dataset.role = message.role;
      if (message.status) article.dataset.status = message.status;
      if (message.role === 'user') {
        article.textContent = message.text;
      } else {
        article.append(renderMarkdown(message.text, this.ownerDocument));
        if (message.citations && message.citations.length > 0) {
          const list = this.ownerDocument.createElement('ol');
          list.className = 'citations';
          list.setAttribute('aria-label', 'Citazioni');
          for (const citation of dedupeCitations(message.citations)) {
            const item = this.ownerDocument.createElement('li');
            const button = this.ownerDocument.createElement('button');
            button.type = 'button';
            button.className = 'citation';
            button.textContent = citationLabel(citation);
            button.setAttribute(
              'aria-label',
              `Apri fonte ${citationLabel(citation)}`,
            );
            button.addEventListener('click', () => this.#citation(citation));
            item.append(button);
            list.append(item);
          }
          article.append(list);
        }
        if (message.error) {
          const error = this.ownerDocument.createElement('div');
          error.className = 'error';
          error.setAttribute('role', 'alert');
          error.textContent = message.error;
          article.append(error);
        }
      }
      messages.append(article);
    }
    messages.scrollTop = messages.scrollHeight;
  }
}

function defaultIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID();
  }
  return `widget-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function citationLabel(citation: Citation): string {
  const page = citation.page ? `, p. ${citation.page}` : '';
  return `${citation.document_id.slice(0, 8)}${page}`;
}

function dedupeCitations(citations: Citation[]): Citation[] {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    if (seen.has(citation.citation_id)) return false;
    seen.add(citation.citation_id);
    return true;
  });
}

export function defineUaiChat(tagName = 'uai-chat'): void {
  if (typeof customElements === 'undefined') return;
  if (!customElements.get(tagName)) customElements.define(tagName, UaiChatElement);
}

if (typeof customElements !== 'undefined' && typeof HTMLElement !== 'undefined') {
  defineUaiChat();
}
