# Contratti v0.1.0

`public.openapi.json`: API gateway, OpenAPI 3.1.
`internal.openapi.json`: schemi FastAPI versionati, API privata, non un SDK pubblico.
L'endpoint interno richiede `Authorization: Bearer <INTERNAL_API_KEY>`.

SSE è UTF-8: `id: UUID`, `event: event_type`, `data: JSON`, riga vuota.
Envelope pubblico: event_id, event_type, event_version=1, timestamp UTC,
run_id, correlation_id, payload. I subscriber trattano gli eventi come immutabili.

- agent.started: `{}`.
- response.delta: `{"text":"..."}`.
- response.completed: `{"text":"risposta completa","usage":{"total_tokens":9}}`.
- agent.failed: `{"code":"provider_error"}` o errore normalizzato del gateway.

EOF senza evento terminale indica fallimento; il client non deve interpretarlo
come risposta completa. Nessun resume da Last-Event-ID: il replay restituisce
l'intero run. Consumare soltanto i delta per aggiornare il testo; completed
contiene nuovamente il testo completo per verifica e persistenza.

Internal RunRequest contiene prompt, modello, history user/assistant, run_id,
correlation_id e authority autenticata dal gateway. Authority assente conserva
compatibilità M1 con bootstrap senza scopes/tool grant. Gli URL provider e i privilegi non fanno parte dell'input.
Il runtime emette gli stessi envelope, ma il gateway valida e persiste l'esito
prima di esporre l'evento terminale al client pubblico.

Le API pubbliche credentials sono riservate a role admin e relativo scope; key,
rotation e revoca sono descritte in [auth.md](../../docs/auth.md). Le risorse sono
filtrate per principal; admin opera su tutte entro i propri scopes. Il DTO pubblico
del messaggio non accetta authority; soltanto il gateway aggiunge i claim interni.

M2-03: GET/PATCH assistant e GET versions usano snapshot immutabili ed ETag/If-Match.
Il DTO interno aggiunge assistant e model_snapshot opzionali per compatibilità v1;
la consistenza col prompt/modello top-level è validata. Il catalogo interno è
protetto e quello pubblico richiede models:read. Dettagli e limiti in
[assistants-models.md](../../docs/assistants-models.md).

## Lifecycle osservativo interno

`lifecycle.schema.json` descrive LifecycleEvent v1: tutte le 18 fasi previste,
metadata immutabili senza prompt/testo/argomenti/memoria e pairing fase/payload.
È il contratto dei subscriber trusted, distinto dai quattro frame SSE pubblici.
Le osservazioni dei frame pubblici ne conservano event_id e correlazione.
Schema generato dal core e confrontato nei test; nessuna nuova route pubblica.
Semantica di consegna, timeout e cancellazione in [events-hooks.md](../../docs/events-hooks.md).

## Catalogo tool — M2-07

GET /v1/tools richiede tools:read e restituisce ToolDefinition senza callable,
moduli o segreti. Il runtime espone GET /internal/v1/tools con Bearer interno.
Gli schemi input/output sono derivati dai modelli Pydantic approvati dall'host;
non abilitano import, esecuzione pubblica o fetch di $ref remoti.
Scope, executor standalone read-only e limiti in [tools.md](../../docs/tools.md).
