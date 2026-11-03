import { fail, redirect } from '@sveltejs/kit';
import type {
  ProviderConfiguration,
  ProviderModel,
  ProviderUpdate,
} from '@universal-ai-kit/sdk';
import { clientFor, gatewayMessage, gatewayStatus } from '$lib/server/gateway';
import type { Actions, PageServerLoad } from './$types';

const PROVIDER_MESSAGES: Record<string, string> = {
  model_in_use:
    'Il modello o le sue capacità sono usati da almeno un assistente. Aggiorna quegli assistenti prima di modificarli.',
  invalid_api_key_ref:
    'Riferimento secret non valido: usa MODEL_API_KEY oppure PROVIDER_API_KEY_*.',
  api_key_ref_not_supported: 'Ollama non usa alcun riferimento secret.',
  invalid_provider_url: 'Il base URL deve essere http/https, senza credenziali, query o frammenti.',
  invalid_configuration: 'Configurazione provider non valida.',
  invalid_provider_configuration: 'Configurazione provider non valida per il runtime.',
  runtime_error: 'Il runtime ha rifiutato la configurazione del provider.',
  capability_not_supported:
    'Ollama supporta solo chat e streaming: rimuovi i modelli con tool calling o structured output.',
  invalid_model_id: 'Identificativo modello non valido.',
  duplicate_model_id: 'Il catalogo contiene un modello duplicato.',
  provider_models_too_large: 'Il provider ha restituito un elenco modelli troppo grande.',
  egress_denied: 'Il base URL non è consentito dalla policy egress del runtime.',
  provider_unreachable: 'Il provider non è raggiungibile dal runtime.',
  provider_models_failed: 'Il provider ha rifiutato la richiesta di elenco modelli.',
  provider_models_invalid: 'Il provider ha restituito un elenco modelli non valido.',
  provider_pending:
    'Configurazione salvata, ma il runtime non l’ha ancora applicata. Riprova tra poco.',
  version_conflict: 'La configurazione è cambiata nel frattempo: ricarica la pagina e riprova.',
};

function providerMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'code' in error) {
    const message = PROVIDER_MESSAGES[String(error.code)];
    if (message) return message;
  }
  return gatewayMessage(error);
}

function modelInput(model: ProviderConfiguration['models'][number]): ProviderModel {
  return {
    id: model.id,
    capabilities: model.capabilities.filter(
      (capability): capability is ProviderModel['capabilities'][number] =>
        capability === 'tool_calling' || capability === 'structured_output',
    ),
    context_window: model.context_window,
  };
}

function currentModels(provider: ProviderConfiguration): ProviderModel[] {
  return provider.models.map(modelInput);
}

function expectedRevision(data: FormData): string {
  return `"${String(data.get('revision') ?? '0')}"`;
}

function canManage(locals: App.Locals): boolean {
  const principal = locals.session!.principal;
  return (
    principal.role === 'admin' &&
    principal.scopes.includes('providers:read') &&
    principal.scopes.includes('providers:write')
  );
}

function denied() {
  return fail(403, {
    error: 'Serve il ruolo admin con gli scope providers:read e providers:write.',
    discovered: null,
  });
}

function parseContextWindow(raw: FormDataEntryValue | null): number | null | undefined {
  const value = String(raw ?? '').trim();
  if (!value) return null;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) return undefined;
  return parsed;
}

export const load: PageServerLoad = async ({ locals, url }) => {
  const principal = locals.session!.principal;
  const canRead = principal.role === 'admin' && principal.scopes.includes('providers:read');
  if (!canRead) {
    return {
      provider: null,
      principal,
      canManage: false,
      saved: false,
      error: null,
      forbidden: true,
    };
  }
  try {
    return {
      provider: await clientFor(locals.session!.apiKey).provider.get(),
      principal,
      canManage: canManage(locals),
      saved: url.searchParams.get('saved') === '1',
      error: null,
      forbidden: false,
    };
  } catch (error) {
    return {
      provider: null,
      principal,
      canManage: false,
      saved: false,
      error: providerMessage(error),
      forbidden: gatewayStatus(error) === 403,
    };
  }
};

