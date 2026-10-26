<script lang="ts">
  import PlaygroundChat from './PlaygroundChat.svelte';

  let { data, form } = $props();
</script>

<svelte:head>
  <title>Playground · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <p class="eyebrow">Test chatbot</p>
    <h1>Playground</h1>
    {#if data.conversationId}
      <p class="muted small">Conversazione <code>{data.conversationId}</code></p>
    {/if}
  </div>
  <div class="head-actions">
    {#if data.conversationId}
      <a class="button secondary" href={`/conversations/${data.conversationId}`}>Cronologia</a>
      <a class="button secondary" href={`/runs?conversation=${data.conversationId}`}>Run</a>
    {/if}
  </div>
</header>

{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}
{#if data.conversationError}
  <p class="error" role="alert">{data.conversationError}</p>
{/if}

{#if !data.conversationId}
  <section class="panel">
    <h2>Nuova conversazione</h2>
    {#if data.assistants.length === 0}
      <p class="empty">Nessun assistente disponibile.</p>
    {:else}
      <form method="POST" action="?/create">
        <label for="assistant_id">Assistente</label>
        <select id="assistant_id" name="assistant_id" required>
          {#each data.assistants as assistant (assistant.id)}
            <option value={assistant.id}>{assistant.name} · {assistant.model}</option>
          {/each}
        </select>
        <button type="submit">Apri playground</button>
      </form>
    {/if}
  </section>
{:else}
  <PlaygroundChat
    conversationId={data.conversationId}
    initialMessages={data.messages}
  />
{/if}
