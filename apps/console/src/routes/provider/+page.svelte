<script lang="ts">
  let { data, form } = $props();
</script>

<svelte:head>
  <title>Provider · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Provider</h1>
    <p class="muted">Provider attivo, riferimento al secret e catalogo modelli usato dagli assistenti.</p>
  </div>
</header>

{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}
{#if data.saved}
  <p class="notice" role="status">Configurazione provider salvata.</p>
{/if}

{#if data.forbidden}
  <p class="notice">
    La gestione del provider è riservata agli amministratori con gli scope
    <code>providers:read</code> e <code>providers:write</code>.
  </p>
{:else if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else if data.provider}
  <section aria-labelledby="provider-config-heading">
    <div class="section-head">
      <h2 id="provider-config-heading">Configurazione</h2>
      <span class="muted small">Revisione {data.provider.revision}</span>
    </div>
    <div class="row-actions">
      <span class="badge" class:ok={data.provider.applied} class:bad={!data.provider.applied}>
        {data.provider.applied ? 'applicato' : 'in attesa'}
      </span>
      <span class="muted small">
        {data.provider.managed ? 'gestito dalla console' : 'configurato dall’ambiente'}
      </span>
      <span class="badge" class:ok={data.provider.api_key_configured} class:bad={!data.provider.api_key_configured}>
        secret {data.provider.api_key_configured ? 'configurato' : 'non configurato'}
      </span>
    </div>
    {#if !data.provider.managed}
      <p class="notice">
        Questa configurazione arriva dall’ambiente del runtime. Salvala per gestirla dalla console.
      </p>
    {/if}
    {#if data.provider.managed && !data.provider.applied}
      <p class="notice">
        Il runtime non ha ancora applicato questa revisione. Il gateway ritenterà automaticamente.
      </p>
    {/if}

    {#if data.canManage}
      <form method="POST" action="?/save" class="form-grid">
        <input type="hidden" name="revision" value={data.provider.revision} />
        <div>
          <label for="provider">Tipo provider</label>
          <select id="provider" name="provider">
            <option value="openai-compatible" selected={data.provider.provider === 'openai-compatible'}>
              OpenAI-compatible
            </option>
            <option value="ollama" selected={data.provider.provider === 'ollama'}>Ollama</option>
          </select>
        </div>
        <div>
          <label for="base_url">Base URL</label>
          <input
            id="base_url"
            name="base_url"
            required
            maxlength="2000"
            value={data.provider.base_url}
            placeholder="https://api.example.com/v1"
            aria-describedby="base-url-hint"
          />
          <p class="hint" id="base-url-hint">
            Per OpenAI-compatible includi il prefisso versione. Egress e TLS restano a carico del runtime.
          </p>
        </div>
        <div>
          <label for="api_key_ref">Riferimento secret</label>
          <input
            id="api_key_ref"
            name="api_key_ref"
            maxlength="80"
            value={data.provider.api_key_ref}
            placeholder="MODEL_API_KEY"
            aria-describedby="api-key-ref-hint"
          />
          <p class="hint" id="api-key-ref-hint">
            Nome della variabile (o file <code>_FILE</code>) nel runtime. La chiave non viene mai salvata o mostrata nella console.
          </p>
        </div>
        <div>
          <label for="max_output_tokens">Max output tokens · 1–8192</label>
          <input
            id="max_output_tokens"
            name="max_output_tokens"
            type="number"
            min="1"
            max="8192"
            required
            value={data.provider.max_output_tokens}
          />
        </div>
        <div class="form-footer">
          <button type="submit">Salva provider</button>
        </div>
      </form>
    {:else}
      <p class="notice">
        La tua chiave può consultare il provider ma non modificarlo: manca lo scope
        <code>providers:write</code>.
      </p>
    {/if}
  </section>

  <section class="provider-models" aria-labelledby="provider-models-heading">
    <div class="section-head">
      <h2 id="provider-models-heading">Modelli</h2>
      <span class="muted small">{data.provider.models.length === 1 ? '1 modello' : `${data.provider.models.length} modelli`}</span>
    </div>

    {#if data.provider.models.length === 0}
      <p class="empty">Nessun modello configurato.</p>
    {:else}
      <table>
        <caption class="visually-hidden">Modelli del provider</caption>
        <thead>
          <tr>
            <th scope="col">Modello</th>
            <th scope="col">Capacità</th>
            <th scope="col">Contesto</th>
            {#if data.canManage}<th scope="col">Azioni</th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each data.provider.models as model (model.id)}
            <tr>
              <td><code>{model.id}</code></td>
              <td>{model.capabilities.join(', ')}</td>
              <td>{model.context_window ?? '—'}</td>
              {#if data.canManage}
                <td>
                  <form method="POST" action="?/removeModel">
                    <input type="hidden" name="revision" value={data.provider.revision} />
                    <input type="hidden" name="model_id" value={model.id} />
                    <button class="link danger" type="submit">Rimuovi</button>
                  </form>
                </td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if data.canManage}
      <div class="row-actions">
        <form method="POST" action="?/discover">
          <button class="secondary" type="submit">Scopri modelli dal provider</button>
        </form>
        <span class="muted small">Usa la configurazione salvata e il secret del runtime.</span>
      </div>

      {#if form?.discovered}
        <div class="notice" aria-live="polite">
          <strong>Modelli esposti dal provider</strong>
          {#if form.discovered.length > 0}
            <p class="muted small">Copiali nel campo del nuovo modello.</p>
            <p>
              {#each form.discovered as id, index}
                <code>{id}</code>{#if index < form.discovered.length - 1}, {/if}
              {/each}
            </p>
          {:else}
            <p class="muted small">Il provider non ha restituito modelli.</p>
          {/if}
        </div>
      {/if}

      <form method="POST" action="?/addModel" class="form-grid">
        <input type="hidden" name="revision" value={data.provider.revision} />
        <div>
          <label for="model_id">Identificativo modello</label>
          <input id="model_id" name="model_id" required maxlength="200" list="available-models" />
          <datalist id="available-models">
            {#each form?.discovered ?? [] as id}
              <option value={id}></option>
            {/each}
          </datalist>
        </div>
        <div>
          <span class="muted small">Capacità aggiuntive</span>
          <label class="check">
            <input type="checkbox" name="capabilities" value="tool_calling" disabled={data.provider.provider === 'ollama'} />
            Tool calling
          </label>
          <label class="check">
            <input type="checkbox" name="capabilities" value="structured_output" disabled={data.provider.provider === 'ollama'} />
            Structured output
          </label>
        </div>
        <div>
          <label for="context_window">Finestra di contesto</label>
          <input id="context_window" name="context_window" type="number" min="1" />
          <p class="hint">Opzionale. Non viene inventata se il provider non la dichiara.</p>
        </div>
        <div class="form-footer">
          <button type="submit">Aggiungi modello</button>
        </div>
      </form>
    {/if}
  </section>
{/if}

<style>
  .provider-models {
    margin-top: 2rem;
  }

  .form-footer {
    grid-column: 1 / -1;
  }
</style>
