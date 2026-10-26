import type { AssistantPatch, ExecutionLimits } from '@universal-ai-kit/sdk';

const limitBounds = {
  max_input_chars: [1, 64000], max_output_chars: [1, 64000], duration_seconds: [0, 120],
  max_steps: [0, 16], max_tool_calls: [0, 32], max_tokens: [0, 1_000_000],
} as const;

export function assistantSettingsFrom(data: FormData) {
  const values = {
    description: String(data.get('description') ?? ''),
    tools: [...new Set(data.getAll('tools').map(String))],
    knowledge_base_ids: [...new Set(data.getAll('knowledge_base_ids').map(String))],
    conversation: data.get('conversation') === 'on',
    max_input_chars: String(data.get('max_input_chars') ?? ''),
    max_output_chars: String(data.get('max_output_chars') ?? ''),
    duration_seconds: String(data.get('duration_seconds') ?? ''),
    max_steps: String(data.get('max_steps') ?? ''),
    max_tool_calls: String(data.get('max_tool_calls') ?? ''),
    max_tokens: String(data.get('max_tokens') ?? ''),
  };
  const invalid = (error: string) => ({ values, patch: null, error });
  if (values.description.length > 4000) return invalid('La descrizione può contenere al massimo 4000 caratteri.');
  if (values.tools.length > 64 || values.tools.some((id) => !/^[a-z][a-z0-9_.-]{0,99}$/.test(id))) {
    return invalid('Selezione tool non valida.');
  }
  if (values.knowledge_base_ids.length > 64 || values.knowledge_base_ids.some((id) => !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))) {
    return invalid('Selezione knowledge base non valida.');
  }
  const limits: ExecutionLimits = {};
  for (const key of Object.keys(limitBounds) as Array<keyof typeof limitBounds>) {
    const value = Number(values[key]);
    const [min, max] = limitBounds[key];
    if (!values[key].trim() || !Number.isFinite(value) || value < min || value > max ||
        (key === 'duration_seconds' ? value <= 0 : !Number.isInteger(value))) {
      return invalid(`Limite non valido: ${key}. Rispetta l'intervallo indicato.`);
    }
    limits[key] = value;
  }
  const patch: AssistantPatch = {
    description: values.description, tools: values.tools, knowledge_base_ids: values.knowledge_base_ids,
    memory: { conversation: values.conversation, semantic: false },
    policy: { require_tool_approval: true }, limits,
  };
  return { values, patch, error: null };
}
