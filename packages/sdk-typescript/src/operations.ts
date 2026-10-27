export interface Operation {
  readonly method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  readonly path: string;
  readonly requiresIdempotencyKey?: true;
  readonly requiresIfMatch?: true;
}

/**
 * The public API operations, kept in lockstep with
 * packages/api-contract/public.openapi.json by tests/contract.test.ts.
 */
export const operations = {
  health: { method: 'GET', path: '/v1/health' },
  me: { method: 'GET', path: '/v1/me' },
  listAssistants: { method: 'GET', path: '/v1/assistants' },
  createAssistant: { method: 'POST', path: '/v1/assistants' },
  getAssistant: { method: 'GET', path: '/v1/assistants/{id}' },
  updateAssistant: {
    method: 'PATCH',
    path: '/v1/assistants/{id}',
    requiresIfMatch: true,
  },
  listAssistantVersions: {
    method: 'GET',
    path: '/v1/assistants/{id}/versions',
  },
  createConversation: { method: 'POST', path: '/v1/conversations' },
  deleteConversation: {
    method: 'DELETE',
    path: '/v1/conversations/{id}',
  },
  getMessages: {
    method: 'GET',
    path: '/v1/conversations/{id}/messages',
  },
  sendMessage: {
    method: 'POST',
    path: '/v1/conversations/{id}/messages',
    requiresIdempotencyKey: true,
  },
  listCredentials: { method: 'GET', path: '/v1/credentials' },
  createCredential: { method: 'POST', path: '/v1/credentials' },
  rotateCredential: {
    method: 'POST',
    path: '/v1/credentials/{id}/rotate',
  },
  revokeCredential: {
    method: 'POST',
    path: '/v1/credentials/{id}/revoke',
  },
  listModels: { method: 'GET', path: '/v1/models' },
  listTools: { method: 'GET', path: '/v1/tools' },
  listPlugins: { method: 'GET', path: '/v1/plugins' },
  configurePlugin: {
    method: 'PUT',
    path: '/v1/plugins/{id}',
    requiresIfMatch: true,
  },
  removePluginConfiguration: {
    method: 'DELETE',
    path: '/v1/plugins/{id}',
    requiresIfMatch: true,
  },
  pluginHealth: { method: 'GET', path: '/v1/plugins/{id}/health' },
  listKnowledgeBases: { method: 'GET', path: '/v1/knowledge-bases' },
  createKnowledgeBase: { method: 'POST', path: '/v1/knowledge-bases' },
  getKnowledgeBase: { method: 'GET', path: '/v1/knowledge-bases/{id}' },
  updateKnowledgeBase: {
    method: 'PATCH',
    path: '/v1/knowledge-bases/{id}',
    requiresIfMatch: true,
  },
  deleteKnowledgeBase: {
    method: 'DELETE',
    path: '/v1/knowledge-bases/{id}',
    requiresIfMatch: true,
  },
  listKnowledgeBaseVersions: {
    method: 'GET',
    path: '/v1/knowledge-bases/{id}/versions',
  },
  createKnowledgeBaseVersion: {
    method: 'POST',
    path: '/v1/knowledge-bases/{id}/versions',
    requiresIfMatch: true,
  },
  listDocuments: { method: 'GET', path: '/v1/documents' },
  uploadDocument: { method: 'POST', path: '/v1/documents' },
  getDocument: { method: 'GET', path: '/v1/documents/{id}' },
  deleteDocument: { method: 'DELETE', path: '/v1/documents/{id}' },
  getDocumentJob: { method: 'GET', path: '/v1/documents/{id}/job' },
  cancelDocumentJob: {
    method: 'POST',
    path: '/v1/documents/{id}/job/cancel',
  },
  exportKnowledgeBase: {
    method: 'GET',
    path: '/v1/knowledge-bases/{id}/export',
  },
  listAgentRuns: { method: 'GET', path: '/v1/agent-runs' },
  getAgentRun: { method: 'GET', path: '/v1/agent-runs/{id}' },
  cancelAgentRun: { method: 'POST', path: '/v1/agent-runs/{id}/cancel' },
  listApprovals: { method: 'GET', path: '/v1/approvals' },
  getApproval: { method: 'GET', path: '/v1/approvals/{id}' },
  approveApproval: {
    method: 'POST',
    path: '/v1/approvals/{id}/approve',
  },
  rejectApproval: {
    method: 'POST',
    path: '/v1/approvals/{id}/reject',
  },
  listAuditEvents: { method: 'GET', path: '/v1/audit-events' },
  getProvider: { method: 'GET', path: '/v1/provider' },
  updateProvider: {
    method: 'PUT',
    path: '/v1/provider',
    requiresIfMatch: true,
  },
  discoverProviderModels: { method: 'POST', path: '/v1/provider/models' },
  createWidgetToken: { method: 'POST', path: '/v1/widget/tokens' },
  revokeWidgetToken: {
    method: 'DELETE',
    path: '/v1/widget/tokens/{id}',
  },
} as const satisfies Record<string, Operation>;

export type OperationId = keyof typeof operations;
