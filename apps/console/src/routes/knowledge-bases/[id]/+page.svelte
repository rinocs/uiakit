<script lang="ts">
  import { onMount } from 'svelte';
  import { invalidateAll } from '$app/navigation';

  let { data, form } = $props();
  let latestVersion = $derived(data.versions[0]);
  let isReader = $derived(data.principal.role === 'reader');

  onMount(() => {
    const active = () =>
      data.documents.some(
        ({ document }) =>
          !['completed', 'failed', 'cancelled'].includes(document.ingestion_state),
      );
    if (!active()) return;
    const timer = setInterval(() => {
      if (active()) void invalidateAll();
    }, 2500);
    return () => clearInterval(timer);
  });

  function formatBytes(value: number): string {
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
  }

  function formatDate(value: string): string {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('it-IT');
  }
</script>

<svelte:head>
  <title>{data.knowledgeBase.name} · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>{data.knowledgeBase.name}</h1>
    <p class="page-context">Knowledge base · revisione {data.knowledgeBase.revision}</p>
    <p class="muted">
      {data.knowledgeBase.description || 'Nessuna descrizione.'} · versione attiva
      {data.knowledgeBase.active_version}
    </p>
  </div>
  <div class="head-actions">
    <a class="button secondary" href={`/knowledge-bases/${data.knowledgeBase.id}/export`}>
      Esporta JSON
    </a>
    <a class="button secondary" href="/knowledge-bases">Torna all'elenco</a>
  </div>
</header>

