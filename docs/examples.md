# Examples

Copy-paste examples for the public API, RAG, tools, widgets, SDKs and operations.
All examples assume a local installation and that you export:

```bash
export UAI_BASE_URL=http://127.0.0.1:8080
export UAI_API_KEY='your admin API key'
```

Replace UUID placeholders and idempotency keys with your own values. The public
OpenAPI contract is authoritative:
`packages/api-contract/public.openapi.json`.

## Health and identity

```bash
curl -s "$UAI_BASE_URL/v1/health"

curl -s "$UAI_BASE_URL/v1/me" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

`/v1/health` checks the gateway and PostgreSQL. It does not prove the external
model is reachable.

## Assistants

Create:

```bash
curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Support assistant",
    "description": "Answers product questions.",
    "model": "llama3.2:3b",
    "system_prompt": "Answer clearly and cite sources.",
    "memory": {"conversation": true, "semantic": false},
    "limits": {"max_steps": 4, "max_tool_calls": 8, "max_tokens": 4096}
  }'
```

List and read:

```bash
curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY"

curl -s "$UAI_BASE_URL/v1/assistants/<assistant-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Update with optimistic concurrency. Read the `ETag` first, then send `If-Match`:

```bash
curl -i -s "$UAI_BASE_URL/v1/assistants/<assistant-id>" \
  -H "Authorization: Bearer $UAI_API_KEY" | grep -i '^ETag:'

curl -s -X PATCH "$UAI_BASE_URL/v1/assistants/<assistant-id>" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "<revision>"' \
  -d '{"system_prompt":"Answer concisely."}'
```

Every update creates an immutable version:

```bash
curl -s "$UAI_BASE_URL/v1/assistants/<assistant-id>/versions" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Model catalog:

```bash
curl -s "$UAI_BASE_URL/v1/models" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

## Conversations and SSE

Create a conversation:

```bash
curl -s "$UAI_BASE_URL/v1/conversations" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"assistant_id":"<assistant-id>"}'
```

Stream a message:

```bash
curl -N "$UAI_BASE_URL/v1/conversations/<conversation-id>/messages" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: example-1' \
  -d '{"content":"Hello, what can you do?"}'
```

SSE frames look like:

```text
id: <event-id>
event: response.delta
data: {"event_id":"...","event_type":"response.delta","event_version":1,...,"payload":{"text":"Hello"}}

id: <event-id>
event: response.completed
data: {"event_type":"response.completed",...,"payload":{"text":"Hello ...","citations":[]}}
```

Only `response.completed` is success. `agent.failed` and `agent.cancelled` are
terminal failures. EOF without a terminal event is not success.

Replay the same request:

```bash
curl -N "$UAI_BASE_URL/v1/conversations/<conversation-id>/messages" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: example-1' \
  -d '{"content":"Hello, what can you do?"}'
```

Same key + same body returns the persisted events. Same key + different body, or
a still-running key, returns `409`.

Completed history:

```bash
curl -s "$UAI_BASE_URL/v1/conversations/<conversation-id>/messages" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Run status and cancel:

```bash
curl -s "$UAI_BASE_URL/v1/agent-runs" \
  -H "Authorization: Bearer $UAI_API_KEY"

curl -s "$UAI_BASE_URL/v1/agent-runs/<run-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"

curl -s -X POST "$UAI_BASE_URL/v1/agent-runs/<run-id>/cancel" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Delete a conversation (owner/admin):

```bash
curl -s -X DELETE "$UAI_BASE_URL/v1/conversations/<conversation-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

## Credentials

Create a scoped reader credential:

```bash
curl -s "$UAI_BASE_URL/v1/credentials" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "principal_id": "ci-reader",
    "role": "reader",
    "scopes": ["assistants:read", "messages:read"],
    "expires_at": "2026-12-31T00:00:00Z"
  }'
```

The plaintext API key is returned once. List credentials:

```bash
curl -s "$UAI_BASE_URL/v1/credentials" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Rotate or revoke a credential other than the current one:

```bash
curl -s -X POST "$UAI_BASE_URL/v1/credentials/<credential-id>/rotate" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"expires_at":"2027-01-31T00:00:00Z"}'

curl -s -X POST "$UAI_BASE_URL/v1/credentials/<credential-id>/revoke" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

## Knowledge base and ingestion

Create a knowledge base with an embedding identity:

```bash
curl -s "$UAI_BASE_URL/v1/knowledge-bases" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Product documentation",
    "description": "Uploaded product docs.",
    "config": {"chunk_size": 1000, "chunk_overlap": 200},
    "embedding": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "version": "nomic-embed-text-v1.5",
      "dimension": 768
    }
  }'
```

Upload a document:

```bash
curl -s "$UAI_BASE_URL/v1/documents" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -F "knowledge_base_id=<kb-id>" \
  -F "title=Product guide" \
  -F "file=@./product-guide.txt"
