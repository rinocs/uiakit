import type { App } from '$app/types';

export function canManage(locals: App.Locals): boolean {
  const principal = locals.session!.principal;
  return (
    principal.role === 'admin' &&
    principal.scopes.includes('providers:read') &&
    principal.scopes.includes('providers:write')
  );
}

export function denied() {
  return null;
}

export const PROVIDER_MESSAGES: Record<string, string> = {
  profile_in_use:
    'Questo provider è usato da almeno un assistente: aggiorna quegli assistenti prima di eliminarlo.',
  not_found: 'Provider non trovato.',
  invalid_profile_id: 'Identificativo provider non valido.',
  too_many_profiles: 'Troppi provider configurati.',
  secret_key_unavailable:
    'Imposta UAI_SECRET_KEY nel gateway per salvare le chiavi dalla console.',
  secret_unreadable: 'La chiave non è leggibile: reinseriscila.',
  secret_value_invalid: 'Valore secret non valido.',
  invalid_configuration: 'Configurazione provider non valida.',
  model_in_use:
    'Il modello è usato da almeno un assistente. Aggiorna quegli assistenti prima di rimuoverlo.',
  version_conflict: 'La configurazione è cambiata nel frattempo: ricarica la pagina e riprova.',
};

export function providerMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'code' in error) {
    const message = PROVIDER_MESSAGES[String((error as { code: unknown }).code)];
    if (message) return message;
  }
  return 'Errore imprevisto.';
}
