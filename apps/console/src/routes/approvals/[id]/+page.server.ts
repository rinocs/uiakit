import { error, fail, redirect } from '@sveltejs/kit';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ params, locals }) => {
  try {
    return {
      approval: await clientFor(locals.session!.apiKey).approvals.get(params.id),
      principal: locals.session!.principal,
    };
  } catch (cause) {
    throw error(404, gatewayMessage(cause));
  }
};

export const actions = {
  approve: async ({ request, params, locals }) => {
    const data = await request.formData();
    if (String(data.get('confirm') ?? '') !== 'yes') {
      return fail(400, { error: 'Conferma di aver verificato destinatario e rischio.' });
    }
    try {
      await clientFor(locals.session!.apiKey).approvals.approve(params.id);
      throw redirect(303, `/approvals/${params.id}`);
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },
  reject: async ({ request, params, locals }) => {
    const data = await request.formData();
    if (String(data.get('confirm') ?? '') !== 'yes') {
      return fail(400, { error: 'Conferma il rifiuto.' });
    }
    try {
      await clientFor(locals.session!.apiKey).approvals.reject(params.id);
      throw redirect(303, `/approvals/${params.id}`);
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