```

Accepted formats: TXT, Markdown, HTML, PDF and DOCX. The server validates the
real MIME type and the size limits (20 MiB, 2M normalized characters).

Poll the job:

```bash
curl -s "$UAI_BASE_URL/v1/documents/<document-id>/job" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Possible states: `queued`, `running`, `completed`, `failed`, `cancelled`. Cancel
a queued/running job:

```bash
curl -s -X POST "$UAI_BASE_URL/v1/documents/<document-id>/job/cancel" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

List documents for a KB:

```bash
curl -s "$UAI_BASE_URL/v1/documents?knowledge_base_id=<kb-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Get/delete a document:

```bash
curl -s "$UAI_BASE_URL/v1/documents/<document-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"

curl -s -X DELETE "$UAI_BASE_URL/v1/documents/<document-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

## Reindex and index readiness

Read the current KB revision:

```bash
curl -i -s "$UAI_BASE_URL/v1/knowledge-bases/<kb-id>" \
  -H "Authorization: Bearer $UAI_API_KEY" | grep -i '^ETag:'
```

Create a new version to rebuild the vector index:

```bash
curl -s "$UAI_BASE_URL/v1/knowledge-bases/<kb-id>/versions" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "<revision>"' \
  -d '{
    "config": {"chunk_size": 1000, "chunk_overlap": 200},
    "embedding": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "version": "nomic-embed-text-v1.5",
      "dimension": 768
    }
  }'
```

Wait for an active version with chunks:

```bash
curl -s "$UAI_BASE_URL/v1/knowledge-bases/<kb-id>/versions" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

The version must show `state: active`, `chunk_count > 0` and a `collection_name`
before RAG can use it. Export provenance:

```bash
curl -s "$UAI_BASE_URL/v1/knowledge-bases/<kb-id>/export" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

## RAG with citations

Create an assistant bound to the KB and the RAG directive:

```bash
curl -s "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "RAG assistant",
    "model": "llama3.2:3b",
    "system_prompt": "Answer only from the supplied context.",
    "knowledge_base_ids": ["<kb-id>"],
    "directives": ["builtin.rag"]
  }'
```

Ask a question through a conversation (same SSE flow as above). The completed
event contains `payload.citations`:

```json
{
  "event_type": "response.completed",
  "payload": {
    "text": "The answer is ... [C1]",
    "citations": [
      {
        "citation_id": "C1",
        "chunk_id": "…",
        "knowledge_base_id": "…",
        "document_id": "…",
        "document_hash": "…",
        "document_version": 1,
        "page": 1,
        "start": 0,
        "end": 420
      }
    ]
  }
}
```

Validate a citation against the KB export: match `chunk_id`, document, version,
page and offsets. Retrieval is filtered by authorized KB and active index version;
an empty ACL or missing index fails closed.

## Tools and approvals

Tool registration is host-owned; the public API exposes the catalog:

```bash
curl -s "$UAI_BASE_URL/v1/tools" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Pending approvals:

```bash
curl -s "$UAI_BASE_URL/v1/approvals" \
  -H "Authorization: Bearer $UAI_API_KEY"

curl -s "$UAI_BASE_URL/v1/approvals/<approval-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Approve or reject (requires `approvals:write` and a run waiting for approval):

```bash
curl -s -X POST "$UAI_BASE_URL/v1/approvals/<approval-id>/approve" \
  -H "Authorization: Bearer $UAI_API_KEY"

curl -s -X POST "$UAI_BASE_URL/v1/approvals/<approval-id>/reject" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

An approval is bound to run, tool, version, argument digest and policy snapshot.
It expires; it cannot be edited or reused. Mutating tool effects are idempotent.

## Plugins

The public API manages installed plugins; it does not install arbitrary code:

```bash
curl -s "$UAI_BASE_URL/v1/plugins" \
  -H "Authorization: Bearer $UAI_API_KEY"

curl -s "$UAI_BASE_URL/v1/plugins/<plugin-id>/health" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Configuration/activation is an admin action documented in [plugins.md](plugins.md)
and [console.md](console.md).

## Widget token

Allow the browser origin in `UAI_WIDGET_ORIGINS` first, then mint a short-lived
token bound to one assistant and conversation:

```bash
curl -s "$UAI_BASE_URL/v1/widget/tokens" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "assistant_id": "<assistant-id>",
    "conversation_id": "<conversation-id>",
    "origin": "https://app.example.com",
    "subject": "user-123",
    "expires_in_seconds": 900
  }'
```

The response contains the one-time `token`. Use it only from that origin:

```bash
curl -N "$UAI_BASE_URL/v1/conversations/<conversation-id>/messages" \
  -H "Authorization: Bearer <widget-token>" \
  -H "Origin: https://app.example.com" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: widget-1' \
  -d '{"content":"Hello"}'
