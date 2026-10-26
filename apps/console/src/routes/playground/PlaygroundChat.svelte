<script lang="ts">
  import { SSEDecoder } from '@universal-ai-kit/sdk';
  import type { Citation, RuntimeEvent } from '@universal-ai-kit/sdk';

  interface Props {
    conversationId: string;
    initialMessages?: Array<{ role: string; content: string }>;
  }

  interface UiMessage {
    role: 'user' | 'assistant';
    text: string;
    status?: 'streaming' | 'completed' | 'failed' | 'cancelled' | 'incomplete' | 'waiting';
    error?: string;
    citations?: Citation[];
  }

  let { conversationId, initialMessages = [] }: Props = $props();
  // svelte-ignore state_referenced_locally
  let messages = $state<UiMessage[]>(
    initialMessages.map((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      text: message.content,
    })),
  );
  let input = $state('');
  let sending = $state(false);
  let status = $state('');
  let runId = $state('');
  let waitingApproval = $state(false);
  let usage = $state<Record<string, number> | null>(null);
  let lastRequest = $state<{ content: string; key: string } | null>(null);
  let controller: AbortController | undefined;

  async function send(content = input, key = newKey(), appendUser = true): Promise<void> {
    const trimmed = content.trim();
    if (!trimmed || sending) return;
    if (appendUser) {
      messages = [...messages, { role: 'user', text: trimmed }];
      input = '';
    }
    lastRequest = { content: trimmed, key };
    const assistantIndex = messages.length;
    messages = [...messages, { role: 'assistant', text: '', status: 'streaming' }];
    const assistant = messages[assistantIndex]!;
    sending = true;
    waitingApproval = false;
    usage = null;
    status = 'Sto rispondendo…';
    controller = new AbortController();
    const signal = controller.signal;

    try {
      const response = await fetch('/api/playground/stream', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          content: trimmed,
          idempotency_key: key,
        }),
        signal,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      if (!response.body) throw new Error('Stream senza body');
      runId = response.headers.get('x-run-id') ?? '';
      const reader = response.body.getReader();
      const decoder = new SSEDecoder();
      const seen = new Set<string>();
      let terminal = false;

      const handle = (data: string): void => {
        let event: RuntimeEvent;
        try {
          event = JSON.parse(data) as RuntimeEvent;
        } catch {
          assistant.status = 'failed';
          assistant.error = 'Evento SSE non valido.';
          terminal = true;
          return;
        }
        if (seen.has(event.event_id)) return;
        seen.add(event.event_id);
        if (event.event_type === 'response.delta') {
          assistant.text += event.payload.text;
        } else if (event.event_type === 'response.completed') {
          assistant.text = event.payload.text || assistant.text;
          assistant.citations = event.payload.citations ?? [];
          usage = event.payload.usage ?? null;
          assistant.status = 'completed';
          terminal = true;
        } else if (event.event_type === 'agent.failed') {
          assistant.status = 'failed';
          assistant.error = `Errore del modello (${event.payload.code}).`;
          terminal = true;
        } else if (event.event_type === 'agent.cancelled') {
          assistant.status = 'cancelled';
          assistant.error = 'Risposta annullata.';
          terminal = true;
        }
      };

      while (!terminal) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const message of decoder.push(value)) handle(message.data);
      }
      if (!terminal) {
        for (const message of decoder.end()) handle(message.data);
      }
      if (!terminal) {
        assistant.status = 'incomplete';
        assistant.error = 'La risposta è incompleta: il collegamento è terminato senza evento finale.';
        status = assistant.error;
        await refreshRunStatus(assistant);
      } else if (assistant.status === 'completed') {
        status = 'Completato';
      } else if (assistant.status === 'failed' || assistant.status === 'cancelled') {
        status = assistant.error ?? 'Errore';
      }
      await reader.cancel().catch(() => undefined);
    } catch (cause) {
      if (signal.aborted) {
        assistant.status = 'cancelled';
        assistant.error = 'Risposta annullata.';
        status = assistant.error;
      } else {
        assistant.status = 'failed';
        assistant.error = cause instanceof Error ? cause.message : 'Errore di rete.';
        status = assistant.error;
      }
    } finally {
      sending = false;
      controller = undefined;
      messages = [...messages];
    }
  }

  async function refreshRunStatus(assistant: UiMessage): Promise<void> {
    if (!runId) return;
    try {
      const response = await fetch(`/api/playground/run?id=${encodeURIComponent(runId)}`);
      if (!response.ok) return;
      const run = (await response.json()) as { status?: string };
      if (run.status === 'waiting_approval') {
        waitingApproval = true;
        assistant.status = 'waiting';
        assistant.error = 'In attesa di approvazione umana.';
        status = assistant.error;
      }
    } catch {
      // Status refresh is best effort; the incomplete stream remains visible.
    }
  }

  function retry(): void {
    if (lastRequest) void send(lastRequest.content, lastRequest.key, false);
  }

  function cancel(): void {
    if (controller) {
      status = 'Annullamento…';
      controller.abort();
    }
  }

  function newKey(): string {
    const cryptoApi = globalThis.crypto;
    if (cryptoApi && typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID();
    return `playground-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void send();
    } else if (event.key === 'Escape') {
      cancel();
    }
  }
</script>

<div class="playground">
  <div class="messages playground-messages" role="log" aria-live="polite" aria-relevant="additions text">
    {#each messages as message, index (index)}
      <article class="message" data-role={message.role} data-status={message.status}>
        {#if message.role === 'user'}
          <div class="message-text">{message.text}</div>
        {:else}
          <div class="message-text">{message.text}</div>
          {#if message.citations && message.citations.length > 0}
            <ul class="citations" aria-label="Citazioni">
              {#each message.citations as citation (citation.citation_id)}
                <li>
                  <a
                    href={`/knowledge-bases/${citation.knowledge_base_id}/documents/${citation.document_id}?chunk=${citation.chunk_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Fonte {citation.document_id.slice(0, 8)}{citation.page ? `, p. ${citation.page}` : ''}
                  </a>
                </li>
              {/each}
            </ul>
          {/if}
          {#if message.error}
            <div class="error" role={message.status === 'failed' || message.status === 'incomplete' ? 'alert' : 'status'}>
              {message.error}
            </div>
          {/if}
          {#if message.status === 'waiting'}
            <a href="/approvals">Apri approvazioni</a>
          {/if}
        {/if}
      </article>
    {/each}
  </div>

  <div class="status" role="status" aria-live="polite">{status}</div>
  {#if usage}
    <div class="status" aria-label="Usage">
      Usage: input {usage.input_tokens ?? 0} / output {usage.output_tokens ?? 0}
    </div>
  {/if}

  <form
    class="playground-form"
    onsubmit={(event) => {
      event.preventDefault();
      void send();
    }}
  >
    <label class="visually-hidden" for="playground-input">Messaggio</label>
    <textarea
      id="playground-input"
      rows="2"
      bind:value={input}
      onkeydown={onKeydown}
      placeholder="Scrivi un messaggio…"
      disabled={sending}
    ></textarea>
    <button type="submit" disabled={sending}>Invia</button>
    {#if sending}
      <button class="danger" type="button" onclick={cancel}>Annulla</button>
    {/if}
  </form>
  {#if lastRequest && (status.includes('incompleta') || status.startsWith('HTTP') || status.includes('Errore'))}
    <button class="secondary" type="button" onclick={retry} disabled={sending}>
      Riprova con la stessa richiesta
    </button>
  {/if}
  {#if waitingApproval}
    <p class="notice">Il run è in attesa di approvazione. Apri la pagina Approvazioni per decidere.</p>
  {/if}
</div>
