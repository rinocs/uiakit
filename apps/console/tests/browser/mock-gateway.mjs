import { createServer } from 'node:http';

const port = Number(process.env.MOCK_PORT || 3101);
const model = {
  id: 'test-model',
  provider: 'openai-compatible',
  capabilities: ['chat', 'streaming'],
  max_output_tokens: 1024,
  context_window: 8192,
};
let assistant = {
  id: '00000000-0000-4000-8000-0000000000a1',
  version: 1,
  name: 'Supporto',
  description: '',
  model: 'test-model',
  system_prompt: 'Rispondi in modo chiaro.',
  directives: [],
  tools: [],
  skills: [],
  knowledge_base_ids: [],
};
const assistantVersions = [structuredClone(assistant)];

const publicKB = {
  id: '00000000-0000-4000-8000-0000000000b1',
  name: 'Supporto clienti',
  description: 'Documenti pubblici di supporto.',
  revision: 1,
  active_version: 1,
  created_at: '2026-10-22T00:00:00Z',
  updated_at: '2026-10-22T00:00:00Z',
};
const privateKB = {
  id: '00000000-0000-4000-8000-0000000000b2',
  name: 'Riservato',
  description: 'Solo admin.',
  revision: 1,
  active_version: 1,
  created_at: '2026-10-22T00:00:00Z',
  updated_at: '2026-10-22T00:00:00Z',
};
const knowledgeBases = [publicKB, privateKB];
const versions = new Map([
  [publicKB.id, [{
    version: 1,
    state: 'active',
    config: { chunk_size: 1000, chunk_overlap: 200 },
    created_at: '2026-10-22T00:00:00Z',
    chunk_count: 0,
    attempts: 0,
  }]],
  [privateKB.id, [{
    version: 1,
    state: 'active',
    config: { chunk_size: 1000, chunk_overlap: 200 },
    created_at: '2026-10-22T00:00:00Z',
    chunk_count: 0,
    attempts: 0,
  }]],
]);
const documents = [];
const jobs = new Map();
const chunks = [];
const tools = [
  {
    id: 'example.lookup',
    name: 'Lookup',
    description: 'Legge un record dal connector example.',
    version: '1.0.0',
    input_schema: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'] },
    output_schema: { type: 'object' },
    permissions: ['tools:execute', 'connector:example'],
    risk_level: 'read_only',
    executor: 'http',
  },
  {
    id: 'example.write',
    name: 'Write',
    description: 'Effetto controllato con approvazione.',
    version: '1.0.0',
    input_schema: { type: 'object' },
    output_schema: { type: 'object' },
    permissions: ['tools:execute', 'connector:example'],
    risk_level: 'mutating',
    executor: 'http',
  },
];
const pluginManifest = {
  id: 'org.uai.hello',
  name: 'Hello plugin',
  version: '1.0.0',
  compatibility: { core: '>=0.1.0' },
  permissions: { core: ['events:observe'] },
  config: {},
  config_schema: { type: 'object' },
};
let pluginCatalog = {
  revision: 1,
  applied: true,
  plugins: [{ manifest: structuredClone(pluginManifest), state: 'inactive' }],
  desired: {},
};
const future = new Date(Date.now() + 3_600_000).toISOString();
const past = new Date(Date.now() - 3_600_000).toISOString();
const approvals = [
  {
    id: '00000000-0000-4000-8000-0000000000e1',
    run_id: '00000000-0000-4000-8000-000000000102',
    tool_id: 'example.write',
    tool_version: '1.0.0',
    arguments_digest: 'c'.repeat(64),
    policy_digest: 'd'.repeat(64),
    policy_snapshot: {
      assistant: { id: assistant.id, version: assistant.version, tools: ['example.write'], require_tool_approval: true },
      principal: { id: actorFor('admin'), scopes: ['approvals:read', 'approvals:write'], allowed_tool_ids: ['example.write'] },
      tool: { id: 'example.write', version: '1.0.0', permissions: ['tools:execute', 'connector:example'], risk_level: 'mutating', executor: 'http' },
      connector_allowlist: ['example'],
    },
    requested_by: 'user-1',
    status: 'pending',
    created_at: '2026-10-22T00:00:00Z',
    expires_at: future,
  },
  {
    id: '00000000-0000-4000-8000-0000000000e2',
    run_id: '00000000-0000-4000-8000-000000000103',
    tool_id: 'example.write',
    tool_version: '1.0.0',
    arguments_digest: 'e'.repeat(64),
    policy_digest: 'f'.repeat(64),
    policy_snapshot: {
      tool: { id: 'example.write', version: '1.0.0', permissions: ['connector:example'], risk_level: 'mutating', executor: 'http' },
    },
    requested_by: 'user-1',
    status: 'pending',
    created_at: '2026-10-22T00:00:00Z',
    expires_at: past,
  },
];

