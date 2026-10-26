<script lang="ts">
  let { data, form } = $props();
  let assistant = $derived(data.assistant);
  let values = $derived(
    form?.values ?? {
      name: assistant.name,
      model: assistant.model,
      system_prompt: assistant.system_prompt,
      directives: (assistant.directives ?? []).join(', '),
    },
  );
</script>

<svelte:head>
  <title>{assistant.name} · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <p class="eyebrow">Assistente · v{assistant.version}</p>
    <h1>{assistant.name}</h1>
  </div>
  <a class="button secondary" href="/assistants">Torna all'elenco</a>
</header>

{#if data.principal.role === 'reader'}
  <p class="notice">Ruolo reader: configurazione in sola lettura.</p>
{/if}

<section class="split">
  <div class="panel">
    <h2>Configurazione</h2>
    <form method="POST" action="?/update">
      <input type="hidden" name="ifMatch" value={JSON.stringify(String(assistant.version))} />

      <label for="name">Nome</label>
      <input id="name" name="name" maxlength="200" required value={values.name} disabled={data.principal.role === 'reader'} />

      <label for="model">Modello</label>
      <select id="model" name="model" required disabled={data.principal.role === 'reader'}>
        {#each data.models as model}
          <option value={model.id} selected={model.id === values.model}>
            {model.id} · {model.provider}
          </option>
        {/each}
      </select>

      <label for="system_prompt">System prompt</label>
      <textarea id="system_prompt" name="system_prompt" rows="10" maxlength="16000" disabled={data.principal.role === 'reader'}>{values.system_prompt}</textarea>

      <label for="directives">Direttive</label>
      <input id="directives" name="directives" value={values.directives} disabled={data.principal.role === 'reader'} />
      <p class="hint">Il salvataggio crea una nuova versione; i run già avviati mantengono la loro.</p>

      {#if data.principal.role !== 'reader'}
        <button type="submit">Salva nuova versione</button>
      {/if}
      {#if form?.error}
        <p class="error" role="alert">{form.error}</p>
      {/if}
    </form>
  </div>

  <div class="panel">
    <h2>Versioni</h2>
    <ol class="versions">
      {#each data.versions as version}
        <li>
          <strong>v{version.version}</strong>
          <span class="muted">{version.model}</span>
          {#if version.version === assistant.version}
            <span class="badge">corrente</span>
          {/if}
        </li>
      {/each}
    </ol>
  </div>
</section>
