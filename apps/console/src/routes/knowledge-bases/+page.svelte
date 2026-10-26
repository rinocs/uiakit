<script lang="ts">
  let { data, form } = $props();
</script>

<svelte:head>
  <title>Knowledge base · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Knowledge base</h1>
  </div>
</header>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{/if}

<section class="split">
  <div>
    <h2>Elenco</h2>
    {#if data.knowledgeBases.length === 0}
      <p class="empty">Nessuna knowledge base autorizzata.</p>
    {:else}
      <ul class="list">
        {#each data.knowledgeBases as kb}
          <li>
            <a href={`/knowledge-bases/${kb.id}`}>
              <strong>{kb.name}</strong>
              <span class="muted">revisione {kb.revision} · versione {kb.active_version}</span>
            </a>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  {#if data.principal.role !== 'reader'}
    <div class="panel">
      <h2>Nuova knowledge base</h2>
      <form method="POST" action="?/create">
        <label for="name">Nome</label>
        <input id="name" name="name" maxlength="200" required value={form?.values?.name ?? ''} />

        <label for="description">Descrizione</label>
        <textarea id="description" name="description" rows="3" maxlength="4000">{form?.values?.description ?? ''}</textarea>

        <fieldset>
          <legend>Chunking</legend>
          <label for="chunk_size">Dimensione chunk</label>
          <input id="chunk_size" name="chunk_size" type="number" min="100" max="8000" value={form?.values?.chunk_size ?? '1000'} required />
          <label for="chunk_overlap">Overlap</label>
          <input id="chunk_overlap" name="chunk_overlap" type="number" min="0" max="7999" value={form?.values?.chunk_overlap ?? '200'} required />
          <p class="hint">L'overlap deve essere inferiore alla dimensione del chunk.</p>
        </fieldset>

        <button type="submit">Crea knowledge base</button>
        {#if form?.error}
          <p class="error" role="alert">{form.error}</p>
        {/if}
      </form>
    </div>
  {:else}
    <div class="panel">
      <h2>Sola lettura</h2>
      <p class="muted">Il ruolo reader non può creare knowledge base.</p>
    </div>
  {/if}
</section>
