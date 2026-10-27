<script lang="ts">
  import type { Credential } from '@universal-ai-kit/sdk';

  let { data, form } = $props();

  const roleLabels: Record<string, string> = {
    admin: 'Admin',
    operator: 'Operator',
    reader: 'Reader',
  };

  function stateOf(credential: Credential) {
    if (credential.revoked_at) return { label: 'Revocata', healthy: false };
    if (Date.parse(credential.expires_at) <= Date.now()) return { label: 'Scaduta', healthy: false };
    return { label: 'Attiva', healthy: true };
  }
</script>

<svelte:head>
  <title>Credenziali · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Credenziali</h1>
    <p class="muted">API key per persone e servizi. Ruolo e scope definiscono cosa può fare ogni chiave.</p>
  </div>
</header>

{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}

{#if form?.secret}
  <section class="notice" aria-labelledby="secret-heading">
    <h2 id="secret-heading">Nuova API key</h2>
    <p class="muted">Copiala ora: non verrà mostrata di nuovo. Se la perdi, ruota la credenziale.</p>
    <pre class="json" data-testid="credential-secret">{form.secret}</pre>
    <a class="button secondary" href="/credentials">Ho copiato la chiave</a>
  </section>
{/if}

{#if data.forbidden}
  <p class="notice">
    La gestione delle credenziali è riservata agli amministratori con scope
    <code>credentials:read</code> e <code>credentials:write</code>.
  </p>
{:else if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else}
  <section aria-labelledby="credential-list">
    <div class="section-head">
      <h2 id="credential-list">Elenco credenziali</h2>
      <span class="muted small">Totale: {data.credentials.length}</span>
    </div>
    {#if data.credentials.length === 0}
      <p class="empty">Nessuna credenziale registrata.</p>
    {:else}
      <table>
        <caption class="visually-hidden">Credenziali API registrate</caption>
        <thead>
          <tr>
            <th scope="col">Principal</th>
            <th scope="col">Ruolo</th>
            <th scope="col">Scope</th>
            <th scope="col">Scadenza</th>
            <th scope="col">Stato</th>
            <th scope="col">Azioni</th>
          </tr>
        </thead>
        <tbody>
          {#each data.credentials as credential (credential.id)}
            {@const state = stateOf(credential)}
            <tr>
              <td>
                <strong>{credential.principal_id || '—'}</strong>
                <div class="muted small" title={credential.id}><code>{credential.id.slice(0, 8)}…</code></div>
              </td>
              <td>{roleLabels[credential.role] ?? credential.role}</td>
              <td>
                {#each credential.scopes as scope, index}
                  <code>{scope}</code>{#if index < credential.scopes.length - 1}, {/if}
                {/each}
              </td>
              <td>{new Date(credential.expires_at).toLocaleString('it-IT')}</td>
              <td>
                <span class="badge" class:ok={state.healthy} class:bad={!state.healthy}>{state.label}</span>
              </td>
              <td>
                {#if credential.revoked_at}
                  <span class="muted small">—</span>
                {:else}
                  <details>
                    <summary>Ruota</summary>
                    <p class="muted small">Genera una nuova chiave e invalida subito quella attuale.</p>
                    <form method="POST" action="?/rotate">
                      <input type="hidden" name="id" value={credential.id} />
                      <label for={`rotate-expiry-${credential.id}`}>Nuova scadenza · opzionale</label>
                      <input
                        id={`rotate-expiry-${credential.id}`}
                        name="expires_at"
                        type="datetime-local"
                      />
                      <button class="secondary" type="submit">Ruota chiave</button>
                    </form>
                  </details>
                  <details class="danger-panel">
                    <summary>Revoca</summary>
                    <p class="muted small">La chiave smette di funzionare subito. L’operazione non è reversibile.</p>
                    <form method="POST" action="?/revoke">
                      <input type="hidden" name="id" value={credential.id} />
                      <button class="danger" type="submit">Conferma revoca</button>
                    </form>
                  </details>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  {#if data.canWrite}
    <section class="credential-create" aria-labelledby="credential-create">
    <div class="section-head">
      <h2 id="credential-create">Nuova credenziale</h2>
    </div>
    <form method="POST" action="?/create" class="form-grid">
      <div>
        <label for="principal_id">Principal ID</label>
        <input id="principal_id" name="principal_id" maxlength="200" autocomplete="off" aria-describedby="principal-hint" />
        <p class="hint" id="principal-hint">Opzionale: identifica la persona o il servizio.</p>
      </div>
      <div>
        <label for="role">Ruolo</label>
        <select id="role" name="role" required>
          <option value="reader">Reader</option>
          <option value="operator">Operator</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      <div>
        <label for="scopes">Scope</label>
        <input id="scopes" name="scopes" required placeholder="assistants:read, agent-runs:read" aria-describedby="scopes-hint" />
        <p class="hint" id="scopes-hint">Separati da virgola. Devono essere previsti dal ruolo scelto.</p>
      </div>
      <div>
        <label for="expires_at">Scadenza</label>
        <input id="expires_at" name="expires_at" type="datetime-local" aria-describedby="expiry-hint" />
        <p class="hint" id="expiry-hint">Opzionale: futura, entro 365 giorni. Predefinita 30 giorni.</p>
      </div>
      <div class="form-footer">
        <button type="submit">Crea credenziale</button>
      </div>
    </form>
    </section>
  {:else}
    <p class="notice">
      La tua chiave può leggere le credenziali ma non modificarle: manca lo scope
      <code>credentials:write</code>.
    </p>
  {/if}
{/if}

<style>
  .credential-create {
    margin-top: 2rem;
  }
</style>
