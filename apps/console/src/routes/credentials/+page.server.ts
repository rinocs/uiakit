import { fail, redirect } from '@sveltejs/kit';
import type { CredentialInput } from '@universal-ai-kit/sdk';
import { clientFor, gatewayMessage, gatewayStatus } from '$lib/server/gateway';
import type { Actions, PageServerLoad } from './$types';

const ROLES = ['reader', 'operator', 'admin'] as const;
const MAX_EXPIRY_MS = 365 * 24 * 60 * 60 * 1000;

const CREDENTIAL_ERRORS: Record<string, string> = {
  cannot_rotate_current_credential:
    'Non puoi ruotare la credenziale con cui hai effettuato l’accesso. Usa un’altra credenziale admin.',
  cannot_revoke_current_credential:
    'Non puoi revocare la credenziale con cui hai effettuato l’accesso. Usa un’altra credenziale admin.',
  invalid_expiry: 'La scadenza deve essere futura e entro 365 giorni.',
  invalid_id: 'Identificativo della credenziale non valido.',
};

function credentialMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'code' in error) {
    const message = CREDENTIAL_ERRORS[String(error.code)];
    if (message) return message;
  }
  return gatewayMessage(error);
}

function parseScopes(raw: FormDataEntryValue | null): string[] {
  return [...new Set(String(raw ?? '').split(/[\s,]+/).filter(Boolean))];
}

/** Returns an ISO timestamp, undefined when omitted, or null when invalid. */
function parseExpiry(raw: FormDataEntryValue | null): string | undefined | null {
  const value = String(raw ?? '').trim();
  if (!value) return undefined;
  const at = new Date(value).getTime();
  const now = Date.now();
  if (!Number.isFinite(at) || at <= now || at > now + MAX_EXPIRY_MS) return null;
  return new Date(at).toISOString();
}

function parseId(data: FormData): string {
  return String(data.get('id') ?? '').trim();
}

function denied() {
  return fail(403, {
    error: 'Serve il ruolo admin con scope credentials:write per gestire le credenziali.',
    secret: null,
  });
}

function canManage(locals: App.Locals): boolean {
  const principal = locals.session!.principal;
  return principal.role === 'admin' && principal.scopes.includes('credentials:write');
}

export const load: PageServerLoad = async ({ locals, setHeaders }) => {
  // The page can render a one-time API key in an action response.
  setHeaders({ 'cache-control': 'no-store' });
  const principal = locals.session!.principal;
  const canWrite = canManage(locals);
  if (principal.role !== 'admin') {
    return { credentials: [], principal, canWrite: false, error: null, forbidden: true };
  }
  try {
    return {
      credentials: await clientFor(locals.session!.apiKey).credentials.list(),
      principal,
      canWrite,
      error: null,
      forbidden: false,
    };
  } catch (error) {
    return {
      credentials: [],
      principal,
      canWrite,
      error: credentialMessage(error),
      forbidden: gatewayStatus(error) === 403,
    };
  }
};

export const actions: Actions = {
  create: async ({ request, locals }) => {
    if (!canManage(locals)) return denied();

    const data = await request.formData();
    const role = String(data.get('role') ?? '');
    if (!ROLES.includes(role as (typeof ROLES)[number])) {
      return fail(422, {
        error: 'Seleziona un ruolo tra reader, operator e admin.',
        secret: null,
      });
    }
    const scopes = parseScopes(data.get('scopes'));
    if (scopes.length === 0) {
      return fail(422, { error: 'Inserisci almeno uno scope.', secret: null });
    }
    const principalId = String(data.get('principal_id') ?? '').trim();
    if (principalId.length > 200) {
      return fail(422, { error: 'Il principal ID supera i 200 caratteri.', secret: null });
    }
    const expiresAt = parseExpiry(data.get('expires_at'));
    if (expiresAt === null) {
      return fail(422, {
        error: 'La scadenza deve essere futura e entro 365 giorni.',
        secret: null,
      });
    }

    const input: CredentialInput = {
      role: role as CredentialInput['role'],
      scopes,
      ...(principalId ? { principal_id: principalId } : {}),
      ...(expiresAt ? { expires_at: expiresAt } : {}),
    };

    try {
      const created = await clientFor(locals.session!.apiKey).credentials.create(input);
      return { error: null, secret: created.api_key };
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: credentialMessage(error),
        secret: null,
      });
    }
  },

  rotate: async ({ request, locals }) => {
    if (!canManage(locals)) return denied();

    const data = await request.formData();
    const id = parseId(data);
    if (!id) {
      return fail(422, { error: 'Identificativo della credenziale mancante.', secret: null });
    }
    const expiresAt = parseExpiry(data.get('expires_at'));
    if (expiresAt === null) {
      return fail(422, {
        error: 'La scadenza deve essere futura e entro 365 giorni.',
        secret: null,
      });
    }

    try {
      const rotated = await clientFor(locals.session!.apiKey).credentials.rotate(
        id,
        expiresAt ? { expires_at: expiresAt } : {},
      );
      return { error: null, secret: rotated.api_key };
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: credentialMessage(error),
        secret: null,
      });
    }
  },

  revoke: async ({ request, locals }) => {
    if (!canManage(locals)) return denied();

    const data = await request.formData();
    const id = parseId(data);
    if (!id) {
      return fail(422, { error: 'Identificativo della credenziale mancante.', secret: null });
    }

    try {
      await clientFor(locals.session!.apiKey).credentials.revoke(id);
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: credentialMessage(error),
        secret: null,
      });
    }
    throw redirect(303, '/credentials');
  },
};
