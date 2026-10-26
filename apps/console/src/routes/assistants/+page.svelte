<script lang="ts">
  let { data, form } = $props();
</script>

<svelte:head>
  <title>Assistenti · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <p class="eyebrow">Configurazione</p>
    <h1>Assistenti</h1>
  </div>
</header>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{/if}

<section class="split">
  <div>
    <h2>Elenco</h2>
    {#if data.assistants.length === 0}
      <p class="empty">Nessun assistente configurato.</p>
    {:else}
      <ul class="list">
        {#each data.assistants as assistant}
          <li>
            <a href={`/assistants/${assistant.id}`}>
              <strong>{assistant.name}</strong>
              <span class="muted">{assistant.model} · v{assistant.version}</span>
            </a>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  {#if data.principal.role !== 'reader'}
    <div class="panel">
      <h2>Nuovo assistente</h2>
      <p class="muted">Salva una nuova versione con il modello e le direttive scelte.</p>
      <form method="POST" action="?/create">
        <label for="name">Nome</label>
        <input id="name" name="name" maxlength="200" required value={form?.values?.name ?? ''} />

        <label for="model">Modello</label>
        <select id="model" name="model" required>
          {#each data.models as model}
            <option value={model.id}>{model.id} · {model.provider}</option>
          {/each}
        </select>

        <label for="system_prompt">System prompt</label>
        <textarea id="system_prompt" name="system_prompt" rows="6" maxlength="16000">{form?.values?.system_prompt ?? ''}</textarea>

        <label for="directives">Direttive</label>
        <input
          id="directives"
          name="directives"
          placeholder="rag, safety"
          value={form?.values?.directives ?? ''}
        />
        <p class="hint">Nomi separati da virgola; il runtime valida registro e dipendenze.</p>

        <button type="submit">Crea assistente</button>
        {#if form?.error}
          <p class="error" role="alert">{form.error}</p>
        {/if}
      </form>
    </div>
  {:else}
    <div class="panel">
      <h2>Accesso in sola lettura</h2>
      <p class="muted">Il ruolo reader non può creare o modificare assistenti.</p>
    </div>
  {/if}
</section>
