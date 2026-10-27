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
      return `Gateway ${String(error.status)}: ${String(error.code)}`;
    }
    if ('message' in error && typeof error.message === 'string') {
      return error.message;
    }
  }
  return 'Gateway non raggiungibile.';
}
