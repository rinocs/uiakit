<script lang="ts">
  import { page } from '$app/stores';
  import '../app.css';

  let { data, children } = $props();
</script>

<div class="shell">
  <aside class="sidebar" aria-label="Navigazione principale">
    <a class="brand" href="/">Universal AI Kit</a>
    <nav>
      <a class:active={$page.url.pathname === '/'} href="/">Dashboard</a>
      <a class:active={$page.url.pathname.startsWith('/assistants')} href="/assistants">Assistenti</a>
      <a class:active={$page.url.pathname.startsWith('/models')} href="/models">Modelli</a>
      <a class:active={$page.url.pathname.startsWith('/knowledge-bases')} href="/knowledge-bases">Knowledge base</a>
      <a class:active={$page.url.pathname.startsWith('/tools')} href="/tools">Tool</a>
      <a class:active={$page.url.pathname.startsWith('/plugins')} href="/plugins">Plugin</a>
      <a class:active={$page.url.pathname.startsWith('/approvals')} href="/approvals">Approvazioni</a>
      <a class:active={$page.url.pathname.startsWith('/runs')} href="/runs">Run</a>
      <a class:active={$page.url.pathname.startsWith('/playground')} href="/playground">Playground</a>
    </nav>
    {#if data.principal}
      <div class="identity">
        <strong>{data.principal.role}</strong>
        <span title={data.principal.scopes.join(', ')}>
          {data.principal.principal_id}
        </span>
        <form method="POST" action="/logout">
          <button class="link" type="submit">Esci</button>
        </form>
      </div>
    {/if}
  </aside>
  <main class="content">
    {@render children()}
  </main>
</div>
