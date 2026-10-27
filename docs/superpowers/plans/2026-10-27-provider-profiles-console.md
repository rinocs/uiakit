# Provider Profiles (console) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an administrator create and edit provider profiles from the console,
including write-only credentials, and let an assistant pick a namespaced
`profile/model` from a grouped select.

**Architecture:** The console stays a thin SvelteKit layer over the gateway API:
loads and form actions call the SDK, the gateway enforces RBAC and persistence.
No credential value is ever rendered back; the pages use the
`secret_source`/`secret_configured`/`secret_readable` flags.

**Tech Stack:** SvelteKit 2 + TypeScript, Vitest, Playwright, the
`@universal-ai-kit/sdk` client.

**Spec:** [2026-10-27-provider-credentials-design.md](../specs/2026-10-27-provider-credentials-design.md)
**Depends on:** [2026-10-27-provider-profiles-backend.md](2026-10-27-provider-profiles-backend.md)
being merged; it defines every endpoint and the SDK resource used here.

## Project-wide requirements

- Copy is Italian and matches the existing pages (`Provider`, `Credenziali`,
  `Salva`, `Rimuovi`); every form control keeps an accessible label, and status
  messages use `role="alert"` / `role="status"` like the current provider page.
- Authorization is unchanged: admin with `providers:read` to see,
  `providers:write` to change; forbidden states reuse the current wording.
- The credential input is `type="password"`, always empty on render, and never
  appears in any response, toast or `data-testid` payload.
- `If-Match` always carries the revision loaded with the page; a 412 surfaces the
  "configurazione cambiata" message and asks for a reload.
- One commit per task, message `feat(console): <task title>`.

## Review Focus

- A stored credential must survive a page reload with the field empty and the
  badge showing "configurato": the input never repopulates (Task 3).
- Saving profile fields must not clear the credential, and saving a credential
  must not change the profile revision the form is holding, or the next save
  fails with 412 (Tasks 2 and 3).
- A profile that is still used by an assistant must fail deletion with
  `profile_in_use` and say which action to take, not show a raw error (Task 1).
- A gateway without `UAI_SECRET_KEY` must show a clear notice and keep the
  environment-reference form usable (Task 3).
- A legacy assistant whose stored model has no profile prefix must preselect the
  `default/` entry, not an empty option (Task 4).

---

### Task 1: Providers list and create

**Files:**
- Create: `apps/console/src/lib/server/provider-access.ts`
- Create: `apps/console/src/routes/providers/+page.server.ts`
- Create: `apps/console/src/routes/providers/+page.svelte`
- Modify: `apps/console/src/routes/provider/+page.server.ts` (import the shared helpers)
- Modify: `apps/console/tests/browser/mock-gateway.mjs`
- Test: `apps/console/tests/browser/providers.spec.ts`

**Interfaces:**
- Consumes: `client.providers.list()`, `client.providers.create(body)`,
  `client.providers.remove(id)` from the backend plan's SDK.
- Produces: `canManage(locals: App.Locals): boolean`, `denied()`, and
  `PROVIDER_MESSAGES` moved to `provider-access.ts` together with
  `providerMessage(error): string`, imported by the provider, providers and
  profile pages.
- Produces: `/providers` page with `load` returning
  `{ profiles, canManage, forbidden, error }` and actions `create` and `remove`.

- [ ] **Step 1: Add the mock gateway routes and write the failing specs**

In `mock-gateway.mjs`, add a `profiles` array (id, name, provider, base_url,
secret_source, secret_configured, secret_readable, max_output_tokens, revision,
applied, managed, models) starting with one `openai` profile, plus handlers for
`GET /v1/providers`, `POST /v1/providers`, `GET|PUT|DELETE /v1/providers/{id}`,
`PUT|DELETE /v1/providers/{id}/secret`, mirroring the existing `/v1/provider`
handlers (scope checks, `If-Match`, 409 `profile_in_use`).

`apps/console/tests/browser/providers.spec.ts`:

```ts
test('admin creates and removes a provider profile', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/providers');
  await expect(page.getByRole('heading', { name: 'Provider', exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'openai', exact: true })).toBeVisible();

  await page.getByLabel('Identificativo').fill('local');
  await page.getByLabel('Nome').fill('Ollama locale');
  await page.getByLabel('Tipo provider').selectOption('ollama');
  await page.getByLabel('Base URL').fill('http://ollama:11434');
  await page.getByLabel('Max output tokens · 1–8192').fill('512');
  await page.getByLabel('Identificativo modello').fill('llama3.2:3b');
  await page.getByRole('button', { name: 'Aggiungi modello' }).click();
  await page.getByRole('button', { name: 'Crea provider' }).click();
  await expect(page.getByRole('cell', { name: 'local', exact: true })).toBeVisible();
});

test('readers cannot manage provider profiles', async ({ page }) => {
  await login(page, 'reader-key');
  await page.goto('/providers');
  await expect(page.getByText(/riservata agli amministratori con gli scope/)).toBeVisible();
});
```