export const actions: Actions = {
  enableToolCalling: async ({ request, locals }) => {
    if (!canManage(locals)) return denied();
    const data = await request.formData();
    const id = String(data.get('model_id') ?? '');
    try {
      const client = clientFor(locals.session!.apiKey);
      const current = await client.provider.get();
      const models = currentModels(current);
      const model = models.find((model) => model.id === id);
      if (current.provider !== 'openai-compatible' || !model) {
        return fail(422, { error: 'Modello non valido per il tool calling.', discovered: null });
      }
      if (!model.capabilities.includes('tool_calling')) model.capabilities.push('tool_calling');
      await client.provider.update({
        provider: current.provider,
        base_url: current.base_url,
        api_key_ref: current.api_key_ref,
        max_output_tokens: current.max_output_tokens,
        models,
      }, { ifMatch: expectedRevision(data) });
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: providerMessage(error), discovered: null,
      });
    }
    throw redirect(303, '/provider?saved=1');
  },
  save: async ({ request, locals }) => {
    if (!canManage(locals)) return denied();
    const data = await request.formData();
    const provider = String(data.get('provider') ?? '');
    const baseUrl = String(data.get('base_url') ?? '').trim();
    const apiKeyRef = String(data.get('api_key_ref') ?? '').trim();
    const maxOutputTokens = Number(data.get('max_output_tokens'));
    if (provider !== 'openai-compatible' && provider !== 'ollama') {
      return fail(422, { error: 'Seleziona un provider valido.', discovered: null });
    }
    if (!baseUrl) {
      return fail(422, { error: 'Inserisci il base URL del provider.', discovered: null });
    }
    if (!Number.isInteger(maxOutputTokens) || maxOutputTokens < 1 || maxOutputTokens > 8192) {
      return fail(422, {
        error: 'Max output tokens deve essere compreso tra 1 e 8192.',
        discovered: null,
      });
    }

    try {
      const client = clientFor(locals.session!.apiKey);
      const current = await client.provider.get();
      const update: ProviderUpdate = {
        provider,
        base_url: baseUrl,
        api_key_ref: provider === 'ollama' ? '' : apiKeyRef,
        max_output_tokens: maxOutputTokens,
        models: currentModels(current),
      };
      if (update.models.length === 0) {
        return fail(422, {
          error: 'Aggiungi almeno un modello prima di cambiare provider.',
          discovered: null,
        });
      }
      await client.provider.update(update, { ifMatch: expectedRevision(data) });
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: providerMessage(error),
        discovered: null,
      });
    }
    throw redirect(303, '/provider?saved=1');
  },

  addModel: async ({ request, locals }) => {
    if (!canManage(locals)) return denied();
    const data = await request.formData();
    const id = String(data.get('model_id') ?? '').trim();
    if (!id || id.length > 200) {
      return fail(422, { error: 'Inserisci un identificativo modello valido.', discovered: null });
    }
    const contextWindow = parseContextWindow(data.get('context_window'));
    if (contextWindow === undefined) {
      return fail(422, {
        error: 'La finestra di contesto deve essere un intero positivo oppure vuota.',
        discovered: null,
      });
    }
    const extras = data
      .getAll('capabilities')
      .map(String)
      .filter((value) => value === 'tool_calling' || value === 'structured_output');

    try {
      const client = clientFor(locals.session!.apiKey);
      const current = await client.provider.get();
      const models = currentModels(current);
      if (models.some((model) => model.id === id)) {
        return fail(422, { error: 'Il modello è già presente.', discovered: null });
      }
      models.push({
        id,
        capabilities:
          current.provider === 'ollama'
            ? []
            : (extras as ProviderModel['capabilities']),
        context_window: contextWindow,
      });
      await client.provider.update(
        {
          provider: current.provider,
          base_url: current.base_url,
          api_key_ref: current.api_key_ref,
          max_output_tokens: current.max_output_tokens,
          models,
        },
        { ifMatch: expectedRevision(data) },
      );
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: providerMessage(error),
        discovered: null,
      });
    }
    throw redirect(303, '/provider?saved=1');
  },

  removeModel: async ({ request, locals }) => {
    if (!canManage(locals)) return denied();
    const data = await request.formData();
    const id = String(data.get('model_id') ?? '');
    try {
      const client = clientFor(locals.session!.apiKey);
      const current = await client.provider.get();
      const models = currentModels(current).filter((model) => model.id !== id);
      if (models.length === 0) {
        return fail(422, {
          error: 'Il provider deve mantenere almeno un modello.',
          discovered: null,
        });
      }
      await client.provider.update(
        {
          provider: current.provider,
          base_url: current.base_url,
          api_key_ref: current.api_key_ref,
          max_output_tokens: current.max_output_tokens,
          models,
        },
        { ifMatch: expectedRevision(data) },
      );
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: providerMessage(error),
        discovered: null,
      });
    }
    throw redirect(303, '/provider?saved=1');
  },

  discover: async ({ locals }) => {
    if (!canManage(locals)) return denied();
    try {
      const client = clientFor(locals.session!.apiKey);
      const current = await client.provider.get();
      const result = await client.provider.discoverModels({
        provider: current.provider,
        base_url: current.base_url,
        api_key_ref: current.api_key_ref,
      });
      return { error: null, discovered: result.models };
    } catch (error) {
      return fail(gatewayStatus(error) ?? 502, {
        error: providerMessage(error),
        discovered: null,
      });
    }
  },
};
