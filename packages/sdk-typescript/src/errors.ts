import type { RuntimeEvent } from './types.ts';

export class UAIError extends Error {
  readonly code: string;

  constructor(message: string, code = 'uai_error', options?: ErrorOptions) {
    super(message, options);
    this.name = 'UAIError';
    this.code = code;
  }
}

export class ValidationError extends UAIError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, 'validation_error', options);
    this.name = 'ValidationError';
  }
}

export class AbortError extends UAIError {
  constructor(
    message = 'The operation was aborted.',
    options?: ErrorOptions,
  ) {
    super(message, 'aborted', options);
    this.name = 'AbortError';
  }
}

export class TimeoutError extends UAIError {
  constructor(message = 'The operation timed out.', options?: ErrorOptions) {
    super(message, 'timeout', options);
    this.name = 'TimeoutError';
  }
}

export class NetworkError extends UAIError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, 'network_error', options);
    this.name = 'NetworkError';
  }
}

export class APIError extends UAIError {
  readonly status: number;
  readonly body: unknown;
  readonly response: Response;

  constructor(
    status: number,
    code: string,
    body: unknown,
    response: Response,
    message = `Gateway request failed with status ${status} (${code}).`,
  ) {
    super(message, code);
    this.name = 'APIError';
    this.status = status;
    this.body = body;
    this.response = response;
  }
}

export class StreamIncompleteError extends UAIError {
  readonly runId?: string;

  constructor(runId?: string) {
    super(
      'The event stream ended without a terminal event.',
      'stream_incomplete',
    );
    this.name = 'StreamIncompleteError';
    this.runId = runId;
  }
}

export class StreamProtocolError extends UAIError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, 'stream_protocol_error', options);
    this.name = 'StreamProtocolError';
  }
}

export class AgentFailedError extends UAIError {
  readonly event: RuntimeEvent;

  constructor(event: RuntimeEvent, code: string) {
    super(`Agent run failed (${code}).`, code);
    this.name = 'AgentFailedError';
    this.event = event;
  }
}

export class AgentCancelledError extends UAIError {
  readonly event: RuntimeEvent;

  constructor(event: RuntimeEvent, code = 'cancelled') {
    super(`Agent run was cancelled (${code}).`, code);
    this.name = 'AgentCancelledError';
    this.event = event;
  }
}
