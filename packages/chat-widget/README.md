# Universal AI Kit Chat Widget

Web Component framework-agnostic per conversazioni con SSE, Markdown
sanitizzato, citazioni autorizzate e accessibilità. Nessun HTML del modello
viene interpretato come markup.

## Build

```bash
npm install --prefix packages/chat-widget
npm run build --prefix packages/chat-widget
```

Il pacchetto dipende da `@universal-ai-kit/sdk` (workspace locale). Con un
bundler normale il bare import viene risolto; nella demo vanilla è presente un
import map.

## Uso

```html
<uai-chat
  id="support"
  title="Supporto"
  placeholder="Come posso aiutarti?"
></uai-chat>
```

```js
import '@universal-ai-kit/chat-widget';

const chat = document.querySelector('#support');
const response = await fetch('/api/widget-token', { method: 'POST' });
const { token, conversation_id } = await response.json();

chat.setConfig({
  baseUrl: 'https://gateway.example.com',
  token,                       // token widget breve, mai una key admin
  conversationId: conversation_id,
  theme: 'light',
  onCitation: (citation) => {
    // Aprire la fonte solo dopo un controllo lato backend.
    console.log(citation);
  },
});
```

La tokenizzazione avviene server-side tramite `POST /v1/widget/tokens`; vedi
[docs/widgets.md](../../docs/widgets.md). Il browser non deve mai ricevere
`UAI_API_KEY` o altre credenziali amministrative.

## API

- Attributi: `base-url`, `token`, `conversation-id`, `title`, `placeholder`,
  `theme` (`light`/`dark`).
- `setConfig(config)`: configurazione programmatica; accetta `backend`,
  `idempotencyKey`, `onEvent`, `onCitation`, `onError` e un oggetto `theme` con
  variabili CSS `--uai-*`.
- Eventi DOM: `uai:event`, `uai:citation`, `uai:error` (bubbling/composed).
- Metodi: `getConfig()`.

`title`, `token` e `conversation-id` possono essere attributi; per token
dinamici usare `setConfig` dopo il mint server-side.

## Comportamento

- `response.delta` accumula testo; gli eventi duplicati per `event_id` vengono
  ignorati.
- `response.completed` mostra le citazioni restituite dal gateway; i pulsanti
  citazione chiamano `onCitation` e emettono `uai:citation`, senza navigazione
  automatica.
- `agent.failed`, `agent.cancelled` ed EOF incompleto sono stati distinti.
- Annulla con il pulsante o `Escape`: viene invocato l'`AbortSignal` dello SDK,
  che richiede anche la cancellazione del run.
- Focus, `role="log"`, `role="status"`, `aria-live`, label del textarea,
  `aria-busy` e layout responsive sono inclusi.
- Il renderer Markdown costruisce nodi DOM e usa `textContent`; HTML nel testo
  del modello resta testo. Solo link `http:`, `https:` e `mailto:` diventano
  cliccabili, con `rel="noopener noreferrer"`.

## Test

```bash
cd packages/chat-widget
npm run check
```

I test coprono sanitizer, link pericolosi, SSE simulato, citazioni, cancellazione,
EOF incompleto, tastiera e ruoli ARIA. Le demo sono in
[examples/widget](../../examples/widget).

## Laravel e FastAPI

Entrambe le integrazioni riusano questo componente. Il backend ospitante
crea una conversazione e un token widget temporaneo dopo aver verificato utente
e origine; il browser riceve solo la configurazione limitata:

```js
import { connectChat } from '@universal-ai-kit/chat-widget';

const chat = document.querySelector('uai-chat');
chat.setConfig({ title: 'Supporto', theme: 'dark' });
await connectChat(chat, {
  sessionUrl: '/widget/session',
  // Per Laravel: sessionUrl: '/uai/widget/session' e l'header CSRF dell'app.
  headers: { 'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]')?.content ?? '' },
});
```

`connectChat(element, { sessionUrl, headers?, signal? })` invia un POST JSON
con credenziali same-origin e rifiuta URL di sessione esterni e redirect.
L'endpoint deve restituire `{ baseUrl, token, conversationId, expiresAt }`;
`token` deve essere un token `uai_widget_…`. Solo i campi di connessione validati
vengono applicati; titolo, tema e callback già configurati restano attivi.
Il metodo restituisce la sessione validata. Gli errori non espongono corpi
upstream né credenziali. Non memorizzare il risultato in localStorage o nei log.

Ogni bootstrap crea una nuova conversazione. Alla scadenza del token ricarica
il widget/la pagina; questa integrazione iniziale non ripristina cronologia
né rinnova automaticamente una conversazione. Gli endpoint devono essere
autenticati, limitati nelle richieste e protetti dalle regole CSRF dell'app.

Guide complete: [Laravel](../../docs/laravel.md), [FastAPI](../../docs/fastapi.md).
