<script lang="ts">
  let { form } = $props();
</script>

<svelte:head>
  <title>Accesso · Universal AI Kit</title>
</svelte:head>

<section class="auth-card">
  <h1>Accedi</h1>
  <p class="muted">
    La key viene usata solo dal server SvelteKit e conservata in memoria di
    sessione; non viene inviata al browser né inclusa nel bundle.
  </p>
  <form method="POST">
    <label for="apiKey">API key</label>
    <input
      id="apiKey"
      name="apiKey"
      type="password"
      autocomplete="current-password"
      required
    />
    <button type="submit">Accedi</button>
    {#if form?.error}
      <p class="error" role="alert">{form.error}</p>
    {/if}
  </form>
  <p class="hint">Sono ammessi ruoli admin, operator e reader. I token widget sono esclusi.</p>
</section>
