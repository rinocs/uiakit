<script lang="ts">
  let { data, form } = $props();
</script>

<svelte:head>
  <title>Conversazione · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Cronologia</h1>
    <p class="muted small"><code>{data.conversationId}</code></p>
  </div>
  <div class="head-actions">
    <a class="button secondary" href={`/playground?conversation=${data.conversationId}`}>Apri playground</a>
    <a class="button secondary" href={`/runs?conversation=${data.conversationId}`}>Run collegati</a>
  </div>
</header>

{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}

{#if data.principal.role !== 'reader'}
  <details class="danger-panel">
    <summary>Elimina conversazione</summary>
    <p class="muted">Elimina messaggi, run, approvazioni e tombstone non sensibile. L'operazione non è reversibile.</p>
    <form method="POST" action="?/delete">
      <button class="danger" type="submit">Elimina definitivamente</button>
    </form>
  </details>
{/if}

{#if data.messages.length === 0}
  <p class="empty">Nessun messaggio completato in questa conversazione.</p>
{:else}
  <ol class="conversation-history">
    {#each data.messages as message, index (index)}
      <li class="message" data-role={message.role}>
        <strong>{message.role === 'assistant' ? 'Assistente' : 'Utente'}</strong>
        <div class="message-text">{message.content}</div>
      </li>
    {/each}
  </ol>
{/if}

<h2>Run</h2>
{#if data.runs.length === 0}
  <p class="empty">Nessun run per questa conversazione.</p>
{:else}
  <ul class="list">
    {#each data.runs as run (run.id)}
      <li>
        <a href={`/runs/${run.id}`}>
          <span><strong>{run.status}</strong> · {run.model}</span>
          <span class="muted small">{new Date(run.created_at).toLocaleString('it-IT')}</span>
        </a>
      </li>
    {/each}
  </ul>
{/if}
