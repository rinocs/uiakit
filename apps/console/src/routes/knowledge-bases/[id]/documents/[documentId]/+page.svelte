<script lang="ts">
  let { data } = $props();
</script>

<svelte:head>
  <title>{data.document.title || data.document.filename} · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>{data.document.title || data.document.filename}</h1>
    <p class="muted">
      {data.document.filename} · {data.document.mime_type} · {data.document.ingestion_state}
    </p>
  </div>
  <a class="button secondary" href={`/knowledge-bases/${data.knowledgeBaseID}`}>
    Torna alla knowledge base
  </a>
</header>

{#if data.chunks.length === 0}
  <p class="empty">Nessun chunk disponibile per questo documento.</p>
{:else}
  <p class="muted">
    {data.chunks.length} chunk esportati. La vista è filtrata sul documento e sulla
    knowledge base autorizzata.
  </p>
  <ol class="chunk-list">
    {#each data.chunks as chunk (chunk.chunk_id)}
      <li id={`chunk-${chunk.chunk_id}`} class:selected={data.selectedChunk === chunk.chunk_id}>
        <div class="chunk-meta">
          <code>{chunk.chunk_id.slice(0, 12)}…</code>
          <span>pagina {chunk.page} · offset {chunk.start}–{chunk.end}</span>
          {#if data.selectedChunk === chunk.chunk_id}
            <span class="badge">citazione</span>
          {/if}
        </div>
        <pre class="chunk-text">{chunk.text}</pre>
      </li>
    {/each}
  </ol>
{/if}
