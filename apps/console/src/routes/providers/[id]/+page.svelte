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
{/if}
