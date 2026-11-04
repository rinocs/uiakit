import { env } from '$env/dynamic/private';
import { UniversalAIKit } from '@universal-ai-kit/sdk';
import type { SessionPrincipal } from './session';

export function gatewayUrl(): string {
  return (env.UAI_GATEWAY_URL || 'http://gateway:8080').replace(/\/+$/, '');
}

export function clientFor(apiKey: string): UniversalAIKit {
  return new UniversalAIKit({ baseUrl: gatewayUrl(), apiKey });
}

export async function principalFor(apiKey: string): Promise<SessionPrincipal> {
  const principal = await clientFor(apiKey).me();
  return {
    principal_id: principal.principal_id,
    role: principal.role,
    scopes: principal.scopes,
  };
}

export function gatewayStatus(error: unknown): number | null {
  if (error && typeof error === 'object' && 'status' in error) {
    const status = Number(error.status);
    if (Number.isInteger(status) && status >= 400 && status < 600) return status;
  }
  return null;
}

export function gatewayMessage(error: unknown): string {
  if (error && typeof error === 'object') {
    if ('status' in error && 'code' in error) {
      if (error.code === 'tool_calling_unsupported') {
        return 'Il modello non è abilitato al tool calling. Abilitalo nella pagina Provider oppure rimuovi i tool dall’assistente.';
      }
      if (error.code === 'structured_output_unsupported') {
        return 'Il modello non supporta l’output strutturato. Aggiorna le capacità nella pagina Provider oppure rimuovi lo schema dall’assistente.';
      }
      return `Gateway ${String(error.status)}: ${String(error.code)}`;
    }
    if ('message' in error && typeof error.message === 'string') {
      return error.message;
    }
  }
  return 'Gateway non raggiungibile.';
}
