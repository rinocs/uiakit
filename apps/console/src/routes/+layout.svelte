<script lang="ts">
  import { page } from '$app/stores';
  import '../app.css';

  let { data, children } = $props();
  const groups = [
    { label: 'Workspace', links: [
      { href: '/', label: 'Dashboard', icon: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z' },
      { href: '/playground', label: 'Playground', icon: 'm8 5 11 7-11 7z' },
    ] },
    { label: 'Configurazione', links: [
      { href: '/assistants', label: 'Assistenti', icon: 'M5 8h14v12H5z M9 12v2 M15 12v2 M9 17h6 M12 4v4 M10 4h4' },
      { href: '/provider', label: 'Provider', icon: 'M4 7h16v10H4z M8 12h8 M8 15h5 M7 7V4 M17 7V4' },
      { href: '/models', label: 'Modelli', icon: 'm12 3 9 5-9 5-9-5z M3 12l9 5 9-5 M3 16l9 5 9-5' },
      { href: '/knowledge-bases', label: 'Knowledge base', icon: 'M12 6v15 M3 4c3-1 6 0 9 2 3-2 6-3 9-2v14c-3-1-6 0-9 2-3-2-6-3-9-2z' },
      { href: '/tools', label: 'Tool', icon: 'M14 6V3h7v7h-3 M14 3l-4 4 7 7 4-4 M10 10 3 17v4h4l7-7' },
      { href: '/plugins', label: 'Plugin', icon: 'M8 3v5 M16 3v5 M5 8h14v3a7 7 0 0 1-14 0z M12 18v3' },
      { href: '/credentials', label: 'Credenziali', icon: 'M15 7a4 4 0 1 1-7.5 1.9L3 13.4V17h3v-2h2v-2h2l2.5-2.5A4 4 0 0 0 15 7z' },
    ] },
    { label: 'Monitoraggio', links: [
      { href: '/runs', label: 'Run', icon: 'M3 12h4l3-8 4 16 3-8h4' },
      { href: '/approvals', label: 'Approvazioni', icon: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z m-4 9 3 3 5-6' },
      { href: '/audit', label: 'Registro audit', icon: 'M6 3h12v18l-3-2-3 2-3-2-3 2z M9 8h6 M9 12h6 M9 16h3' },
    ] },
  ];
</script>

<div class="shell" class:auth-shell={$page.url.pathname === '/login'} data-theme={data.preferences.theme} data-density={data.preferences.density}>
  <a class="skip-link" href="#main-content">Vai al contenuto</a>
  <aside class="sidebar" aria-label="Navigazione principale">
    <a class="brand" href="/">
      <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M5 5v9a7 7 0 0 0 14 0V5 M10 5v9a2 2 0 0 0 4 0V5" /></svg></span>
      <span>Universal AI Kit<small>Console</small></span>
    </a>
    {#if data.principal}
      <nav>
        {#each groups as group}
          <div class="nav-group">
            <p class="nav-label">{group.label}</p>
            {#each group.links as link}
              {@const active = link.href === '/' ? $page.url.pathname === '/' : $page.url.pathname.startsWith(link.href)}
              <a class:active href={link.href} aria-current={active ? 'page' : undefined}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d={link.icon} /></svg>{link.label}
              </a>
            {/each}
          </div>
        {/each}
      </nav>
      <div class="sidebar-bottom">
        <a class="settings-nav" class:active={$page.url.pathname === '/settings'} href="/settings" aria-current={$page.url.pathname === '/settings' ? 'page' : undefined}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16 M4 17h16 M8 4v6 M16 14v6" /></svg>Impostazioni
        </a>
        <div class="identity">
          <strong>{data.principal.role}</strong>
          <span title={data.principal.scopes.join(', ')}>{data.principal.principal_id}</span>
          <form method="POST" action="/logout"><button class="link" type="submit">Esci</button></form>
        </div>
      </div>
    {/if}
  </aside>
  <main id="main-content" class="content" tabindex="-1">
    {@render children()}
  </main>
</div>
