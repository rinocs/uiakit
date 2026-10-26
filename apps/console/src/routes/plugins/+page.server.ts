import { fail, redirect } from '@sveltejs/kit';
import type { PluginSetting } from '@universal-ai-kit/sdk';
import { clientFor, gatewayMessage } from '$lib/server/gateway';

export const load = async ({ locals }) => {
  const client = clientFor(locals.session!.apiKey);
  try {
    const catalog = await client.plugins.list();
    const health = await Promise.all(
      catalog.plugins.map(async (plugin) => ({
        id: plugin.manifest.id,
        health: await client.plugins.health(plugin.manifest.id).catch(() => null),
      })),
    );
    return {
      catalog,
      health: Object.fromEntries(health.map((entry) => [entry.id, entry.health])),
      principal: locals.session!.principal,
      error: null,
    };
  } catch (error) {
    return {
      catalog: null,
      health: {},
      principal: locals.session!.principal,
      error: gatewayMessage(error),
    };
  }
};

export const actions = {
  configure: async ({ request, locals }) => {
    const data = await request.formData();
    const id = String(data.get('plugin_id') ?? '');
    const ifMatch = String(data.get('ifMatch') ?? '');
    let config: Record<string, unknown>;
    try {
      const parsed = JSON.parse(String(data.get('config') ?? '{}'));
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('config must be an object');
      }
      config = parsed;
    } catch {
      return fail(422, { error: 'La configurazione plugin deve essere un oggetto JSON valido.' });
    }
    const setting: PluginSetting = {
      enabled: data.get('enabled') === 'on',
      config,
    };
    try {
      await clientFor(locals.session!.apiKey).plugins.configure(id, setting, { ifMatch });
      throw redirect(303, '/plugins');
    } catch (cause) {
      if (isRedirect(cause)) throw cause;
      return fail(statusOf(cause), { error: gatewayMessage(cause) });
    }
  },

  remove: async ({ request, locals }) => {
    const data = await request.formData();
    try {
      await clientFor(locals.session!.apiKey).plugins.remove(
        String(data.get('plugin_id') ?? ''),
        { ifMatch: String(data.get('ifMatch') ?? '') },
      );
      throw redirect(303, '/plugins');
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
