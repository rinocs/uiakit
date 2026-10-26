<script lang="ts">
  import { page } from '$app/stores';
  let { data, form } = $props();
</script>

<svelte:head><title>Impostazioni · Universal AI Kit</title></svelte:head>
<header class="page-head">
  <div><h1>Impostazioni</h1><p class="muted">Il tuo ambiente di lavoro, le tue preferenze.</p></div>
</header>
{#if form?.error}<p class="error" role="alert">{form.error}</p>{/if}
{#if $page.url.searchParams.get('saved') === '1'}<p class="notice" role="status">Preferenze salvate su questo browser.</p>{/if}
<div class="settings-layout">
  <section class="panel" aria-labelledby="appearance-heading">
    <div class="section-intro"><h2 id="appearance-heading">Aspetto e leggibilità</h2><p class="muted">Si applicano a tutte le pagine della console e restano attive su questo browser.</p></div>
    <form method="POST" action="?/appearance">
      <label for="theme">Tema</label>
      <select id="theme" name="theme" value={data.preferences.theme}>
        <option value="dark">Graphite scuro</option><option value="light">Graphite chiaro</option><option value="system">Segui il sistema</option>
      </select>
      <p class="hint">Accento arancio in ogni tema. Il tema di sistema segue le preferenze del dispositivo.</p>
      <label for="density">Densità</label>
      <select id="density" name="density" value={data.preferences.density}>
        <option value="comfortable">Comoda</option><option value="compact">Compatta</option>
      </select>
      <p class="hint">La densità compatta riduce lo spazio in navigazione, elenchi e tabelle.</p>
      <div class="form-footer"><button type="submit">Salva preferenze</button></div>
    </form>
  </section>
  <section class="settings-resources" aria-labelledby="configuration-heading">
    <h2 id="configuration-heading">Configurazione operativa</h2>
    <p class="muted">Ogni assistente ha una configurazione versionata. Le modifiche si applicano ai nuovi run.</p>
    <ul class="settings-links">
      <li><a href="/assistants"><strong>Assistenti</strong><span>Modello, prompt, tool, memoria e limiti</span></a></li>
      <li><a href="/knowledge-bases"><strong>Knowledge base</strong><span>Documenti, chunking e versioni dell'indice</span></a></li>
      <li><a href="/plugins"><strong>Plugin</strong><span>Stato e configurazione delle estensioni</span></a></li>
      <li><a href="/models"><strong>Modelli e capacità</strong><span>Catalogo disponibile nel runtime</span></a></li>
    </ul>
    <p class="hint">Provider, endpoint e credenziali sono gestiti dal deployment. La console rispetta i permessi del tuo account.</p>
  </section>
</div>
