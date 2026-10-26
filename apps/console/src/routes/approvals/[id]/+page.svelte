<script lang="ts">
  let { data, form } = $props();
  let approval = $derived(data.approval);
  let expired = $derived(new Date(approval.expires_at).getTime() <= Date.now());
  let canWrite = $derived(data.principal.scopes.includes('approvals:write'));
  let pending = $derived(approval.status === 'pending' && !expired);
  let risk = $derived(
    approval.policy_snapshot?.tool &&
      typeof approval.policy_snapshot.tool === 'object' &&
      'risk_level' in approval.policy_snapshot.tool
      ? String(approval.policy_snapshot.tool.risk_level)
      : 'unknown',
  );
  let connectors = $derived.by(() => {
    const tool = approval.policy_snapshot?.tool;
    const permissions =
      tool && typeof tool === 'object' && 'permissions' in tool && Array.isArray(tool.permissions)
        ? tool.permissions
        : [];
    return permissions
      .filter((permission): permission is string => typeof permission === 'string' && permission.startsWith('connector:'))
      .map((permission) => permission.slice('connector:'.length));
  });
</script>

<svelte:head>
  <title>Approvazione {approval.tool_id} · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <h1>{approval.tool_id}</h1>
    <p class="page-context">Approvazione · {approval.status}</p>
    <p class="muted">Run {approval.run_id} · richiesta da {approval.requested_by}</p>
  </div>
  <a class="button secondary" href="/approvals">Torna all'elenco</a>
</header>

{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}

<section class="split">
  <div class="panel">
    <h2>Binding immutabile</h2>
    <dl class="details">
      <dt>Tool</dt><dd>{approval.tool_id} v{approval.tool_version}</dd>
      <dt>Rischio</dt><dd><span class:bad={risk !== 'read_only'} class="badge">{risk}</span></dd>
      <dt>Connettore destinatario</dt>
      <dd>{connectors.length > 0 ? connectors.join(', ') : 'nessuno'}</dd>
      <dt>Richiedente</dt><dd>{approval.requested_by}</dd>
      <dt>Scade</dt><dd>{new Date(approval.expires_at).toLocaleString('it-IT')}</dd>
      <dt>Digest argomenti</dt><dd><code>{approval.arguments_digest}</code></dd>
      <dt>Digest policy</dt><dd><code>{approval.policy_digest}</code></dd>
    </dl>
    <p class="hint">
      Gli argomenti completi non sono persistiti né modificabili. La decisione
      vale solo per questo digest, tool, versione, run e policy.
    </p>

    {#if pending && canWrite}
      <div class="approval-actions">
        <form method="POST" action="?/approve">
          <label class="check">
            <input type="checkbox" name="confirm" value="yes" required />
            Ho verificato destinatario e rischio
          </label>
          <button type="submit">Approva</button>
        </form>
        <form method="POST" action="?/reject">
          <label class="check">
            <input type="checkbox" name="confirm" value="yes" required />
            Confermo il rifiuto
          </label>
          <button class="danger" type="submit">Rifiuta</button>
        </form>
      </div>
    {:else if expired}
      <p class="notice">Approvazione scaduta: non è più possibile approvarla.</p>
    {:else if !canWrite}
      <p class="notice">Il tuo token non ha lo scope approvals:write.</p>
    {:else}
      <p class="notice">Approvazione già decisa: {approval.status}.</p>
    {/if}
  </div>

  <div class="panel">
    <h2>Policy snapshot</h2>
    <pre class="json">{JSON.stringify(approval.policy_snapshot, null, 2)}</pre>
    {#if approval.decided_by}
      <p class="muted small">
        Decisa da {approval.decided_by}
        {#if approval.decided_at}· {new Date(approval.decided_at).toLocaleString('it-IT')}{/if}
      </p>
    {/if}
  </div>
</section>
