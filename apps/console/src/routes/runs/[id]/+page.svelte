<script lang="ts">
  let { data, form } = $props();
  let run = $derived(data.run);
  let cancellable = $derived(['queued', 'running', 'waiting_approval'].includes(run.status));
</script>

<svelte:head>
  <title>Run {run.id.slice(0, 8)} · Universal AI Kit</title>
</svelte:head>

<header class="page-head">
  <div>
    <p class="eyebrow">Run · {run.status}</p>
    <h1>{run.model}</h1>
    <p class="muted">
      Assistente {run.assistant_id} v{run.assistant_version} ·
      <a href={`/conversations/${run.conversation_id}`}>conversazione</a>
    </p>
  </div>
  <div class="head-actions">
    <a class="button secondary" href="/runs">Torna ai run</a>
    {#if cancellable && data.principal.scopes.includes('agent-runs:write')}
      <form method="POST" action="?/cancel">
        <button class="danger" type="submit">Cancella run</button>
      </form>
    {/if}
  </div>
</header>

{#if form?.error}
  <p class="error" role="alert">{form.error}</p>
{/if}

<section class="split">
  <div>
    <div class="panel">
      <h2>Stato</h2>
      <dl class="details">
        <dt>Status</dt>
        <dd>
          <span class:ok={run.status === 'completed'} class:bad={['failed', 'cancelled'].includes(run.status)} class="badge">
            {run.status}
          </span>
        </dd>
        <dt>Creato</dt><dd>{new Date(run.created_at).toLocaleString('it-IT')}</dd>
        <dt>Aggiornato</dt><dd>{new Date(run.updated_at).toLocaleString('it-IT')}</dd>
        {#if run.finished_at}<dt>Terminato</dt><dd>{new Date(run.finished_at).toLocaleString('it-IT')}</dd>{/if}
        {#if run.cancel_requested_at}<dt>Cancel richiesto</dt><dd>{new Date(run.cancel_requested_at).toLocaleString('it-IT')}</dd>{/if}
      </dl>
      {#if run.status === 'waiting_approval'}
        <p class="notice">Il run attende una decisione umana. Le approvazioni collegate sono qui sotto.</p>
      {/if}
    </div>

    <div class="panel">
      <h2>Approvazioni collegate</h2>
      {#if data.approvals.length === 0}
        <p class="empty">Nessuna approvazione per questo run.</p>
      {:else}
        <ul class="list">
          {#each data.approvals as approval (approval.id)}
            <li>
              <a href={`/approvals/${approval.id}`}>
                <span><strong>{approval.tool_id}</strong> · {approval.status}</span>
                <span class="muted small">scade {new Date(approval.expires_at).toLocaleString('it-IT')}</span>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>

  <div class="panel">
    <h2>Audit</h2>
    <p class="hint">
      I dettagli sono già redatti dal gateway: prompt, messaggi, header e segreti
      non vengono mostrati.
    </p>
    {#if data.audit === null}
      <p class="notice">Audit non disponibile per il tuo ruolo.</p>
    {:else if data.audit.length === 0}
      <p class="empty">Nessun evento di audit.</p>
    {:else}
      <ul class="audit-list">
        {#each data.audit as event (event.id)}
          <li>
            <div><strong>{event.action}</strong> · {event.outcome}</div>
            <div class="muted small">
              {new Date(event.created_at).toLocaleString('it-IT')}
              {#if event.target_type}· {event.target_type}{/if}
            </div>
            <pre class="json">{JSON.stringify(event.details ?? {}, null, 2)}</pre>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</section>
