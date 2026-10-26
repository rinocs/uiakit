import { error, fail, redirect } from '@sveltejs/kit';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ params, locals }) => {
  const client = clientFor(locals.session!.apiKey);
  let run;
  try {
    run = await client.agentRuns.get(params.id);
  } catch (cause) {
    throw error(404, gatewayMessage(cause));
  }
  const [audit, approvals] = await Promise.all([
    client.auditEvents.list({ runId: params.id, limit: 100 }).catch(() => null),
    client.approvals.list().catch(() => []),
  ]);
  return {
    run,
    audit,
    approvals: approvals.filter((approval) => approval.run_id === params.id),
    principal: locals.session!.principal,
  };
};

export const actions = {
  cancel: async ({ params, locals }) => {
    try {
      await clientFor(locals.session!.apiKey).agentRuns.cancel(params.id);
      throw redirect(303, `/runs/${params.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },
};

function statusOf(error: unknown): number {
  const status = error && typeof error === 'object' && 'status' in error
    ? Number(error.status)
    : 0;
  return status >= 400 && status < 600 ? status : 400;
}

function isRedirect(value: unknown): boolean {
  return Boolean(value && typeof value === 'object' && 'status' in value && 'location' in value);
}