const liveMessages = new Map([
  ['00000000-0000-4000-8000-0000000000c1', [
    { role: 'user', content: 'Ciao' },
    { role: 'assistant', content: 'Ciao dal mock' },
  ]],
  ['00000000-0000-4000-8000-0000000000c2', [
    { role: 'user', content: 'Scrivi un effetto' },
  ]],
  ['00000000-0000-4000-8000-0000000000c3', [
    { role: 'user', content: 'Errore' },
  ]],
  ['00000000-0000-4000-8000-0000000000c4', [
    { role: 'user', content: 'Cancella' },
  ]],
]);
const runs = [
  {
    id: '00000000-0000-4000-8000-000000000101',
    conversation_id: '00000000-0000-4000-8000-0000000000c1',
    status: 'completed',
    assistant_id: assistant.id,
    assistant_version: assistant.version,
    model: 'test-model',
    created_at: '2026-10-22T00:00:00Z',
    updated_at: '2026-10-22T00:00:01Z',
    finished_at: '2026-10-22T00:00:01Z',
  },
  {
    id: '00000000-0000-4000-8000-000000000102',
    conversation_id: '00000000-0000-4000-8000-0000000000c2',
    status: 'waiting_approval',
    assistant_id: assistant.id,
    assistant_version: assistant.version,
    model: 'test-model',
    created_at: '2026-10-22T00:00:00Z',
    updated_at: '2026-10-22T00:00:01Z',
  },
  {
    id: '00000000-0000-4000-8000-000000000103',
    conversation_id: '00000000-0000-4000-8000-0000000000c3',
    status: 'failed',
    assistant_id: assistant.id,
    assistant_version: assistant.version,
    model: 'test-model',
    created_at: '2026-10-22T00:00:00Z',
    updated_at: '2026-10-22T00:00:01Z',
  },
  {
    id: '00000000-0000-4000-8000-000000000104',
    conversation_id: '00000000-0000-4000-8000-0000000000c4',
    status: 'cancelled',
    assistant_id: assistant.id,
    assistant_version: assistant.version,
    model: 'test-model',
    created_at: '2026-10-22T00:00:00Z',
    updated_at: '2026-10-22T00:00:01Z',
  },
];
const auditEvents = [
  {
    id: '00000000-0000-4000-8000-000000000201',
    actor_principal_id: 'admin-1',
    action: 'tool.approved',
    target_id: '00000000-0000-4000-8000-0000000000e1',
    target_type: 'approval',
    run_id: '00000000-0000-4000-8000-000000000102',
    outcome: 'success',
    created_at: '2026-10-22T00:00:01Z',
    details: { tool_id: 'example.write', decision: 'approved', authorization: '[redacted]', api_key: '[redacted]' },
  },
  {
    id: '00000000-0000-4000-8000-000000000202',
    actor_principal_id: 'admin-1',
    action: 'credential.created',
    target_id: '00000000-0000-4000-8000-0000000000c1',
    target_type: 'credential',
    outcome: 'success',
    created_at: '2026-10-22T00:00:02Z',
    details: { role: 'reader', scopes: ['assistants:read', 'models:read'], api_key: '[redacted]' },
  },
];
const credentials = [
  {
    id: '00000000-0000-4000-8000-0000000000c1',
    principal_id: 'ci-runner',
    role: 'reader',
    scopes: ['assistants:read', 'models:read'],
    expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
    revoked_at: null,
    created_at: '2026-10-01T00:00:00Z',
  },
];
let providerConfig = {
  revision: 1,
  provider: 'openai-compatible',
  base_url: 'http://provider.local/v1',
  api_key_ref: 'MODEL_API_KEY',
  max_output_tokens: 1024,
  models: [{ id: 'test-model', capabilities: [], context_window: 8192 }],
};