{#if data.uploaded}
  <p class="notice" role="status">Documento caricato. Lo stato di ingestion si aggiorna automaticamente.</p>
{/if}
{#if data.reindexed}
  <p class="notice" role="status">Nuova versione di reindicizzazione creata.</p>
{/if}
{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}
{#if form?.uploadError}
  <p class="error" role="alert">{form.uploadError}</p>
{/if}
{#if form?.associationError}
  <p class="error" role="alert">{form.associationError}</p>
{/if}

{#if isReader}
  <p class="notice">Ruolo reader: knowledge base in sola lettura.</p>
{/if}

<section class="split">
  <div class="panel">
    <h2>Documenti</h2>
    <div class="section-head">
      <span class="muted">Limite 20 MiB · TXT, Markdown, HTML, PDF, DOCX</span>
      <a href={`/knowledge-bases/${data.knowledgeBase.id}`}>Aggiorna stato</a>
    </div>

    {#if data.documents.length === 0}
      <p class="empty">Nessun documento caricato.</p>
    {:else}
      <ul class="document-list">
        {#each data.documents as entry (entry.document.id)}
          {@const document = entry.document}
          {@const job = entry.job}
          <li>
            <div class="document-head">
              <a href={`/knowledge-bases/${data.knowledgeBase.id}/documents/${document.id}`}>
                <strong>{document.title || document.filename}</strong>
              </a>
              <span class:ok={document.ingestion_state === 'completed'} class:bad={document.ingestion_state === 'failed'}>
                {document.ingestion_state}
              </span>
            </div>
            <div class="muted small">
              {document.filename} · {formatBytes(document.size_bytes)} · {formatDate(document.created_at)}
            </div>
            {#if job}
              <div class="muted small">
                Job: {job.state} · tentativi {job.attempts}
                {#if job.error_code}· <span class="error">{job.error_code}</span>{/if}
              </div>
            {/if}
            <div class="row-actions">
              <a href={`/knowledge-bases/${data.knowledgeBase.id}/documents/${document.id}`}>Apri fonte</a>
              {#if !isReader && job && ['queued', 'running'].includes(job.state)}
                <form method="POST" action="?/cancelJob">
                  <input type="hidden" name="document_id" value={document.id} />
                  <button class="link" type="submit">Annulla job</button>
                </form>
              {/if}
              {#if !isReader}
                <details>
                  <summary>Elimina</summary>
                  <form method="POST" action="?/deleteDocument">
                    <input type="hidden" name="document_id" value={document.id} />
                    <input type="hidden" name="confirm" value="yes" />
                    <button class="link danger" type="submit">Conferma eliminazione</button>
                  </form>
                </details>
              {/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}

    {#if !isReader}
      <h3>Carica documento</h3>
      <form method="POST" action="?/upload" enctype="multipart/form-data">
        <label for="file">File</label>
        <input id="file" name="file" type="file" accept=".txt,.md,.markdown,.html,.htm,.pdf,.docx" required />
        <label for="title">Titolo (opzionale)</label>
        <input id="title" name="title" maxlength="200" />
        <button type="submit">Carica e accoda</button>
        <p class="hint">Il titolo vuoto usa il nome del file. L'upload non viene ripetuto al refresh.</p>
      </form>
    {/if}
  </div>

  <div>
    <div class="panel">
      <h2>Configurazione</h2>
      <form method="POST" action="?/update">
        <input type="hidden" name="ifMatch" value={JSON.stringify(String(data.knowledgeBase.revision))} />
        <label for="name">Nome</label>
        <input id="name" name="name" maxlength="200" required value={data.knowledgeBase.name} disabled={isReader} />
        <label for="description">Descrizione</label>
        <textarea id="description" name="description" rows="3" maxlength="4000" disabled={isReader}>{data.knowledgeBase.description}</textarea>
        {#if !isReader}
          <button type="submit">Salva knowledge base</button>
        {/if}
      </form>
    </div>

    <div class="panel">
      <h2>Assistenti associati</h2>
      <form method="POST" action="?/associate">
        {#each data.assistants as assistant (assistant.id)}
          <label class="check">
            <input
              type="checkbox"
              name="assistant_ids"
              value={assistant.id}
              checked={(assistant.knowledge_base_ids ?? []).includes(data.knowledgeBase.id)}
              disabled={isReader}
            />
            {assistant.name}
          </label>
        {/each}
        {#if !isReader}
          <button type="submit">Aggiorna associazioni</button>
        {/if}
      </form>
      <p class="hint">Ogni modifica crea una nuova versione dell'assistente; i run esistenti mantengono la loro.</p>
    </div>

    <div class="panel">
      <h2>Versioni</h2>
      <ol class="versions">
        {#each data.versions as version (version.version)}
          <li>
            <strong>v{version.version}</strong>
            <span class="muted">
              {version.state} · {version.chunk_count} chunk · tentativi {version.attempts}
            </span>
            {#if version.version === data.knowledgeBase.active_version}
              <span class="badge">attiva</span>
            {/if}
            {#if version.error_code}<span class="error">{version.error_code}</span>{/if}
          </li>
        {/each}
      </ol>

      {#if !isReader}
        <h3>Reindicizza</h3>
        <form method="POST" action="?/reindex">
          <input type="hidden" name="ifMatch" value={JSON.stringify(String(data.knowledgeBase.revision))} />
          <label for="chunk_size">Dimensione chunk</label>
          <input
            id="chunk_size"
            name="chunk_size"
            type="number"
            min="100"
            max="8000"
            value={latestVersion?.config?.chunk_size ?? 1000}
            required
          />
          <label for="chunk_overlap">Overlap</label>
          <input
            id="chunk_overlap"
            name="chunk_overlap"
            type="number"
            min="0"
            max="7999"
            value={latestVersion?.config?.chunk_overlap ?? 200}
            required
          />
          <button type="submit">Crea versione</button>
          <p class="hint">La reindicizzazione è atomica; la versione precedente resta leggibile.</p>
        </form>
      {/if}
    </div>

    {#if !isReader}
      <div class="panel danger-panel">
        <h2>Elimina knowledge base</h2>
        <p class="muted">L'operazione elimina documenti, chunk e associazioni. Richiede conferma.</p>
        <details>
          <summary>Mostra conferma</summary>
          <form method="POST" action="?/delete">
            <input type="hidden" name="ifMatch" value={JSON.stringify(String(data.knowledgeBase.revision))} />
            <input type="hidden" name="confirm" value="yes" />
            <button class="danger" type="submit">Elimina definitivamente</button>
          </form>
        </details>
      </div>
    {/if}
  </div>
</section>
