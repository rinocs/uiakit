import { describe, expect, it } from 'vitest';
import { readPreferences, preferencesFrom } from '../src/lib/server/preferences';
import { assistantSettingsFrom } from '../src/lib/server/assistant-settings';

function form(values: Record<string, string | string[]>) {
  const result = new FormData();
  for (const [key, value] of Object.entries(values)) {
    for (const item of Array.isArray(value) ? value : [value]) result.append(key, item);
  }
  return result;
}
const valid = {
  description: 'Supporto', tools: ['example.lookup'], knowledge_base_ids: ['00000000-0000-4000-8000-0000000000b1'],
  conversation: 'on', max_input_chars: '64000', max_output_chars: '32000', duration_seconds: '30.5',
  max_steps: '0', max_tool_calls: '0', max_tokens: '0',
};

describe('console preferences', () => {
  it('rejects malformed or unrecognized persisted preferences', () => {
    for (const value of [undefined, '{', 'null', '{"theme":"purple","density":"compact"}']) {
      expect(readPreferences(value)).toEqual({ theme: 'dark', density: 'comfortable' });
    }
    expect(readPreferences('{"theme":"system","density":"compact"}')).toEqual({ theme: 'system', density: 'compact' });
    expect(preferencesFrom(form({ theme: 'light', density: 'comfortable' }))).toEqual({ theme: 'light', density: 'comfortable' });
    expect(preferencesFrom(form({ theme: 'dark', density: 'invalid' }))).toBeNull();
  });
});

describe('assistant operational settings', () => {
  it('keeps zero budget semantics, resource selections and mandatory approval', () => {
    const result = assistantSettingsFrom(form(valid));
    expect(result.error).toBeNull();
    expect(result.patch).toEqual({
      description: 'Supporto', tools: ['example.lookup'], knowledge_base_ids: ['00000000-0000-4000-8000-0000000000b1'],
      memory: { conversation: true, semantic: false }, policy: { require_tool_approval: true },
      limits: { max_input_chars: 64000, max_output_chars: 32000, duration_seconds: 30.5, max_steps: 0, max_tool_calls: 0, max_tokens: 0 },
    });
  });
  it('rejects missing, nonfinite, fractional or out-of-range limits without losing entered values', () => {
    for (const [key, value] of [['max_steps', '17'], ['max_tokens', '1.5'], ['duration_seconds', 'Infinity'], ['max_input_chars', ''], ['max_tool_calls', '-1']]) {
      const result = assistantSettingsFrom(form({ ...valid, [key]: value }));
      expect(result.error).toBeTruthy();
      expect(result.values[key as keyof typeof result.values]).toEqual(value);
    }
    expect(assistantSettingsFrom(new FormData()).error).toBeTruthy();
  });
  it('rejects invalid resources and ignores forged policy or semantic memory fields', () => {
    expect(assistantSettingsFrom(form({ ...valid, tools: ['bad tool'] })).error).toBeTruthy();
    expect(assistantSettingsFrom(form({ ...valid, knowledge_base_ids: ['invalid'] })).error).toBeTruthy();
    const result = assistantSettingsFrom(form({ ...valid, conversation: '', semantic: 'on', require_tool_approval: 'false' }));
    expect(result.patch?.memory).toEqual({ conversation: false, semantic: false });
    expect(result.patch?.policy).toEqual({ require_tool_approval: true });
  });
});
