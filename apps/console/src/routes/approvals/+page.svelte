<script lang="ts">
  let { data } = $props();

  function risk(approval: { policy_snapshot: Record<string, unknown> }): string {
    const tool = approval.policy_snapshot.tool;
    return tool && typeof tool === 'object' && 'risk_level' in tool
      ? String(tool.risk_level)
      : 'unknown';
  }

  function connectors(approval: { policy_snapshot: Record<string, unknown> }): string[] {
    const tool = approval.policy_snapshot.tool;
    const permissions = tool && typeof tool === 'object' && 'permissions' in tool && Array.isArray(tool.permissions)
      ? tool.permissions
      : [];
    return permissions
      .filter((permission): permission is string => typeof permission === 'string' && permission.startsWith('connector:'))
      .map((permission) => permission.slice('connector:'.length));
  }
</script>

<svelte:head>
  <title>Approvazioni · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>Approvazioni</h1>
  </div>
</header>

{#if data.error}
  <p class="error" role="alert">{data.error}</p>
{:else if data.approvals.length === 0}
  <p class="empty">Nessuna richiesta di approvazione.</p>
{:else}
  <ul class="list">
    {#each data.approvals as approval (approval.id)}
      <li>
        <a href={`/approvals/${approval.id}`}>
          <span>
            <strong>{approval.tool_id}</strong>
            <span class="muted"> · rischio {risk(approval)}</span>
          </span>
          <span class="badge">{approval.status}</span>
          <span class="muted small">
            {connectors(approval).length > 0 ? `connettore ${connectors(approval).join(', ')}` : 'nessun connector'}
            · scade {new Date(approval.expires_at).toLocaleString('it-IT')}
          </span>
        </a>
      </li>
    {/each}
  </ul>
{/if}
