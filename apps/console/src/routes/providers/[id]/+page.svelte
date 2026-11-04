<script lang="ts">
  let { data } = $props();
</script>
{#if data.profile}
  <h1>{data.profile.id}</h1>
  <form method="POST" action="?/save">
    <label>Nome <input name="name" value={data.profile.name} /></label>
    <label>Base URL <input name="base_url" value={data.profile.base_url} /></label>
    <input type="hidden" name="revision" value={data.profile.revision} />
    <input type="hidden" name="provider" value={data.profile.provider} />
    <input type="hidden" name="max_output_tokens" value={data.profile.max_output_tokens} />
    <input type="hidden" name="models" value={JSON.stringify(data.profile.models)} />
    <button type="submit">Salva provider</button>
  </form>
  {#if data.saved}<p role="status">Configurazione provider salvata.</p>{/if}
  <section>
    <h2>Credenziali</h2>
    <p>{data.profile.secret_configured ? 'secret configurato' : 'secret non configurato'}</p>
    <form method="POST" action="?/saveSecret">
      <label>Chiave API <input type="password" name="value" /></label>
      <label>Variabile d'ambiente <input name="ref" /></label>
      <button type="submit" formaction="?/saveSecret" name="action" value="key">Salva chiave</button>
      <button type="submit" formaction="?/saveSecret" name="action" value="env">Usa variabile d'ambiente</button>
    </form>
    <form method="POST" action="?/clearSecret">
      <button type="submit">Rimuovi chiave</button>
    </form>
  </section>
{/if}
