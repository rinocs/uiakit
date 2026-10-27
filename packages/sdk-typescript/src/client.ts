import {
  APIError,
  AbortError,
  NetworkError,
  TimeoutError,
  UAIError,
  ValidationError,
} from './errors.ts';
import { operations, type Operation } from './operations.ts';
import { MessageStream } from './stream.ts';
import type {
  AgentRun,
  Assistant,
  AssistantInput,
  AssistantPatch,
  AuditEvent,
  Approval,
  Conversation,
  ConversationInput,
  Credential,
  CredentialInput,
  CredentialRotation,
  CredentialSecret,
  Document,
  DocumentJob,
  DocumentUpload,
  Health,
  KnowledgeBase,
  KnowledgeBaseExport,
  KnowledgeBaseInput,
  KnowledgeBasePatch,
  KnowledgeBaseVersion,
  KnowledgeBaseVersionInput,
  Message,
  MessageInput,
  ModelDefinition,
  PrincipalInfo,
  ProviderConfiguration,
  ProviderDiscovery,
  ProviderModelList,
  ProviderUpdate,
  PluginCatalog,
  PluginHealth,
  PluginSetting,
  PluginUpdate,
  ToolDefinition,
  WidgetToken,
  WidgetTokenInput,
} from './types.ts';

export interface ClientOptions {
  baseUrl: string;
  apiKey: string;
  fetch?: typeof globalThis.fetch;
  headers?: HeadersInit;
  timeoutMs?: number;
}

export interface RequestOptions {
  pathParams?: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  form?: FormData;
  headers?: HeadersInit;
  signal?: AbortSignal;
  timeoutMs?: number;
  idempotencyKey?: string;
  ifMatch?: string;
}

export interface MutationOptions {
  ifMatch: string;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface SendMessageOptions {
  idempotencyKey: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  cancelOnAbort?: boolean;
}

export type DocumentUploadInput = Omit<DocumentUpload, 'file'> & {
  file: Blob;
  filename?: string;
};

interface FetchResult {
  response: Response;
  signal?: AbortSignal;
}

export class UniversalAIKit {
  readonly baseUrl: string;
  readonly assistants: AssistantsResource;
  readonly conversations: ConversationsResource;
  readonly credentials: CredentialsResource;
  readonly models: ModelsResource;
  readonly tools: ToolsResource;
  readonly plugins: PluginsResource;
  readonly knowledgeBases: KnowledgeBasesResource;
  readonly documents: DocumentsResource;
  readonly agentRuns: AgentRunsResource;
  readonly approvals: ApprovalsResource;
  readonly auditEvents: AuditEventsResource;
  readonly provider: ProviderResource;
  readonly widgetTokens: WidgetTokensResource;

  readonly #apiKey: string;
  readonly #fetch: typeof globalThis.fetch;
  readonly #headers: Headers;
  readonly #timeoutMs: number | undefined;

  constructor(options: ClientOptions) {
    if (!options.baseUrl) throw new ValidationError('baseUrl is required.');
    if (!options.apiKey) throw new ValidationError('apiKey is required.');
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.#apiKey = options.apiKey;
    this.#fetch = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.#headers = new Headers(options.headers);
    this.#timeoutMs = options.timeoutMs;

    this.assistants = new AssistantsResource(this);
    this.conversations = new ConversationsResource(this);
    this.credentials = new CredentialsResource(this);
    this.models = new ModelsResource(this);
    this.tools = new ToolsResource(this);
    this.plugins = new PluginsResource(this);
    this.knowledgeBases = new KnowledgeBasesResource(this);
    this.documents = new DocumentsResource(this);
    this.agentRuns = new AgentRunsResource(this);
    this.approvals = new ApprovalsResource(this);
    this.auditEvents = new AuditEventsResource(this);
    this.provider = new ProviderResource(this);
    this.widgetTokens = new WidgetTokensResource(this);
  }

