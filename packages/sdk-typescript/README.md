# Universal AI Kit TypeScript SDK

Client tipizzato per la Public API e per lo stream SSE del gateway. Funziona in
Node.js 20+ e nei browser moderni, senza dipendenze runtime.

## Installazione

Il pacchetto è nel workspace:

```bash
npm install --prefix packages/sdk-typescript
npm run build --prefix packages/sdk-typescript
```

## Uso

```ts
import { UniversalAIKit } from '@universal-ai-kit/sdk';

const client = new UniversalAIKit({
  baseUrl: 'http://localhost:8080',
  apiKey: process.env.UAI_API_KEY!,
});

const assistants = await client.assistants.list();
const conversation = await client.conversations.create({
  assistant_id: assistants[0].id,
});

const stream = await client.conversations.sendMessage(
  conversation.id,
  { content: 'Riassumi i documenti caricati.' },
  { idempotencyKey: crypto.randomUUID() },
);

for await (const event of stream) {
  if (event.event_type === 'response.delta') {
    process.stdout.write(event.payload.text);
  }
}
```

`sendMessage` richiede una `Idempotency-Key` esplicita: lo SDK non la genera.
Ritentare la stessa richiesta con la stessa chiave recupera l'esito persistito.

## SSE e terminali

Lo stream emette eventi `RuntimeEvent` con payload discriminato:

- `agent.started`
- `response.delta`
- `response.completed`
- `agent.failed`
- `agent.cancelled`

`response.completed` è l'unico esito di successo. Se il corpo termina senza un
evento terminale, l'iterazione lancia `StreamIncompleteError`. `agent.failed` e
`agent.cancelled` vengono emessi e poi trasformati in `AgentFailedError` /
`AgentCancelledError`, così un consumer non può confondere una disconnessione o
un errore con un completamento.

Il parser SSE gestisce frame divisi tra chunk, UTF-8 spezzato, CRLF e righe
`data:` multiple.

## Abort e timeout

```ts
const controller = new AbortController();
const stream = await client.conversations.sendMessage(
  conversation.id,
  { content: '...' },
  { idempotencyKey: crypto.randomUUID(), signal: controller.signal },
);

controller.abort();
```

L'abort interrompe la richiesta e, per impostazione predefinita, chiede al
gateway di cancellare il run (`POST /v1/agent-runs/{id}/cancel`). Disabilitare
con `cancelOnAbort: false` solo se un altro componente possiede la
cancellazione.

## Errori

Tutti gli errori estendono `UAIError`:

- `APIError`: risposta non-2xx con `status`, `code` e `body`.
- `ValidationError`: input o header obbligatorio mancante.
- `AbortError`, `TimeoutError`, `NetworkError`.
- `StreamIncompleteError`, `StreamProtocolError`.
- `AgentFailedError`, `AgentCancelledError`.

## Sicurezza

Usare una API key amministrativa solo server-side. Per il browser usare un token
widget temporaneo e scope limitati, mai una key amministrativa nel bundle. Lo SDK
inoltra il bearer token fornito e non effettua logging delle credenziali.

## Sviluppo

```bash
cd packages/sdk-typescript
npm run generate       # rigenera src/generated.ts dal contratto OpenAPI
npm run check          # contratto + typecheck + test
npm run build
```

`src/generated.ts` è generato da `packages/api-contract/public.openapi.json`.
Non modificarlo a mano: il test di contratto fallisce se il file o la mappa
`src/operations.ts` divergono dall'OpenAPI pubblico.
