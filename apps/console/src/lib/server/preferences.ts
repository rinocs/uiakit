export const PREFERENCES_COOKIE = 'uai_console_preferences';
export type ConsolePreferences = { theme: 'dark' | 'light' | 'system'; density: 'comfortable' | 'compact' };
const defaults: ConsolePreferences = { theme: 'dark', density: 'comfortable' };

function validate(value: unknown): ConsolePreferences | null {
  if (!value || typeof value !== 'object') return null;
  const { theme, density } = value as Record<string, unknown>;
  if ((theme === 'dark' || theme === 'light' || theme === 'system') &&
      (density === 'comfortable' || density === 'compact')) return { theme, density };
  return null;
}

export function readPreferences(cookie: string | undefined): ConsolePreferences {
  try { return validate(JSON.parse(cookie ?? 'null')) ?? { ...defaults }; }
  catch { return { ...defaults }; }
}

export function preferencesFrom(data: FormData): ConsolePreferences | null {
  return validate({ theme: data.get('theme'), density: data.get('density') });
}
