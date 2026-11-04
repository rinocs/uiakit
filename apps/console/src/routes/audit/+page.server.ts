import { clientFor, gatewayMessage, gatewayStatus } from '$lib/server/gateway';
import type { PageServerLoad } from './$types';

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;

function text(value: string | null): string {
  return (value ?? '').trim().slice(0, 200);
}

function limitOf(value: string | null): number {
  const parsed = Number.parseInt(value ?? '', 10);
  if (!Number.isFinite(parsed)) return DEFAULT_LIMIT;
  return Math.min(MAX_LIMIT, Math.max(1, parsed));
}

export const load: PageServerLoad = async ({ locals, url }) => {
  const filters = {
    action: text(url.searchParams.get('action')),
    runId: text(url.searchParams.get('run_id')),
    targetId: text(url.searchParams.get('target_id')),
    limit: limitOf(url.searchParams.get('limit')),
  };

  try {
    const events = await clientFor(locals.session!.apiKey).auditEvents.list({
      action: filters.action || undefined,
      runId: filters.runId || undefined,
      targetId: filters.targetId || undefined,
      limit: filters.limit,
    });
    return { events, filters, error: null, forbidden: false };
  } catch (error) {
    return {
      events: [],
      filters,
      error: gatewayMessage(error),
      forbidden: gatewayStatus(error) === 403,
    };
  }
};
