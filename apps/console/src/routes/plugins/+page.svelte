<script lang="ts">
  let { data, form } = $props();
  let canWrite = $derived(
    data.principal.role === 'admin' || data.principal.scopes.includes('plugins:write'),
  );
</script>

<svelte:head>
  <title>Plugin · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <p class="eyebrow">Estensioni</p>
    <h1>Plugin</h1>
  </div>
</header>

<p class="notice">
  La console configura solo plugin già installati dal deployment. Non carica
  archivî, non installa codice e non accetta manifest arbitrari.
</p>

{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}
{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else if !data.catalog || data.catalog.plugins.length === 0}
  <p class="empty">Nessun plugin installato.</p>
{:else}
  <p class="muted small">
    Revisione catalogo {data.catalog.revision} ·
    {data.catalog.applied ? 'applicato' : 'in attesa di applicazione'}
  </p>
  <div class="cards">
    {#each data.catalog.plugins as plugin (plugin.manifest.id)}
      {@const health = data.health[plugin.manifest.id]}
      <article class="card">
        <div class="tool-head">
          <div>
            <strong>{plugin.manifest.name}</strong>
            <div class="muted small">
              <code>{plugin.manifest.id}</code> · v{plugin.manifest.version}
            </div>
          </div>
          <span class:ok={plugin.state === 'active'} class:bad={plugin.state === 'failed'} class="badge">
            {plugin.state}
          </span>
        </div>
        <p class="muted small">
          Salute: <span class:ok={health?.status === 'ok'} class:bad={health?.status === 'unavailable'}>
            {health?.status ?? 'unknown'}
          </span>
          · desiderato: {data.catalog.desired[plugin.manifest.id] ?? false}
        </p>

        {#if canWrite}
          <form method="POST" action="?/configure">
            <input type="hidden" name="plugin_id" value={plugin.manifest.id} />
            <input type="hidden" name="ifMatch" value={JSON.stringify(String(data.catalog.revision))} />
            <label class="check">
              <input
                type="checkbox"
                name="enabled"
                checked={data.catalog.desired[plugin.manifest.id] ?? plugin.state === 'active'}
              />
              Abilitato
            </label>
            <label for={`config-${plugin.manifest.id}`}>Configurazione JSON</label>
            <textarea id={`config-${plugin.manifest.id}`} name="config" rows="4">{JSON.stringify(plugin.manifest.config ?? {}, null, 2)}</textarea>
            <div class="row-actions">
              <button type="submit">Applica</button>
            </div>
          </form>
          <details>
            <summary>Rimuovi configurazione</summary>
            <form method="POST" action="?/remove">
              <input type="hidden" name="plugin_id" value={plugin.manifest.id} />
              <input type="hidden" name="ifMatch" value={JSON.stringify(String(data.catalog.revision))} />
              <button class="link danger" type="submit">Rimuovi configurazione</button>
            </form>
          </details>
        {:else}
          <p class="hint">Ruolo in sola lettura.</p>
        {/if}
      </article>
    {/each}
  </div>
{/if}
