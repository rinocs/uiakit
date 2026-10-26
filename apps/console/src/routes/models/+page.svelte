<script lang="ts">
  let { data } = $props();
</script>

<svelte:head>
  <title>Modelli · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Modelli</h1>
  </div>
</header>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else}
  <table>
    <thead>
      <tr><th>Modello</th><th>Provider</th><th>Capacità</th><th>Contesto</th><th>Output</th></tr>
    </thead>
    <tbody>
      {#each data.models as model}
        <tr>
          <td><code>{model.id}</code></td>
          <td>{model.provider}</td>
          <td>{model.capabilities.join(', ')}</td>
          <td>{model.context_window}</td>
          <td>{model.max_output_tokens}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