function providerDefinitions() {
  return providerConfig.models.map((model) => ({
    id: model.id,
    provider: providerConfig.provider,
    capabilities: ['chat', 'streaming', ...model.capabilities].sort(),
    max_output_tokens: providerConfig.max_output_tokens,
    context_window: model.context_window,
  }));
}

function providerView() {
  return {
    revision: providerConfig.revision,
    managed: true,
    applied: true,
    provider: providerConfig.provider,
    base_url: providerConfig.base_url,
    api_key_ref: providerConfig.api_key_ref,
    api_key_configured: true,
    max_output_tokens: providerConfig.max_output_tokens,
    models: providerDefinitions(),
  };
}
const replayCounts = new Map();

function actorFor() {
  return 'admin-1';
}

function writeSSE(response, id, type, payload) {
  const event = {
    event_id: id,
    event_type: type,
    event_version: 1,
    timestamp: '2026-10-22T00:00:00Z',
    run_id: '00000000-0000-4000-8000-000000000199',
    correlation_id: '00000000-0000-4000-8000-000000000198',
    payload,
  };
  response.write(`id: ${id}\nevent: ${type}\ndata: ${JSON.stringify(event)}\n\n`);
}

function sseHeaders(response, runId) {
  response.writeHead(200, {
    'content-type': 'text/event-stream',
    'cache-control': 'no-store',
    'x-run-id': runId,
  });
  response.flushHeaders();
}

function principal(key) {
  if (key === 'admin-key') {
    return {
      principal_id: 'admin-1',
      role: 'admin',
      scopes: [
        'assistants:read', 'assistants:write', 'models:read',
        'knowledge-bases:read', 'knowledge-bases:write',
        'documents:read', 'documents:write',
        'tools:read', 'plugins:read', 'plugins:write',
        'approvals:read', 'approvals:write',
        'audit:read', 'credentials:read', 'credentials:write',
        'providers:read', 'providers:write',
      ],
    };
  }
  if (key === 'reader-key') {
    return {
      principal_id: 'reader-1',
      role: 'reader',
      scopes: ['assistants:read', 'models:read', 'knowledge-bases:read', 'documents:read'],
    };
  }
  if (key === 'widget-key') {
    return { principal_id: 'widget:1', role: 'widget', scopes: ['messages:read', 'messages:write'] };
  }
  return null;
}

function send(response, status, body, headers = {}) {
  response.writeHead(status, { 'content-type': 'application/json', ...headers });
  response.end(JSON.stringify(body));
}

async function body(request) {
  const chunksRead = [];
  for await (const chunk of request) chunksRead.push(chunk);
  return chunksRead.length ? JSON.parse(Buffer.concat(chunksRead).toString('utf8')) : {};
}

async function rawBody(request) {
  const chunksRead = [];
  for await (const chunk of request) chunksRead.push(chunk);
  return Buffer.concat(chunksRead);
}

function multipart(buffer, contentType) {
  const match = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType || '');
  if (!match) return { fields: {} };
  const boundary = `--${match[1] || match[2]}`;
  const fields = {};
  const text = buffer.toString('utf8');
  for (const part of text.split(boundary)) {
    const split = part.indexOf('\r\n\r\n');
    if (split === -1) continue;
    const headers = part.slice(0, split);
    let value = part.slice(split + 4).replace(/\r\n$/, '');
    const name = /name="([^"]+)"/.exec(headers)?.[1];
    const filename = /filename="([^"]*)"/.exec(headers)?.[1];
    if (!name) continue;
    fields[name] = filename ? { filename, value } : value;
  }
  return { fields };
}

function visibleKB(actor, id) {
  const kb = knowledgeBases.find((item) => item.id === id);
  if (!kb) return null;
  if (actor.role !== 'admin' && kb.id === privateKB.id) return null;
  return kb;
}