  health(options: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<Health> {
    return this.request(operations.health, options);
  }

  me(options: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<PrincipalInfo> {
    return this.request(operations.me, options);
  }

  /** @internal */
  async request<T>(
    operation: Operation,
    options: RequestOptions = {},
  ): Promise<T> {
    const { response } = await this.fetchResponse(operation, options);
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (text.trim() === '') return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch (error) {
      throw new UAIError(
        'Gateway returned an invalid JSON response.',
        'invalid_response',
        { cause: error },
      );
    }
  }

  /** @internal */
  async sendMessage(
    conversationId: string,
    input: MessageInput,
    options: SendMessageOptions,
  ): Promise<MessageStream> {
    const { response, signal } = await this.fetchResponse(
      operations.sendMessage,
      {
        pathParams: { id: conversationId },
        body: input,
        idempotencyKey: options.idempotencyKey,
        signal: options.signal,
        timeoutMs: options.timeoutMs,
        headers: { Accept: 'text/event-stream' },
      },
    );
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.toLowerCase().startsWith('text/event-stream')) {
      throw new APIError(
        response.status,
        'invalid_content_type',
        undefined,
        response,
        'Gateway did not return an SSE stream.',
      );
    }
    if (!response.body) {
      throw new APIError(
        response.status,
        'missing_stream',
        undefined,
        response,
        'Gateway returned an empty SSE response.',
      );
    }
    const runId = response.headers.get('x-run-id');
    if (!runId) {
      throw new APIError(
        response.status,
        'missing_run_id',
        undefined,
        response,
        'Gateway did not return X-Run-ID.',
      );
    }
    const assistantVersion = parseAssistantVersion(
      response.headers.get('x-assistant-version'),
    );

    return new MessageStream({
      body: response.body,
      runId,
      assistantVersion,
      signal,
      cancelOnAbort: options.cancelOnAbort !== false,
      cancel: () => this.agentRuns.cancel(runId),
    });
  }

  /** @internal */
  async fetchResponse(
    operation: Operation,
    options: RequestOptions,
  ): Promise<FetchResult> {
    if (operation.requiresIdempotencyKey && !options.idempotencyKey) {
      throw new ValidationError(
        `Idempotency-Key is required for ${operation.method} ${operation.path}.`,
      );
    }
    if (operation.requiresIfMatch && !options.ifMatch) {
      throw new ValidationError(
        `If-Match is required for ${operation.method} ${operation.path}.`,
      );
    }

    const url = new URL(this.baseUrl + this.#fillPath(operation, options));
    for (const [name, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined) url.searchParams.set(name, String(value));
    }

    const headers = new Headers(this.#headers);
    headers.set('Authorization', `Bearer ${this.#apiKey}`);
    headers.set('Accept', headers.get('Accept') ?? 'application/json');
    if (options.idempotencyKey) {
      headers.set('Idempotency-Key', options.idempotencyKey);
    }
    if (options.ifMatch) headers.set('If-Match', options.ifMatch);
    if (options.headers) {
      for (const [name, value] of new Headers(options.headers)) {
        headers.set(name, value);
      }
    }

    let body: BodyInit | undefined;
    if (options.form) {
      body = options.form;
    } else if (options.body !== undefined) {
      body = JSON.stringify(options.body);
      if (!headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }
    }

    const prepared = this.#prepareSignal(options.signal, options.timeoutMs);
    let response: Response;
    try {
      response = await this.#fetch(url.toString(), {
        method: operation.method,
        headers,
        body,
        signal: prepared.signal,
      });
    } catch (error) {
      if (prepared.timedOut()) {
        throw new TimeoutError(undefined, { cause: error });
      }
      if (prepared.signal?.aborted || isAbortError(error)) {
        throw new AbortError(undefined, { cause: error });
      }
      throw new NetworkError('Gateway request failed.', { cause: error });
    }

    if (!response.ok) {
      const errorBody = await readErrorBody(response);
      const code = errorCode(errorBody, response.status);
      throw new APIError(response.status, code, errorBody, response);
    }

    return { response, signal: prepared.signal };
  }

  #fillPath(operation: Operation, options: RequestOptions): string {
    let path = operation.path;
    for (const [name, value] of Object.entries(options.pathParams ?? {})) {
      path = path.replace(`{${name}}`, encodeURIComponent(value));
    }
    if (path.includes('{')) {
      throw new ValidationError(
        `Missing path parameter for ${operation.path}.`,
      );
    }
    return path;
  }

  #prepareSignal(
    signal: AbortSignal | undefined,
    timeoutMs: number | undefined,
  ): { signal?: AbortSignal; timedOut: () => boolean } {
    const timeout = timeoutMs ?? this.#timeoutMs;
    if (!timeout || timeout <= 0) {
      return { signal, timedOut: () => false };
    }
    const timeoutSignal = AbortSignal.timeout(timeout);
    return {
      signal: signal
        ? AbortSignal.any([signal, timeoutSignal])
        : timeoutSignal,
      timedOut: () => timeoutSignal.aborted,
    };
  }
}

class AssistantsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<Assistant[]> {
    return this.#client.request(operations.listAssistants, options);
  }

  create(
    input: AssistantInput,
    options: { signal?: AbortSignal } = {},
  ): Promise<Assistant> {
    return this.#client.request(operations.createAssistant, {
      ...options,
      body: input,
    });
  }

  get(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Assistant> {
    return this.#client.request(operations.getAssistant, {
      ...options,
      pathParams: { id },
    });
  }

  update(
    id: string,
    patch: AssistantPatch,
    options: MutationOptions,
  ): Promise<Assistant> {
    return this.#client.request(operations.updateAssistant, {
      pathParams: { id },
      body: patch,
      ifMatch: options.ifMatch,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  }

  versions(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Assistant[]> {
    return this.#client.request(operations.listAssistantVersions, {
      ...options,
      pathParams: { id },
    });
  }
}

class ConversationsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  create(
    input: ConversationInput,
    options: { signal?: AbortSignal } = {},
  ): Promise<Conversation> {
    return this.#client.request(operations.createConversation, {
      ...options,
      body: input,
    });
  }

  delete(id: string, options: { signal?: AbortSignal } = {}): Promise<void> {
    return this.#client.request(operations.deleteConversation, {
      ...options,
      pathParams: { id },
    });
  }

  messages(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Message[]> {
    return this.#client.request(operations.getMessages, {
      ...options,
      pathParams: { id },
    });
  }

  sendMessage(
    id: string,
    input: MessageInput,
    options: SendMessageOptions,
  ): Promise<MessageStream> {
    return this.#client.sendMessage(id, input, options);
  }
}

class CredentialsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<Credential[]> {
    return this.#client.request(operations.listCredentials, options);
  }

  create(
    input: CredentialInput,
    options: { signal?: AbortSignal } = {},
  ): Promise<CredentialSecret> {
    return this.#client.request(operations.createCredential, {
      ...options,
      body: input,
    });
  }

  rotate(
    id: string,
    input: CredentialRotation,
    options: { signal?: AbortSignal } = {},
  ): Promise<CredentialSecret> {
    return this.#client.request(operations.rotateCredential, {
      ...options,
      pathParams: { id },
      body: input,
    });
  }

  revoke(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<{ status: string }> {
    return this.#client.request(operations.revokeCredential, {
      ...options,
      pathParams: { id },
    });
  }
}

class ModelsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<ModelDefinition[]> {
    return this.#client.request(operations.listModels, options);
  }
}

class ToolsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<ToolDefinition[]> {
    return this.#client.request(operations.listTools, options);
  }
}

class PluginsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<PluginCatalog> {
    return this.#client.request(operations.listPlugins, options);
  }

  configure(
    id: string,
    setting: PluginSetting,
    options: MutationOptions,
  ): Promise<PluginUpdate> {
    return this.#client.request(operations.configurePlugin, {
      pathParams: { id },
      body: setting,
      ifMatch: options.ifMatch,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  }

  remove(id: string, options: MutationOptions): Promise<PluginUpdate> {
    return this.#client.request(operations.removePluginConfiguration, {
      pathParams: { id },
      ifMatch: options.ifMatch,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  }

  health(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<PluginHealth> {
    return this.#client.request(operations.pluginHealth, {
      ...options,
      pathParams: { id },
    });
  }
}

class KnowledgeBasesResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<KnowledgeBase[]> {
    return this.#client.request(operations.listKnowledgeBases, options);
  }

  create(
    input: KnowledgeBaseInput,
    options: { signal?: AbortSignal } = {},
  ): Promise<KnowledgeBase> {
    return this.#client.request(operations.createKnowledgeBase, {
      ...options,
      body: input,
    });
  }

  get(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<KnowledgeBase> {
    return this.#client.request(operations.getKnowledgeBase, {
      ...options,
      pathParams: { id },
    });
  }

  update(
    id: string,
    patch: KnowledgeBasePatch,
    options: MutationOptions,
  ): Promise<KnowledgeBase> {
    return this.#client.request(operations.updateKnowledgeBase, {
      pathParams: { id },
      body: patch,
      ifMatch: options.ifMatch,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  }

  delete(id: string, options: MutationOptions): Promise<void> {
    return this.#client.request(operations.deleteKnowledgeBase, {
      pathParams: { id },
      ifMatch: options.ifMatch,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  }

  versions(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<KnowledgeBaseVersion[]> {
    return this.#client.request(operations.listKnowledgeBaseVersions, {
      ...options,
      pathParams: { id },
    });
  }

  createVersion(
    id: string,
    input: KnowledgeBaseVersionInput,
    options: MutationOptions,
  ): Promise<KnowledgeBaseVersion> {
    return this.#client.request(operations.createKnowledgeBaseVersion, {
      pathParams: { id },
      body: input,
      ifMatch: options.ifMatch,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  }

  export(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<KnowledgeBaseExport> {
    return this.#client.request(operations.exportKnowledgeBase, {
      ...options,
      pathParams: { id },
    });
  }
}

class DocumentsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(
    knowledgeBaseId?: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Document[]> {
    return this.#client.request(operations.listDocuments, {
      ...options,
      query: { knowledge_base_id: knowledgeBaseId },
    });
  }

  upload(
    input: DocumentUploadInput,
    options: { signal?: AbortSignal } = {},
  ): Promise<Document> {
    const form = new FormData();
    form.set('knowledge_base_id', input.knowledge_base_id);
    form.set(
      'file',
      input.file,
      input.filename ??
        (typeof File !== 'undefined' && input.file instanceof File
          ? input.file.name
          : 'document'),
    );
    if (input.title !== undefined) form.set('title', input.title);
    return this.#client.request(operations.uploadDocument, {
      ...options,
      form,
    });
  }

  get(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Document> {
    return this.#client.request(operations.getDocument, {
      ...options,
      pathParams: { id },
    });
  }

  delete(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<void> {
    return this.#client.request(operations.deleteDocument, {
      ...options,
      pathParams: { id },
    });
  }

  job(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<DocumentJob> {
    return this.#client.request(operations.getDocumentJob, {
      ...options,
      pathParams: { id },
    });
  }

  cancelJob(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<DocumentJob> {
    return this.#client.request(operations.cancelDocumentJob, {
      ...options,
      pathParams: { id },
    });
  }
}

class AgentRunsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<AgentRun[]> {
    return this.#client.request(operations.listAgentRuns, options);
  }

  get(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<AgentRun> {
    return this.#client.request(operations.getAgentRun, {
      ...options,
      pathParams: { id },
    });
  }

  cancel(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<AgentRun> {
    return this.#client.request(operations.cancelAgentRun, {
      ...options,
      pathParams: { id },
    });
  }
}

class ApprovalsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(options: { signal?: AbortSignal } = {}): Promise<Approval[]> {
    return this.#client.request(operations.listApprovals, options);
  }

  get(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Approval> {
    return this.#client.request(operations.getApproval, {
      ...options,
      pathParams: { id },
    });
  }

  approve(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Approval> {
    return this.#client.request(operations.approveApproval, {
      ...options,
      pathParams: { id },
    });
  }

  reject(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<Approval> {
    return this.#client.request(operations.rejectApproval, {
      ...options,
      pathParams: { id },
    });
  }
}

class ProviderResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  get(options: { signal?: AbortSignal } = {}): Promise<ProviderConfiguration> {
    return this.#client.request(operations.getProvider, options);
  }

  update(
    update: ProviderUpdate,
    options: MutationOptions,
  ): Promise<ProviderConfiguration> {
    return this.#client.request(operations.updateProvider, {
      body: update,
      ifMatch: options.ifMatch,
      signal: options.signal,
      timeoutMs: options.timeoutMs,
    });
  }

  discoverModels(
    discovery: ProviderDiscovery,
    options: { signal?: AbortSignal } = {},
  ): Promise<ProviderModelList> {
    return this.#client.request(operations.discoverProviderModels, {
      ...options,
      body: discovery,
    });
  }
}

class WidgetTokensResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  create(
    input: WidgetTokenInput,
    options: { signal?: AbortSignal } = {},
  ): Promise<WidgetToken> {
    return this.#client.request(operations.createWidgetToken, {
      ...options,
      body: input,
    });
  }

  revoke(
    id: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<{ status: string }> {
    return this.#client.request(operations.revokeWidgetToken, {
      ...options,
      pathParams: { id },
    });
  }
}

class AuditEventsResource {
  readonly #client: UniversalAIKit;

  constructor(client: UniversalAIKit) {
    this.#client = client;
  }

  list(
    options: {
      runId?: string;
      action?: string;
      targetId?: string;
      limit?: number;
      signal?: AbortSignal;
    } = {},
  ): Promise<AuditEvent[]> {
    return this.#client.request(operations.listAuditEvents, {
      query: {
        run_id: options.runId,
        action: options.action,
        target_id: options.targetId,
        limit: options.limit,
      },
      signal: options.signal,
    });
  }
}

async function readErrorBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.trim() === '') return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorCode(body: unknown, status: number): string {
  if (
    typeof body === 'object' &&
    body !== null &&
    'error' in body &&
    typeof body.error === 'string'
  ) {
    return body.error;
  }
  return `http_${status}`;
}

function parseAssistantVersion(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    error.name === 'AbortError'
  );
}