- [ ] **Step 2: Run the specs to verify they fail**

```bash
cd apps/console && npx playwright test providers.spec.ts
```

Expected: navigation to `/providers` returns 404.

- [ ] **Step 3: Implement the shared helpers and the list page**

`provider-access.ts` holds `canManage`, `denied`, `PROVIDER_MESSAGES` (extended
with `profile_in_use`, `not_found`, `invalid_profile_id`, `too_many_profiles`,
`secret_key_unavailable`, `secret_unreadable`, `secret_value_invalid`,
`invalid_configuration`) and `providerMessage(error)`. The provider page imports
them instead of defining them.

`/providers/+page.server.ts` load mirrors the provider page's guard
(`forbidden` when the scope is missing, error message otherwise) and returns
`profiles` from `client.providers.list()`. Actions: `create` validates id
`^[a-z0-9][a-z0-9-]{0,31}$`, non-empty name and base URL, integer
`max_output_tokens` in 1–8192, at least one model, then calls
`client.providers.create`; `remove` calls `client.providers.remove(id)` and maps
`profile_in_use` to
"Questo provider è usato da almeno un assistente: aggiorna quegli assistenti prima di eliminarlo."

The Svelte page renders a table (id, nome, tipo, base URL, credenziale, stato,
modelli, azioni) with a "Crea provider" form below it, a link per row to
`/providers/{id}`, and a danger panel for deletion. Because the API requires at
least one model, the create form keeps a client-side model list ("Aggiungi
modello" appends to it, "Rimuovi" removes from it) and submits it with the rest.

- [ ] **Step 4: Run the specs to verify they pass**

```bash
cd apps/console && npx playwright test providers.spec.ts && npm run check
```

Expected: both specs pass, no svelte-check errors.

- [ ] **Step 5: Commit**

```bash
git add apps/console/src/lib/server/provider-access.ts \
  apps/console/src/routes/providers apps/console/src/routes/provider/+page.server.ts \
  apps/console/tests/browser/mock-gateway.mjs apps/console/tests/browser/providers.spec.ts
git commit -m "feat(console): list and create provider profiles"
```

---

### Task 2: Profile detail — fields, models and discovery

**Files:**
- Create: `apps/console/src/routes/providers/[id]/+page.server.ts`
- Create: `apps/console/src/routes/providers/[id]/+page.svelte`
- Test: `apps/console/tests/browser/providers.spec.ts`

**Interfaces:**
- Consumes: `client.providers.get(id)`, `client.providers.update(id, body, { ifMatch })`,
  `client.providers.discoverModels(id)`, and the shared helpers from Task 1.
- Produces: `load` returning `{ profile, canManage, forbidden, error, saved }` and
  actions `save`, `addModel`, `removeModel`, `discover`.

- [ ] **Step 1: Write the failing specs**

Append to `providers.spec.ts`:

```ts
test('admin edits fields and manages the profile catalog', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/providers/openai');
  await expect(page.getByRole('heading', { name: 'openai', level: 1 })).toBeVisible();

  await page.getByLabel('Nome').fill('OpenAI EU');
  await page.getByLabel('Base URL').fill('https://eu.example.com/v1');
  await page.getByRole('button', { name: 'Salva provider' }).click();
  await expect(page.getByRole('status')).toContainText('Configurazione provider salvata.');

  await page.getByRole('button', { name: 'Scopri modelli dal provider' }).click();
  const discovery = page.getByText('Modelli esposti dal provider').locator('..');
  await expect(discovery).toContainText('extra-model');

  await page.getByLabel('Identificativo modello').fill('eu-model');
  await page.getByRole('button', { name: 'Aggiungi modello' }).click();
  await expect(page.getByRole('cell', { name: 'eu-model', exact: true })).toBeVisible();

  const row = page.getByRole('row', { name: /eu-model/ });
  await row.getByRole('button', { name: 'Rimuovi' }).click();
  await expect(page.getByRole('cell', { name: 'eu-model', exact: true })).toHaveCount(0);
});

test('a stale revision asks for a reload', async ({ context, page }) => {
  await login(page, 'admin-key');
  await page.goto('/providers/openai');
  const second = await context.newPage();
  await login(second, 'admin-key');
  await second.goto('/providers/openai');

  await page.getByLabel('Nome').fill('First save');
  await page.getByRole('button', { name: 'Salva provider' }).click();
  await expect(page.getByRole('status')).toContainText('Configurazione provider salvata.');

  await second.getByLabel('Nome').fill('Second save');
  await second.getByRole('button', { name: 'Salva provider' }).click();
  await expect(second.getByRole('alert')).toContainText('configurazione è cambiata');
});
```

- [ ] **Step 2: Run the specs to verify they fail**

```bash
cd apps/console && npx playwright test providers.spec.ts -g 'edits fields'
```

Expected: `/providers/openai` returns 404.

- [ ] **Step 3: Implement the detail page**

`load` calls `client.providers.get(id)`; a 404 returns a SvelteKit `error(404)`.
The `save` action validates name, base URL, `max_output_tokens` and sends
`{ name, provider, base_url, max_output_tokens, models }` with the hidden
revision as `ifMatch`. `addModel`/`removeModel` reuse the current provider page
logic (reject duplicates, keep at least one model, map `model_in_use` to
"Rimuovi prima gli assistenti che usano questo modello."). `discover` calls
`client.providers.discoverModels(id)` and returns the list as `discovered`. All
successful actions redirect to `/providers/{id}?saved=1`, which the load maps to
`saved: true`.

The Svelte page reuses the existing provider page markup for the fields and the
model table, keeps the accessible labels identical, adds a back link to
`/providers`, and shows the `applied` badge with the same copy
("applicato" / "in attesa").

- [ ] **Step 4: Run the specs to verify they pass**

```bash
cd apps/console && npx playwright test providers.spec.ts && npm run check
```

Expected: all provider specs pass, no svelte-check errors.

- [ ] **Step 5: Commit**

```bash
git add apps/console/src/routes/providers apps/console/tests/browser/providers.spec.ts
git commit -m "feat(console): edit provider profiles and their catalog"
```

---

### Task 3: Credential panel

**Files:**
- Modify: `apps/console/src/routes/providers/[id]/+page.server.ts`
- Modify: `apps/console/src/routes/providers/[id]/+page.svelte`
- Test: `apps/console/tests/browser/providers.spec.ts`

**Interfaces:**
- Consumes: `client.providers.setSecret(id, body)` and
  `client.providers.clearSecret(id)`.
- Produces: actions `saveSecret` and `clearSecret`, each redirecting with
  `?saved=secret`.

- [ ] **Step 1: Write the failing specs**

```ts
test('the credential is write-only and survives a reload', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/providers/openai');
  await expect(page.getByText('secret non configurato')).toBeVisible();

  await page.getByLabel('Chiave API').fill('sk-live-123');
  await page.getByRole('button', { name: 'Salva chiave' }).click();
  await expect(page.getByText('secret configurato')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Chiave API')).toHaveValue('');
  await expect(page.getByText('sk-live-123')).toHaveCount(0);

  await page.getByRole('button', { name: 'Rimuovi chiave' }).click();
  await expect(page.getByText('secret non configurato')).toBeVisible();
});

test('the environment reference form works', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/providers/openai');
  await page.getByLabel('Variabile d\'ambiente').fill('MODEL_API_KEY');
  await page.getByRole('button', { name: 'Usa variabile d\'ambiente' }).click();
  await expect(page.getByText('secret configurato')).toBeVisible();
  await expect(page.getByText('MODEL_API_KEY')).toBeVisible();
});
```

- [ ] **Step 2: Run the specs to verify they fail**

```bash
cd apps/console && npx playwright test providers.spec.ts -g 'credential|environment reference'
```

Expected: the credential controls do not exist.

- [ ] **Step 3: Implement the panel**

`saveSecret` reads `value` and `ref`; when `value` is non-empty it posts
`{ source: 'stored', value }`, otherwise `{ source: 'env', ref }`; it rejects
both/neither with 422 and the message
"Inserisci una chiave oppure una variabile d'ambiente.". `clearSecret` calls
`client.providers.clearSecret(id)`. Errors map through `providerMessage` so
`secret_key_unavailable` shows
"Imposta UAI_SECRET_KEY nel gateway per salvare le chiavi dalla console." and
`secret_unreadable` shows "La chiave non è leggibile: reinseriscila.".

The Svelte panel shows the badge (`secret configurato` / `secret non
configurato`), the current `secret_source` (`stored` / `env` with the reference
name / `none`), a password input labelled "Chiave API" that is never prefilled, a
text input labelled "Variabile d'ambiente", the three buttons ("Salva chiave",
"Usa variabile d'ambiente", "Rimuovi chiave"), and the `UAI_SECRET_KEY` notice
when `secret_source === 'none'` and a stored save fails.

- [ ] **Step 4: Run the specs to verify they pass**

```bash
cd apps/console && npx playwright test providers.spec.ts && npm run check
```

Expected: all provider specs pass.

- [ ] **Step 5: Commit**

```bash
git add apps/console/src/routes/providers apps/console/tests/browser/providers.spec.ts
git commit -m "feat(console): manage provider credentials write-only"
```

---

### Task 4: Assistant model select, navigation and redirect

**Files:**
- Modify: `apps/console/src/routes/assistants/+page.svelte`
- Modify: `apps/console/src/routes/assistants/+page.server.ts`
- Modify: `apps/console/src/routes/+layout.svelte`
- Delete: `apps/console/src/routes/provider/+page.svelte`
- Modify: `apps/console/src/routes/provider/+page.server.ts` (load redirects to `/providers`)
- Test: `apps/console/tests/browser/console.spec.ts`, `accessibility.spec.ts`

**Interfaces:**
- Consumes: `client.providers.list()` in the assistants load, replacing the
  current `client.models.list()` so there is a single catalog source.
- Produces: assistant options labelled `profile/model`, grouped by profile name;
  `/provider` answering a 308 redirect to `/providers`; navigation entry
  "Provider" pointing at `/providers`.

- [ ] **Step 1: Write the failing specs**

In `console.spec.ts`:

```ts
test('the assistant form offers namespaced models grouped by profile', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/assistants');
  const group = page.locator('optgroup[label="OpenAI"]');
  await expect(group.locator('option[value="openai/test-model"]')).toHaveCount(1);
});

test('the legacy provider page redirects to the profile list', async ({ page }) => {
  await login(page, 'admin-key');
  await page.goto('/provider');
  await expect(page).toHaveURL(/\/providers$/);
});
```

In `accessibility.spec.ts`, update the navigation assertion to expect
`/providers` for the "Provider" link.

- [ ] **Step 2: Run the specs to verify they fail**

```bash
cd apps/console && npx playwright test console.spec.ts accessibility.spec.ts
```

Expected: the option values are ungrouped and `/provider` still renders the old page.

- [ ] **Step 3: Implement the select, the redirect and the navigation**

The assistants `load` replaces `client.models.list()` with
`client.providers.list()` and returns `{ assistants, profiles }`. The page renders
`{#each profiles as profile}<optgroup label={profile.name}>` with one `<option
value="{profile.id}/{model.id}">` per model; when an assistant's stored model has
no `/`, the value is matched as `default/{model}` so the correct option is
selected.

`provider/+page.server.ts` becomes a load that throws
`redirect(308, '/providers')`; delete the Svelte page. In `+layout.svelte`, change
the "Provider" link to `/providers` and keep the icon.

- [ ] **Step 4: Run the suite to verify it passes**

```bash
cd apps/console && npx playwright test && npm run check
```

Expected: all browser specs pass, no svelte-check errors.

- [ ] **Step 5: Commit**

```bash
git add apps/console/src/routes/assistants apps/console/src/routes/provider \
  apps/console/src/routes/+layout.svelte apps/console/tests/browser
git commit -m "feat(console): bind assistants to namespaced provider models"
```

---

### Task 5: Console documentation and full gate

**Files:**
- Modify: `apps/console/README.md`, `docs/guide.md`, `docs/assistants-models.md`
- Test: `apps/console/tests/browser/admin.spec.ts`, `console-settings.test.ts`

- [ ] **Step 1: Update the console README**

Document `/providers` (list/create), `/providers/{id}` (fields, credential panel,
catalog, discovery), the write-only credential rule, the `UAI_SECRET_KEY`
requirement for stored credentials, the `/provider` redirect, and the grouped
`profile/model` assistant select. Keep the existing structure and language of the
README and add no new sections beyond those.

- [ ] **Step 2: Run the whole console suite**

```bash
cd apps/console && npm test && npm run check && npx playwright test
```

Expected: Vitest and Playwright suites pass; the accessibility spec covers the
new pages.

- [ ] **Step 3: Run the repository gate**

```bash
make test-console && make test-console-browser && make test
```

Expected: the console targets and the full gate pass.

- [ ] **Step 4: Commit**

```bash
git add apps/console/README.md docs/guide.md docs/assistants-models.md
git commit -m "docs(console): describe provider profiles and stored credentials"
```
