<script lang="ts">
  let { data } = $props();
</script>

<svelte:head>
  <title>Run · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Run</h1>
    {#if data.conversation}
      <p class="muted small">Filtrati per conversazione <code>{data.conversation}</code></p>
    {/if}
  </div>
  {#if data.conversation}
    <a class="button secondary" href={`/conversations/${data.conversation}`}>Cronologia</a>
  {/if}
</header>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else if data.runs.length === 0}
  <p class="empty">Nessun run visibile.</p>
{:else}
  <table>
    <thead>
      <tr><th>Stato</th><th>Modello</th><th>Conversazione</th><th>Creato</th></tr>
    </thead>
    <tbody>
      {#each data.runs as run (run.id)}
        <tr>
          <td>
            <a href={`/runs/${run.id}`}>
              <span class:ok={run.status === 'completed'} class:bad={['failed', 'cancelled'].includes(run.status)} class="badge">
                {run.status}
              </span>
            </a>
          </td>
          <td>{run.model}</td>
          <td><a href={`/conversations/${run.conversation_id}`}><code>{run.conversation_id.slice(0, 8)}…</code></a></td>
          <td>{new Date(run.created_at).toLocaleString('it-IT')}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
