<script lang="ts">
  let { data } = $props();
</script>

<svelte:head>
  <title>Audit · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Audit</h1>
    <p class="muted">Chi ha fatto cosa, su quale risorsa e con quale esito.</p>
  </div>
</header>

{#if !data.forbidden}
<form method="GET" class="form-grid" aria-label="Filtri audit">
  <div>
    <label for="action">Azione</label>
    <input id="action" name="action" value={data.filters.action} maxlength="200" placeholder="es. tool.approved" />
  </div>
  <div>
    <label for="run_id">Run ID</label>
    <input id="run_id" name="run_id" value={data.filters.runId} maxlength="200" />
  </div>
  <div>
    <label for="target_id">Target ID</label>
    <input id="target_id" name="target_id" value={data.filters.targetId} maxlength="200" />
  </div>
  <div>
    <label for="limit">Limite · 1–200</label>
    <input id="limit" name="limit" type="number" min="1" max="200" value={data.filters.limit} />
  </div>
  <div class="form-footer">
    <button type="submit">Filtra</button>
    <a class="button secondary" href="/audit">Azzera</a>
  </div>
</form>
{/if}

{#if data.forbidden}
  <p class="notice">
    La consultazione dell’audit è riservata agli amministratori con scope <code>audit:read</code>.
  </p>
{:else if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else if data.events.length === 0}
  <p class="empty">Nessun evento per i filtri selezionati.</p>
{:else}
<section class="audit-events" aria-labelledby="events-heading">
  <div class="section-head">
    <h2 id="events-heading">Eventi</h2>
    <span class="muted small">{data.events.length} eventi · limite {data.filters.limit}</span>
  </div>
  <ul class="audit-list">
    {#each data.events as event (event.id)}
      <li>
        <div>
          <strong>{event.action}</strong> · {event.outcome}
          {#if event.run_id}
            · <a class="inline-link" href={`/runs/${event.run_id}`}>run</a>
          {/if}
        </div>
        <div class="muted small">
          {new Date(event.created_at).toLocaleString('it-IT')} ·
          {event.actor_principal_id}
          {#if event.target_type}· {event.target_type}{/if}
          {#if event.target_id}· <code>{event.target_id}</code>{/if}
        </div>
        {#if event.digest}
          <div class="muted small">Digest <code>{event.digest.slice(0, 16)}…</code></div>
        {/if}
        <details>
          <summary>Dettagli</summary>
          <pre class="json">{JSON.stringify(event.details ?? {}, null, 2)}</pre>
        </details>
      </li>
    {/each}
  </ul>
</section>
{/if}

<style>
  .audit-events {
    margin-top: 2rem;
  }

  .inline-link {
    text-decoration: underline;
  }
</style>
