import { AbortError } from './errors.ts';

export interface SSEMessage {
  id?: string;
  event?: string;
  data: string;
}

/**
 * Incremental Server-Sent Events decoder. It accepts arbitrary byte chunks,
 * including chunks that split a UTF-8 code point or an SSE frame.
 */
export class SSEDecoder {
  #text = '';
  #decoder = new TextDecoder();
  #started = false;
  #data: string[] = [];
  #event: string | undefined;
  #id: string | undefined;
  #lastEventId: string | undefined;

  push(chunk: Uint8Array): SSEMessage[] {
    this.#text += this.#decoder.decode(chunk, { stream: true });
    if (!this.#started) {
      this.#started = true;
      if (this.#text.startsWith('\uFEFF')) this.#text = this.#text.slice(1);
    }
    return this.#drain(false);
  }

  end(): SSEMessage[] {
    this.#text += this.#decoder.decode();
    const messages = this.#drain(true);
    // An incomplete frame at EOF is not dispatched by the SSE specification.
    this.#data = [];
    this.#event = undefined;
    this.#id = undefined;
    return messages;
  }

  #drain(atEnd: boolean): SSEMessage[] {
    const messages: SSEMessage[] = [];
    while (true) {
      let index = -1;
      for (let i = 0; i < this.#text.length; i += 1) {
        const character = this.#text[i];
        if (character === '\n' || character === '\r') {
          index = i;
          break;
        }
      }
      if (index === -1) break;

      const character = this.#text[index];
      if (
        character === '\r' &&
        index === this.#text.length - 1 &&
        !atEnd
      ) {
        // A trailing CR may be the first half of a CRLF pair.
        break;
      }

      let next = index + 1;
      if (character === '\r' && this.#text[next] === '\n') next += 1;
      const line = this.#text.slice(0, index);
      this.#text = this.#text.slice(next);
      this.#consumeLine(line, messages);
    }

    if (atEnd && this.#text.length > 0) {
      const line = this.#text;
      this.#text = '';
      this.#consumeLine(line, messages);
    }
    return messages;
  }

  #consumeLine(line: string, messages: SSEMessage[]): void {
    if (line === '') {
      const data = this.#data.join('\n');
      const event = this.#event;
      const id = this.#id ?? this.#lastEventId;
      this.#data = [];
      this.#event = undefined;
      this.#id = undefined;
      if (data === '') return;
      messages.push({
        ...(id === undefined ? {} : { id }),
        ...(event === undefined ? {} : { event }),
        data,
      });
      return;
    }

    if (line.startsWith(':')) return;

    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? '' : line.slice(separator + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    switch (field) {
      case 'data':
        this.#data.push(value);
        break;
      case 'event':
        this.#event = value;
        break;
      case 'id':
        if (!value.includes('\0')) {
          this.#id = value;
          this.#lastEventId = value;
        }
        break;
      case 'retry':
        break;
      default:
        break;
    }
  }
}

export async function* parseSSE(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SSEMessage> {
  const reader = stream.getReader();
  const decoder = new SSEDecoder();
  const onAbort = (): void => {
    void reader.cancel().catch(() => undefined);
  };

  if (signal?.aborted) {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
    throw new AbortError();
  }
  signal?.addEventListener('abort', onAbort, { once: true });

  try {
    while (true) {
      if (signal?.aborted) throw new AbortError();
      const { done, value } = await reader.read();
      if (signal?.aborted) throw new AbortError();
      if (done) break;
      for (const message of decoder.push(value)) yield message;
    }
    for (const message of decoder.end()) yield message;
  } catch (error) {
    if (signal?.aborted && !(error instanceof AbortError)) {
      throw new AbortError(undefined, { cause: error });
    }
    throw error;
  } finally {
    signal?.removeEventListener('abort', onAbort);
    reader.releaseLock();
  }
}
