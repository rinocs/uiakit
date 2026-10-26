package uai

// Operation describes one public HTTP operation. It is kept in lockstep with
// packages/api-contract/public.openapi.json by TestOperationsMatchPublicContract.
type Operation struct {
	Method                 string
	Path                   string
	RequiresIdempotencyKey bool
	RequiresIfMatch        bool
}

var Operations = map[string]Operation{
	"health":                     {Method: "GET", Path: "/v1/health"},
	"me":                         {Method: "GET", Path: "/v1/me"},
	"listAssistants":             {Method: "GET", Path: "/v1/assistants"},
	"createAssistant":            {Method: "POST", Path: "/v1/assistants"},
	"getAssistant":               {Method: "GET", Path: "/v1/assistants/{id}"},
	"updateAssistant":            {Method: "PATCH", Path: "/v1/assistants/{id}", RequiresIfMatch: true},
	"listAssistantVersions":      {Method: "GET", Path: "/v1/assistants/{id}/versions"},
	"createConversation":         {Method: "POST", Path: "/v1/conversations"},
	"deleteConversation":         {Method: "DELETE", Path: "/v1/conversations/{id}"},
	"getMessages":                {Method: "GET", Path: "/v1/conversations/{id}/messages"},
	"sendMessage":                {Method: "POST", Path: "/v1/conversations/{id}/messages", RequiresIdempotencyKey: true},
	"listCredentials":            {Method: "GET", Path: "/v1/credentials"},
	"createCredential":           {Method: "POST", Path: "/v1/credentials"},
	"rotateCredential":           {Method: "POST", Path: "/v1/credentials/{id}/rotate"},
	"revokeCredential":           {Method: "POST", Path: "/v1/credentials/{id}/revoke"},
	"listModels":                 {Method: "GET", Path: "/v1/models"},
	"listTools":                  {Method: "GET", Path: "/v1/tools"},
	"listPlugins":                {Method: "GET", Path: "/v1/plugins"},
	"configurePlugin":            {Method: "PUT", Path: "/v1/plugins/{id}", RequiresIfMatch: true},
	"removePluginConfiguration":  {Method: "DELETE", Path: "/v1/plugins/{id}", RequiresIfMatch: true},
	"pluginHealth":               {Method: "GET", Path: "/v1/plugins/{id}/health"},
	"listKnowledgeBases":         {Method: "GET", Path: "/v1/knowledge-bases"},
	"createKnowledgeBase":        {Method: "POST", Path: "/v1/knowledge-bases"},
	"getKnowledgeBase":           {Method: "GET", Path: "/v1/knowledge-bases/{id}"},
	"updateKnowledgeBase":        {Method: "PATCH", Path: "/v1/knowledge-bases/{id}", RequiresIfMatch: true},
	"deleteKnowledgeBase":        {Method: "DELETE", Path: "/v1/knowledge-bases/{id}", RequiresIfMatch: true},
	"listKnowledgeBaseVersions":  {Method: "GET", Path: "/v1/knowledge-bases/{id}/versions"},
	"createKnowledgeBaseVersion": {Method: "POST", Path: "/v1/knowledge-bases/{id}/versions", RequiresIfMatch: true},
	"listDocuments":              {Method: "GET", Path: "/v1/documents"},
	"uploadDocument":             {Method: "POST", Path: "/v1/documents"},
	"getDocument":                {Method: "GET", Path: "/v1/documents/{id}"},
	"deleteDocument":             {Method: "DELETE", Path: "/v1/documents/{id}"},
	"getDocumentJob":             {Method: "GET", Path: "/v1/documents/{id}/job"},
	"cancelDocumentJob":          {Method: "POST", Path: "/v1/documents/{id}/job/cancel"},
	"exportKnowledgeBase":        {Method: "GET", Path: "/v1/knowledge-bases/{id}/export"},
	"listAgentRuns":              {Method: "GET", Path: "/v1/agent-runs"},
	"getAgentRun":                {Method: "GET", Path: "/v1/agent-runs/{id}"},
	"cancelAgentRun":             {Method: "POST", Path: "/v1/agent-runs/{id}/cancel"},
	"listApprovals":              {Method: "GET", Path: "/v1/approvals"},
	"getApproval":                {Method: "GET", Path: "/v1/approvals/{id}"},
	"approveApproval":            {Method: "POST", Path: "/v1/approvals/{id}/approve"},
	"rejectApproval":             {Method: "POST", Path: "/v1/approvals/{id}/reject"},
	"listAuditEvents":            {Method: "GET", Path: "/v1/audit-events"},
	"createWidgetToken":          {Method: "POST", Path: "/v1/widget/tokens"},
	"revokeWidgetToken":          {Method: "DELETE", Path: "/v1/widget/tokens/{id}"},
}