```

Revoke it when the session ends:

```bash
curl -s -X DELETE "$UAI_BASE_URL/v1/widget/tokens/<token-id>" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

## SDK examples

### TypeScript

```ts
import { UniversalAIKit } from '@universal-ai-kit/sdk'

const client = new UniversalAIKit({
  baseUrl: process.env.UAI_BASE_URL!,
  apiKey: process.env.UAI_API_KEY!,
})

const assistant = await client.assistants.create({
  name: 'App assistant',
  model: 'llama3.2:3b',
  system_prompt: 'Be concise.',
})
const conversation = await client.conversations.create({
  assistant_id: assistant.id,
})
const stream = await client.conversations.sendMessage(
  conversation.id,
  { content: 'Hello' },
  { idempotencyKey: crypto.randomUUID() },
)
for await (const event of stream) {
  if (event.event_type === 'response.delta') process.stdout.write(event.payload.text)
}
```

### Go

```go
client, err := uai.New(os.Getenv("UAI_BASE_URL"), os.Getenv("UAI_API_KEY"))
if err != nil {
    log.Fatal(err)
}
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()

assistant, err := client.CreateAssistant(ctx, uai.AssistantInput{
    Name: "App assistant", Model: "llama3.2:3b", SystemPrompt: "Be concise.",
})
if err != nil {
    log.Fatal(err)
}
conversation, err := client.CreateConversation(ctx, uai.ConversationInput{
    AssistantID: assistant.ID,
})
if err != nil {
    log.Fatal(err)
}
stream, err := client.SendMessage(ctx, conversation.ID,
    uai.MessageInput{Content: "Hello"}, "app-"+uuid.NewString())
if err != nil {
    log.Fatal(err)
}
defer stream.Close()
for {
    event, err := stream.Next()
    if errors.Is(err, io.EOF) {
        break
    }
    if err != nil {
        log.Fatal(err)
    }
    if event.EventType == "response.delta" {
        var payload uai.TextPayload
        _ = event.DecodePayload(&payload)
        fmt.Print(payload.Text)
    }
}
```

### PHP

```php
use UniversalAIKit\Client;

$client = new Client(
    baseUrl: getenv('UAI_BASE_URL') ?: 'http://127.0.0.1:8080',
    apiKey: getenv('UAI_API_KEY') ?: throw new RuntimeException('missing key'),
);

$assistant = $client->createAssistant([
    'name' => 'App assistant',
    'model' => 'llama3.2:3b',
    'system_prompt' => 'Be concise.',
]);
$conversation = $client->createConversation(['assistant_id' => $assistant['id']]);
$stream = $client->streamMessage(
    $conversation['id'],
    ['content' => 'Hello'],
    idempotencyKey: bin2hex(random_bytes(16)),
);
foreach ($stream as $event) {
    if ($event['event_type'] === 'response.delta') {
        echo $event['payload']['text'];
    }
}
```

See the package READMEs for exact generated types and error classes.

## Docker and operations

Start and inspect:

```bash
docker compose up -d --build --wait
docker compose --profile full up -d --build --wait
docker compose ps
docker compose logs -f gateway runtime worker
```

Graceful shutdown:

```bash
docker compose stop gateway
docker compose start gateway
```

Backup and restore:

```bash
deploy/backup.sh --output backups/$(date -u +%Y%m%dT%H%M%SZ)
cd backups/<timestamp> && sha256sum -c SHA256SUMS
deploy/restore.sh --backup backups/<timestamp> --reset-target --start
```

Upgrade:

```bash
deploy/backup.sh --output backups/pre-upgrade
docker compose stop gateway runtime worker
# update images/tags from the verified release bundle
docker compose up -d --wait postgres
docker compose up -d --wait gateway
docker compose up -d --wait runtime worker
```

Two installations:

```bash
docker compose --env-file .env.a up -d --wait
docker compose --env-file .env.b up -d --wait
```

Use separate `.env.a`/`.env.b` files with distinct `COMPOSE_PROJECT_NAME`, ports,
credentials and volumes; do not share state. The full checks:

```bash
make e2e
make e2e-upgrade
make e2e-two-instances
make e2e-restore
make test-console-browser
make release-dry-run
```

## Error examples

```bash
# 401: wrong key
curl -i "$UAI_BASE_URL/v1/me" -H 'Authorization: Bearer wrong'

# 409: same idempotency key, different body
curl -i "$UAI_BASE_URL/v1/conversations/<id>/messages" \
  -H "Authorization: Bearer $UAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: example-1' \
  -d '{"content":"different"}'

# 429: rate limit (Retry-After is returned)
curl -i "$UAI_BASE_URL/v1/assistants" \
  -H "Authorization: Bearer $UAI_API_KEY"
```

Error bodies use `{"error":"stable_code"}`. Do not branch on provider text; use
the stable `error`/event code.
