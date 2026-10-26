# Universal AI Kit console

Console SvelteKit minima per assistenti, versioni, modelli e direttive. La API
key viene validata con `GET /v1/me`, resta in memoria server-side e non viene mai
inclusa nel bundle o nelle risposte al browser.

## Sviluppo

```bash
cd apps/console
npm install
npm run dev
```

Variabili server-side:

```dotenv
UAI_GATEWAY_URL=http://localhost:8080
ORIGIN=http://localhost:5173
BODY_SIZE_LIMIT=24M
```

## Build e test

```bash
npm run check          # svelte-check + vitest + build
npm run test:browser   # Playwright; richiede Chromium e dipendenze di sistema
```

## Sicurezza

- Cookie di sessione opaco, HttpOnly, SameSite=Lax, Secure su HTTPS.
- Sessione in memoria con TTL 8h; logout esplicito. Per più istanze servono
  sessioni distribuite (M6).
- Ruoli e scope vengono letti dal gateway; i controlli UI non sostituiscono
  l'autorizzazione API. Reader è in sola lettura.
- Le API key non vengono mai restituite al client; il browser riceve solo
  l'identità e gli scope effettivi.
