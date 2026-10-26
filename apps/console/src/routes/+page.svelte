<script lang="ts">
  let { data } = $props();
</script>

<svelte:head>
  <title>Dashboard · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <p class="eyebrow">Panoramica</p>
    <h1>Dashboard</h1>
  </div>
  <a class="button" href="/assistants">Gestisci assistenti</a>
</header>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else}
  <div class="cards">
    <article class="card">
      <span class="metric">{data.assistants.length}</span>
      <h2>Assistenti</h2>
      <p class="muted">Versioni, prompt, modelli e direttive.</p>
      <a href="/assistants">Apri</a>
    </article>
    <article class="card">
      <span class="metric">{data.models.length}</span>
      <h2>Modelli</h2>
      <p class="muted">Catalogo pubblico importato dal runtime.</p>
      <a href="/models">Apri</a>
    </article>
  </div>
{/if}
