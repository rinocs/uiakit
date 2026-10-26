<script lang="ts">
  let { data, form } = $props();
  let assistant = $derived(data.assistant);
  let values = $derived(
    form?.values ?? {
      description: assistant.description ?? '',
      tools: assistant.tools ?? [],
      knowledge_base_ids: assistant.knowledge_base_ids ?? [],
      conversation: assistant.memory?.conversation ?? true,
      max_input_chars: String(assistant.limits?.max_input_chars ?? 64000),
      max_output_chars: String(assistant.limits?.max_output_chars ?? 64000),
      duration_seconds: String(assistant.limits?.duration_seconds ?? 120),
      max_steps: String(assistant.limits?.max_steps ?? 4),
      max_tool_calls: String(assistant.limits?.max_tool_calls ?? 8),
      max_tokens: String(assistant.limits?.max_tokens ?? 8192),
      name: assistant.name,
      model: assistant.model,
      system_prompt: assistant.system_prompt,
      directives: (assistant.directives ?? []).join(', '),
    },
  );
  let readOnly = $derived(data.principal.role === 'reader');
  let toolOptions = $derived([
    ...data.tools.map((tool) => ({ id: tool.id, name: tool.name })),
    ...values.tools.filter((id) => !data.tools.some((tool) => tool.id === id)).map((id) => ({ id, name: `${id} (fuori catalogo)` })),
  ]);
  let kbOptions = $derived([
    ...data.knowledgeBases.map((kb) => ({ id: kb.id, name: kb.name })),
    ...values.knowledge_base_ids.filter((id) => !data.knowledgeBases.some((kb) => kb.id === id)).map((id) => ({ id, name: `${id} (fuori catalogo)` })),
  ]);
</script>

<svelte:head>
  <title>{assistant.name} · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>{assistant.name}</h1>
    <p class="page-context">Assistente · v{assistant.version}</p>
  </div>
  <a class="button secondary" href="/assistants">Torna all'elenco</a>
</header>

{#if data.principal.role === 'reader'}
  <p class="notice">Ruolo reader: configurazione in sola lettura.</p>
{/if}

{#if data.catalogWarning}<p class="notice" role="status">{data.catalogWarning}</p>{/if}
<section class="split assistant-settings">
  <div class="panel">
    <h2>Configurazione</h2>
    <form method="POST" action="?/update">
      <input type="hidden" name="ifMatch" value={JSON.stringify(String(assistant.version))} />

      <label for="name">Nome</label>
      <input id="name" name="name" maxlength="200" required value={values.name} disabled={data.principal.role === 'reader'} />

      <label for="description">Descrizione</label>
      <textarea id="description" name="description" rows="2" maxlength="4000" disabled={readOnly}>{values.description}</textarea>

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
      <fieldset disabled={readOnly}>
        <legend>Risorse e memoria</legend>
        <p class="hint">I tool selezionati richiedono anche i permessi di esecuzione dell'utente. Le operazioni restano soggette ad approvazione.</p>
        <label for="tools">Tool abilitati</label>
        <select id="tools" name="tools" multiple size="4" aria-describedby="selection-help">
          {#each toolOptions as tool}<option value={tool.id} selected={values.tools.includes(tool.id)}>{tool.name}</option>{/each}
        </select>
        {#if toolOptions.length === 0}<p class="hint">Nessun tool disponibile nel catalogo.</p>{/if}
        <label for="knowledge_base_ids">Knowledge base collegate</label>
        <select id="knowledge_base_ids" name="knowledge_base_ids" multiple size="4" aria-describedby="selection-help">
          {#each kbOptions as kb}<option value={kb.id} selected={values.knowledge_base_ids.includes(kb.id)}>{kb.name}</option>{/each}
        </select>
        {#if kbOptions.length === 0}<p class="hint">Nessuna knowledge base disponibile.</p>{/if}
        <p class="hint" id="selection-help">Selezione multipla: usa Ctrl su Windows/Linux o Cmd su macOS per aggiungere o rimuovere elementi.</p>
        <label class="check"><input type="checkbox" name="conversation" checked={values.conversation} />Mantieni la memoria della conversazione</label>
      </fieldset>

      <fieldset disabled={readOnly}>
        <legend>Limiti di esecuzione</legend>
        <div class="form-grid">
          <div><label for="max_input_chars">Caratteri input · 1–64.000</label><input id="max_input_chars" name="max_input_chars" type="number" min="1" max="64000" required value={values.max_input_chars} /></div>
          <div><label for="max_output_chars">Caratteri output · 1–64.000</label><input id="max_output_chars" name="max_output_chars" type="number" min="1" max="64000" required value={values.max_output_chars} /></div>
          <div><label for="duration_seconds">Durata massima · secondi</label><input id="duration_seconds" name="duration_seconds" type="number" min="0.001" step="any" max="120" required value={values.duration_seconds} /><p class="hint">Maggiore di 0, massimo 120.</p></div>
          <div><label for="max_steps">Passi · 0–16</label><input id="max_steps" name="max_steps" type="number" min="0" max="16" required value={values.max_steps} /></div>
          <div><label for="max_tool_calls">Chiamate tool · 0–32</label><input id="max_tool_calls" name="max_tool_calls" type="number" min="0" max="32" required value={values.max_tool_calls} /></div>
          <div><label for="max_tokens">Budget token · 0–1.000.000</label><input id="max_tokens" name="max_tokens" type="number" min="0" max="1000000" required value={values.max_tokens} /></div>
        </div>
        <p class="hint">Per passi, chiamate tool e token, 0 usa il valore predefinito del runtime.</p>
      </fieldset>
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
