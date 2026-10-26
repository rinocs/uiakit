<script lang="ts">
  let { data } = $props();
</script>

<svelte:head><title>Dashboard · Universal AI Kit</title></svelte:head>
<header class="page-head">
  <div><h1>Dashboard</h1><p class="muted">Configura i tuoi assistenti. Segui ogni esecuzione.</p></div>
  <a class="button" href="/playground">Apri playground <span aria-hidden="true">→</span></a>
</header>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else}
  <section class="workspace-overview" aria-labelledby="workspace-heading">
    <div class="section-head"><h2 id="workspace-heading">Il tuo workspace</h2><a href="/settings">Impostazioni</a></div>
    <div class="overview-row"><div><h3>Assistenti</h3><p class="muted">Prompt, risorse e limiti di esecuzione.</p></div><span class="overview-count">{data.assistants.length}</span><a class="button secondary" href="/assistants">Gestisci assistenti</a></div>
    <div class="overview-row"><div><h3>Modelli disponibili</h3><p class="muted">Capacità e finestre di contesto dichiarate dal runtime.</p></div><span class="overview-count">{data.models.length}</span><a class="button secondary" href="/models">Esplora modelli</a></div>
  </section>
  <section class="workspace-sections" aria-label="Attività del workspace">
    <div><h2>Configura</h2><p class="muted">Collega le fonti e definisci cosa possono fare gli assistenti.</p><a href="/knowledge-bases">Gestisci knowledge base</a><a href="/tools">Consulta i tool</a><a href="/plugins">Configura plugin</a></div>
    <div><h2>Verifica</h2><p class="muted">Prova una conversazione, controlla gli esiti e autorizza le operazioni.</p><a href="/playground">Prova nel playground</a><a href="/runs">Consulta i run</a><a href="/approvals">Gestisci approvazioni</a></div>
  </section>
{/if}