function exportFor(kb) {
  return {
    knowledge_base: kb,
    versions: versions.get(kb.id) ?? [],
    documents: documents.filter((document) => document.knowledge_base_id === kb.id),
    chunks: chunks.filter((chunk) => chunk.knowledge_base_id === kb.id),
    exported_at: '2026-10-22T00:00:00Z',
  };
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || '/', 'http://127.0.0.1');
  const key = (request.headers.authorization || '').replace(/^Bearer\s+/, '');
  if (url.pathname === '/v1/health') return send(response, 200, { status: 'ok', version: 'test' });
  const actor = principal(key);
  if (!actor) return send(response, 401, { error: 'unauthorized' });

  if (request.method === 'GET' && url.pathname === '/v1/me') return send(response, 200, actor);
  if (request.method === 'GET' && url.pathname === '/v1/models') return send(response, 200, providerDefinitions());
  if (request.method === 'GET' && url.pathname === '/v1/provider') {
    if (!actor.scopes.includes('providers:read')) return send(response, 403, { code: 'forbidden' });
    return send(response, 200, providerView());
  }
  if (request.method === 'PUT' && url.pathname === '/v1/provider') {
    if (!actor.scopes.includes('providers:write')) return send(response, 403, { code: 'forbidden' });
    if (request.headers['if-match'] !== `"${providerConfig.revision}"`) {
      return send(response, 412, { code: 'version_conflict' });
    }
    const input = await body(request);
    providerConfig = {
      revision: providerConfig.revision + 1,
      provider: input.provider,
      base_url: input.base_url,
      api_key_ref: input.api_key_ref ?? '',
      max_output_tokens: input.max_output_tokens,
      models: input.models ?? [],
    };
    return send(response, 200, providerView());
  }
  if (request.method === 'POST' && url.pathname === '/v1/provider/models') {
    if (!actor.scopes.includes('providers:write')) return send(response, 403, { code: 'forbidden' });
    return send(response, 200, { models: ['test-model', 'extra-model'] });
  }
  if (request.method === 'GET' && url.pathname === '/v1/assistants') return send(response, 200, [assistant]);

  if (request.method === 'POST' && url.pathname === '/v1/assistants') {
    if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
    const input = await body(request);
    assistant = {
      ...assistant,
      ...input,
      version: 1,
      id: `00000000-0000-4000-8000-0000000000${String(assistant.version + 1).padStart(2, '0')}`,
    };
    assistantVersions.length = 0;
    assistantVersions.push(structuredClone(assistant));
    return send(response, 201, assistant);
  }

  const assistantMatch = url.pathname.match(/^\/v1\/assistants\/([^/]+)(\/versions)?$/);
  if (assistantMatch) {
    if (assistantMatch[1] !== assistant.id) return send(response, 404, { error: 'not_found' });
    if (assistantMatch[2] && request.method === 'GET') return send(response, 200, assistantVersions);
    if (!assistantMatch[2] && request.method === 'GET') return send(response, 200, assistant, { etag: `"${assistant.version}"` });
    if (!assistantMatch[2] && request.method === 'PATCH') {
      if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
      const expected = Number(String(request.headers['if-match'] || '').replaceAll('"', ''));
      if (expected !== assistant.version) return send(response, 412, { error: 'version_conflict' });
      const patch = await body(request);
      assistant = { ...assistant, ...patch, version: assistant.version + 1 };
      assistantVersions.push(structuredClone(assistant));
      return send(response, 200, assistant, { etag: `"${assistant.version}"` });
    }
  }

  if (request.method === 'GET' && url.pathname === '/v1/knowledge-bases') {
    return send(response, 200, knowledgeBases.filter((kb) => visibleKB(actor, kb.id)));
  }
  if (request.method === 'POST' && url.pathname === '/v1/knowledge-bases') {
    if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
    const input = await body(request);
    const kb = {
      id: `00000000-0000-4000-8000-0000000000${String(knowledgeBases.length + 1).padStart(2, '0')}`,
      name: input.name,
      description: input.description ?? '',
      revision: 1,
      active_version: 1,
      created_at: '2026-10-22T00:00:00Z',
      updated_at: '2026-10-22T00:00:00Z',
    };
    knowledgeBases.push(kb);
    versions.set(kb.id, [{
      version: 1,
      state: 'active',
      config: input.config ?? { chunk_size: 1000, chunk_overlap: 200 },
      created_at: '2026-10-22T00:00:00Z',
      chunk_count: 0,
      attempts: 0,
    }]);
    return send(response, 201, kb, { etag: '"1"' });
  }

  const kbMatch = url.pathname.match(/^\/v1\/knowledge-bases\/([^/]+)(\/versions|\/export)?$/);
  if (kbMatch) {
    const kb = visibleKB(actor, kbMatch[1]);
    if (!kb) return send(response, 404, { error: 'not_found' });
    if (kbMatch[2] === '/export' && request.method === 'GET') return send(response, 200, exportFor(kb));
    if (kbMatch[2] === '/versions' && request.method === 'GET') return send(response, 200, versions.get(kb.id));
    if (kbMatch[2] === '/versions' && request.method === 'POST') {
      if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
      const input = await body(request);
      const list = versions.get(kb.id);
      const next = {
        version: list.length + 1,
        state: 'active',
        config: input.config ?? { chunk_size: 1000, chunk_overlap: 200 },
        created_at: '2026-10-22T00:00:00Z',
        chunk_count: 0,
        attempts: 0,
      };
      list.unshift(next);
      kb.active_version = next.version;
      kb.revision += 1;
      return send(response, 201, next);
    }
    if (!kbMatch[2] && request.method === 'GET') return send(response, 200, kb, { etag: `"${kb.revision}"` });
    if (!kbMatch[2] && request.method === 'PATCH') {
      if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
      const patch = await body(request);
      Object.assign(kb, patch);
      kb.revision += 1;
      kb.updated_at = '2026-10-22T00:00:00Z';
      return send(response, 200, kb, { etag: `"${kb.revision}"` });
    }
    if (!kbMatch[2] && request.method === 'DELETE') {
      if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
      knowledgeBases.splice(knowledgeBases.indexOf(kb), 1);
      response.writeHead(204);
      response.end();
      return;
    }
  }

  if (request.method === 'POST' && url.pathname === '/v1/conversations') {
    const input = await body(request);
    const id = '00000000-0000-4000-8000-0000000000c9';
    liveMessages.set(id, []);
    return send(response, 201, { id, assistant_id: input.assistant_id });
  }

  const conversationMatch = url.pathname.match(/^\/v1\/conversations\/([^/]+)\/messages$/);
  if (conversationMatch && request.method === 'GET') {
    return send(response, 200, liveMessages.get(conversationMatch[1]) ?? []);
  }
  if (conversationMatch && request.method === 'POST') {
    const conversationId = conversationMatch[1];
    const input = await body(request);
    const key = request.headers['idempotency-key'] || 'live-key';
    const runId = '00000000-0000-4000-8000-000000000199';
    sseHeaders(response, runId);
    const userMessages = liveMessages.get(conversationId) ?? [];
    liveMessages.set(conversationId, [...userMessages, { role: 'user', content: input.content }]);

    if (conversationId.endsWith('c5')) {
      writeSSE(response, 'dup-1', 'agent.started', {});
      writeSSE(response, 'dup-2', 'response.delta', { text: 'Ciao' });
      writeSSE(response, 'dup-2', 'response.delta', { text: 'Ciao' });
      writeSSE(response, 'dup-3', 'response.completed', { text: 'Ciao', usage: { input_tokens: 1, output_tokens: 1 } });
      response.end();
      return;
    }
    if (conversationId.endsWith('c6')) {
      writeSSE(response, 'int-1', 'agent.started', {});
      writeSSE(response, 'int-2', 'response.delta', { text: 'Parziale' });
      response.end();
      return;
    }
    if (conversationId.endsWith('c7')) {
      const count = (replayCounts.get(key) ?? 0) + 1;
      replayCounts.set(key, count);
      writeSSE(response, 'rep-1', 'agent.started', {});
      writeSSE(response, 'rep-2', 'response.delta', { text: 'Risposta' });
      if (count > 1) {
        writeSSE(response, 'rep-3', 'response.completed', { text: 'Risposta completa', usage: { input_tokens: 2, output_tokens: 2 } });
      }
      response.end();
      return;
    }
    if (conversationId.endsWith('c8')) {
      writeSSE(response, 'cancel-1', 'agent.started', {});
      writeSSE(response, 'cancel-2', 'response.delta', { text: 'Attendo…' });
      await new Promise((resolve) => {
        request.on('close', resolve);
        setTimeout(resolve, 5000);
      });
      response.end();
      return;
    }
    writeSSE(response, 'live-1', 'agent.started', {});
    writeSSE(response, 'live-2', 'response.delta', { text: 'Ciao dal mock' });
    writeSSE(response, 'live-3', 'response.completed', {
      text: 'Ciao dal mock',
      usage: { input_tokens: 3, output_tokens: 4 },
      citations: [{
        citation_id: 'citation-live',
        chunk_id: 'a'.repeat(64),
        knowledge_base_id: publicKB.id,
        document_id: '00000000-0000-4000-8000-0000000000d0',
        document_hash: 'b'.repeat(64),
        document_version: 1,
        page: 1,
        start: 0,
        end: 10,
      }],
    });
    response.end();
    return;
  }

  if (request.method === 'GET' && url.pathname === '/v1/agent-runs') {
    return send(response, 200, runs);
  }
  const runMatch = url.pathname.match(/^\/v1\/agent-runs\/([^/]+)(\/cancel)?$/);
  if (runMatch) {
    const run = runs.find((item) => item.id === runMatch[1]);
    if (!run) return send(response, 404, { error: 'not_found' });
    if (runMatch[2] && request.method === 'POST') {
      run.status = 'cancelled';
      run.updated_at = '2026-10-22T00:00:02Z';
      return send(response, 200, run);
    }
    if (request.method === 'GET') return send(response, 200, run);
  }

  if (request.method === 'GET' && url.pathname === '/v1/audit-events') {
    if (!actor.scopes.includes('audit:read')) return send(response, 403, { code: 'forbidden' });
    const runId = url.searchParams.get('run_id');
    const action = url.searchParams.get('action');
    const targetId = url.searchParams.get('target_id');
    const limit = Number(url.searchParams.get('limit') || 0);
    let events = auditEvents.filter((event) =>
      (!runId || event.run_id === runId) &&
      (!action || event.action === action) &&
      (!targetId || event.target_id === targetId),
    );
    if (limit > 0) events = events.slice(0, limit);
    return send(response, 200, events);
  }

  if (request.method === 'GET' && url.pathname === '/v1/credentials') {
    if (!actor.scopes.includes('credentials:read')) return send(response, 403, { code: 'forbidden' });
    return send(response, 200, credentials);
  }
  if (request.method === 'POST' && url.pathname === '/v1/credentials') {
    if (!actor.scopes.includes('credentials:write')) return send(response, 403, { code: 'forbidden' });
    const input = await body(request);
    const now = new Date();
    const credential = {
      id: crypto.randomUUID(),
      principal_id: input.principal_id || `service-${credentials.length + 1}`,
      role: input.role,
      scopes: input.scopes ?? [],
      expires_at: input.expires_at || new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      revoked_at: null,
      created_at: now.toISOString(),
    };
    credentials.push(credential);
    return send(response, 201, { credential, api_key: `uai_test_${crypto.randomUUID()}` });
  }
  const credentialMatch = url.pathname.match(/^\/v1\/credentials\/([^/]+)\/(rotate|revoke)$/);
  if (credentialMatch && request.method === 'POST') {
    if (!actor.scopes.includes('credentials:write')) return send(response, 403, { code: 'forbidden' });
    const credential = credentials.find((item) => item.id === credentialMatch[1]);
    if (!credential) return send(response, 404, { code: 'not_found' });
    if (credentialMatch[2] === 'rotate') {
      const input = await body(request);
      credential.expires_at =
        input.expires_at || new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
      return send(response, 200, { credential, api_key: `uai_test_${crypto.randomUUID()}` });
    }
    credential.revoked_at = new Date().toISOString();
    return send(response, 200, { status: 'revoked' });
  }

  if (request.method === 'GET' && url.pathname === '/v1/documents') {
    const kbId = url.searchParams.get('knowledge_base_id');
    return send(response, 200, documents.filter(
      (document) => !kbId || (visibleKB(actor, document.knowledge_base_id) && document.knowledge_base_id === kbId),
    ));
  }

  if (request.method === 'POST' && url.pathname === '/v1/documents') {
    if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
    const parsed = multipart(await rawBody(request), request.headers['content-type']);
    const kb = visibleKB(actor, parsed.fields.knowledge_base_id);
    if (!kb || !parsed.fields.file) return send(response, 422, { error: 'invalid_upload' });
    const id = `00000000-0000-4000-8000-0000000000d${documents.length + 1}`;
    const document = {
      id,
      knowledge_base_id: kb.id,
      filename: parsed.fields.file.filename,
      title: parsed.fields.title || parsed.fields.file.filename,
      mime_type: 'text/plain',
      size_bytes: parsed.fields.file.value.length,
      sha256: 'b'.repeat(64),
      created_at: '2026-10-22T00:00:00Z',
      ingestion_state: 'queued',
    };
    documents.push(document);
    jobs.set(id, {
      id: `job-${documents.length}`,
      document_id: id,
      state: 'queued',
      attempts: 0,
      created_at: '2026-10-22T00:00:00Z',
      updated_at: '2026-10-22T00:00:00Z',
    });
    chunks.push({
      chunk_id: 'a'.repeat(64),
      knowledge_base_id: kb.id,
      document_id: id,
      document_hash: document.sha256,
      document_version: 1,
      page: 1,
      start: 0,
      end: parsed.fields.file.value.length,
      text: parsed.fields.file.value,
      chunk_size: 1000,
      overlap: 0,
    });
    return send(response, 201, document);
  }

  const documentMatch = url.pathname.match(/^\/v1\/documents\/([^/]+)(\/job(?:\/cancel)?)?$/);
  if (documentMatch) {
    const document = documents.find((item) => item.id === documentMatch[1]);
    if (!document || !visibleKB(actor, document.knowledge_base_id)) {
      return send(response, 404, { error: 'not_found' });
    }
    if (!documentMatch[2] && request.method === 'GET') return send(response, 200, document);
    if (!documentMatch[2] && request.method === 'DELETE') {
      if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
      documents.splice(documents.indexOf(document), 1);
      jobs.delete(document.id);
      response.writeHead(204);
      response.end();
      return;
    }
    if (documentMatch[2] === '/job' && request.method === 'GET') {
      const job = jobs.get(document.id);
      if (job.state === 'queued') {
        job.state = 'running';
        document.ingestion_state = 'running';
      } else if (job.state === 'running') {
        job.state = 'completed';
        document.ingestion_state = 'completed';
      }
      return send(response, 200, job);
    }
    if (documentMatch[2] === '/job/cancel' && request.method === 'POST') {
      const job = jobs.get(document.id);
      job.state = 'cancelled';
      document.ingestion_state = 'cancelled';
      return send(response, 200, job);
    }
  }

  if (request.method === 'GET' && url.pathname === '/v1/tools') {
    return send(response, 200, tools);
  }

  if (request.method === 'GET' && url.pathname === '/v1/plugins') {
    if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
    return send(response, 200, pluginCatalog);
  }

  const pluginMatch = url.pathname.match(/^\/v1\/plugins\/([^/]+)(\/health)?$/);
  if (pluginMatch) {
    const plugin = pluginCatalog.plugins.find((item) => item.manifest.id === pluginMatch[1]);
    if (!plugin) return send(response, 404, { error: 'not_found' });
    if (pluginMatch[2] === '/health' && request.method === 'GET') {
      return send(response, 200, { status: plugin.state === 'active' ? 'ok' : 'unknown' });
    }
    if (!pluginMatch[2] && request.method === 'PUT') {
      if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
      const input = await body(request);
      pluginCatalog.desired[plugin.manifest.id] = Boolean(input.enabled);
      plugin.state = input.enabled ? 'active' : 'inactive';
      plugin.manifest.config = input.config ?? {};
      pluginCatalog.revision += 1;
      return send(response, 200, { revision: pluginCatalog.revision, applied: true });
    }
    if (!pluginMatch[2] && request.method === 'DELETE') {
      pluginCatalog.desired[plugin.manifest.id] = false;
      plugin.state = 'inactive';
      pluginCatalog.revision += 1;
      return send(response, 200, { revision: pluginCatalog.revision, applied: true });
    }
  }

  if (request.method === 'GET' && url.pathname === '/v1/approvals') {
    if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
    return send(response, 200, approvals);
  }

  const approvalMatch = url.pathname.match(/^\/v1\/approvals\/([^/]+)(\/(?:approve|reject))?$/);
  if (approvalMatch) {
    if (actor.role === 'reader') return send(response, 403, { error: 'forbidden' });
    const approval = approvals.find((item) => item.id === approvalMatch[1]);
    if (!approval) return send(response, 404, { error: 'not_found' });
    if (!approvalMatch[2] && request.method === 'GET') return send(response, 200, approval);
    if (approvalMatch[2] && request.method === 'POST') {
      if (approval.status !== 'pending' || new Date(approval.expires_at).getTime() <= Date.now()) {
        return send(response, 409, { error: 'approval_not_pending' });
      }
      approval.status = approvalMatch[2] === '/approve' ? 'approved' : 'rejected';
      approval.decided_by = actor.principal_id;
      approval.decided_at = new Date().toISOString();
      return send(response, 200, approval);
    }
  }

  send(response, 404, { error: 'not_found' });
});

server.listen(port, '127.0.0.1', () => console.log(`mock gateway on ${port}`));
