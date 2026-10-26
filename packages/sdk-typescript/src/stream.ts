import {
  AbortError,
  AgentCancelledError,
  AgentFailedError,
  StreamIncompleteError,
  StreamProtocolError,
} from './errors.ts';
import { parseSSE } from './sse.ts';
import type { RuntimeEvent } from './types.ts';

const EVENT_TYPES = new Set<RuntimeEvent['event_type']>([
  'agent.started',
  'response.delta',
  'response.completed',
  'agent.failed',
  'agent.cancelled',
]);

interface MessageStreamOptions {
  body: ReadableStream<Uint8Array>;
  runId: string;
  assistantVersion?: number;
  signal?: AbortSignal;
  cancelOnAbort: boolean;
  cancel: () => Promise<unknown>;
}

export class MessageStream implements AsyncIterable<RuntimeEvent> {
  readonly runId: string;
  readonly assistantVersion?: number;

  readonly #body: ReadableStream<Uint8Array>;
  readonly #signal: AbortSignal | undefined;
  readonly #cancel: () => Promise<unknown>;
  readonly #cancelOnAbort: boolean;
  #cancelRequested = false;
  #abortListener: (() => void) | undefined;

  constructor(options: MessageStreamOptions) {
    this.runId = options.runId;
    this.assistantVersion = options.assistantVersion;
    this.#body = options.body;
    this.#signal = options.signal;
    this.#cancel = options.cancel;
    this.#cancelOnAbort = options.cancelOnAbort;

    if (this.#signal && this.#cancelOnAbort) {
      this.#abortListener = () => this.#requestCancel();
      if (this.#signal.aborted) {
        this.#requestCancel();
      } else {
        this.#signal.addEventListener('abort', this.#abortListener, {
          once: true,
        });
      }
    }
  }

  [Symbol.asyncIterator](): AsyncGenerator<RuntimeEvent> {
    return this.#iterate();
  }

  async *#iterate(): AsyncGenerator<RuntimeEvent> {
    try {
      for await (const message of parseSSE(this.#body, this.#signal)) {
        const event = parseRuntimeEvent(message.data, message.event);
        yield event;
        if (event.event_type === 'response.completed') return;
        if (event.event_type === 'agent.failed') {
          throw new AgentFailedError(event, event.payload.code);
        }
        if (event.event_type === 'agent.cancelled') {
          throw new AgentCancelledError(
            event,
            event.payload.code ?? 'cancelled',
          );
        }
      }
      throw new StreamIncompleteError(this.runId);
    } finally {
      if (this.#abortListener && this.#signal) {
        this.#signal.removeEventListener('abort', this.#abortListener);
      }
    }
  }

  #requestCancel(): void {
    if (this.#cancelRequested) return;
    this.#cancelRequested = true;
    void this.#cancel().catch(() => undefined);
  }
}

function parseRuntimeEvent(
  data: string,
  eventName?: string,
): RuntimeEvent {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch (error) {
    throw new StreamProtocolError('SSE data is not valid JSON.', {
      cause: error,
    });
  }
  if (!isRecord(value)) {
    throw new StreamProtocolError('SSE data must be a JSON object.');
  }
  const eventType = value.event_type;
  if (
    typeof eventType !== 'string' ||
    !EVENT_TYPES.has(eventType as RuntimeEvent['event_type'])
  ) {
    throw new StreamProtocolError('SSE event has an unknown event_type.');
  }
  if (eventName !== undefined && eventName !== eventType) {
    throw new StreamProtocolError(
      `SSE event name ${eventName} does not match ${eventType}.`,
    );
  }
  const payload = value.payload;
  if (!isRecord(payload)) {
    throw new StreamProtocolError('SSE event payload must be an object.');
  }
  switch (eventType) {
    case 'response.delta':
      if (typeof payload.text !== 'string') {
        throw new StreamProtocolError('response.delta payload.text is required.');
      }
      break;
    case 'response.completed':
      if (typeof payload.text !== 'string') {
        throw new StreamProtocolError(
          'response.completed payload.text is required.',
        );
      }
      break;
    case 'agent.failed':
      if (typeof payload.code !== 'string') {
        throw new StreamProtocolError('agent.failed payload.code is required.');
      }
      break;
    case 'agent.cancelled':
      if (payload.code !== undefined && typeof payload.code !== 'string') {
        throw new StreamProtocolError(
          'agent.cancelled payload.code must be a string.',
        );
      }
      break;
    case 'agent.started':
      break;
  }
  return value as RuntimeEvent;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
