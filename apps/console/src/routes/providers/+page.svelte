<script lang="ts">
  import { page } from '$app/stores';
  let { data, form } = $props();
  let models: { id: string }[] = [];
  let modelInput = '';
  function addModel() { if (modelInput.trim()) { models = [...models, { id: modelInput.trim() }]; modelInput = ''; } }
  function removeModel(i: number) { models = models.filter((_, idx) => idx !== i); }
</script>

<h1>Provider</h1>
{#if data.forbidden}
  <p role="alert">Serve il ruolo admin con gli scope providers:read e providers:write.</p>
{:else if data.error}
  <p role="alert">{data.error}</p>
{:else}
  <table>
    <thead><tr><th>id</th><th>nome</th></tr></thead>
    <tbody>
      {#each data.profiles as p}
        <tr><td>{p.id}</td><td>{p.name}</td><td><a href={`/providers/${p.id}`}>Apri</a></td></tr>
      {/each}
    </tbody>
  </table>

  <h2>Crea provider</h2>
  <form method="POST" action="?/create">
    <label>Identificativo <input name="id" /></label>
    <label>Nome <input name="name" /></label>
    <label>Tipo provider
      <select name="provider">
        <option value="openai">openai</option>
        <option value="ollama">ollama</option>
      </select>
    </label>
    <label>Base URL <input name="base_url" /></label>
    <label>Max output tokens · 1–8192 <input name="max_output_tokens" type="number" /></label>
    <label>Identificativo modello <input bind:value={modelInput} /></label>
    <button type="button" onclick={addModel}>Aggiungi modello</button>
    {#each models as m, i}
      <div>{m.id} <button type="button" onclick={() => removeModel(i)}>Rimuovi</button></div>
    {/each}
    <input type="hidden" name="models" value={JSON.stringify(models.map(m => ({ id: m.id, capabilities: [], context_window: null })))} />
    <button type="submit">Crea provider</button>
  </form>
  {#if form?.error}<p role="alert">{form.error}</p>{/if}
{/if}
