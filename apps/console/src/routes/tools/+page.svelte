<script lang="ts">
  let { data } = $props();
</script>

<svelte:head>
  <title>Tool · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <p class="eyebrow">Estensioni</p>
    <h1>Tool</h1>
  </div>
</header>

<p class="notice">
  Il catalogo è read-only. Connector, URL, header e credenziali sono definiti
  dal deployment; la console non installa codice né accetta URL arbitrari.
</p>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else if data.tools.length === 0}
  <p class="empty">Nessun tool registrato.</p>
{:else}
  <div class="cards">
    {#each data.tools as tool (tool.id)}
      <article class="card">
        <div class="tool-head">
          <div>
            <strong>{tool.name}</strong>
            <div class="muted small"><code>{tool.id}</code> · v{tool.version}</div>
          </div>
          <span class:bad={tool.risk_level !== 'read_only'} class="badge">{tool.risk_level}</span>
        </div>
        <p>{tool.description}</p>
        <div class="muted small">
          Executor: {tool.executor ?? 'builtin'} · Connettori:
          {#each tool.permissions.filter((permission) => permission.startsWith('connector:')) as connector}
            <code>{connector.slice('connector:'.length)}</code>
          {:else}
            nessuno
          {/each}
        </div>
        <details>
          <summary>Schema input</summary>
          <pre class="json">{JSON.stringify(tool.input_schema, null, 2)}</pre>
        </details>
      </article>
    {/each}
  </div>
{/if}
