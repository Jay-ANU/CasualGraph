import type { ModelConfiguration } from '../types/api';

export function parseModelStatus(value: unknown): ModelConfiguration | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as ModelConfiguration;
  if (typeof data.provider !== 'string' || typeof data.model !== 'string' || typeof data.configured !== 'boolean') return null;
  for (const tier of ['flash', 'deep'] as const) {
    const mode = data.modes?.[tier];
    if (!mode || typeof mode.model !== 'string' || typeof mode.configured !== 'boolean' || typeof mode.thinking !== 'boolean') return null;
  }
  return data;
}

// Model ids start with the family name; ids from other families are shown as configured.
const MODEL_FAMILIES = new Map([
  ['claude', 'Claude'],
  ['deepseek', 'DeepSeek'],
  ['gemini', 'Gemini'],
  ['glm', 'GLM'],
  ['gpt', 'GPT'],
  ['kimi', 'Kimi'],
  ['qwen', 'Qwen'],
]);

const formatModelIdPart = (part: string) => {
  if (/^v\d/i.test(part)) return `V${part.slice(1)}`;
  return /^\d/.test(part) ? part : `${part.charAt(0).toUpperCase()}${part.slice(1)}`;
};

/** "deepseek-v4-pro" -> "DeepSeek V4 Pro", "claude-sonnet-4-5-20250929" -> "Claude Sonnet 4.5". */
export function modelDisplayName(model: string): string {
  const id = String(model || '').trim();
  if (!id) return 'Model not configured';
  const [family, ...rest] = id.split('-').filter(Boolean);
  const familyName = MODEL_FAMILIES.get((family || '').toLowerCase());
  if (!familyName || rest.length === 0) return id;
  const words: string[] = [];
  for (const part of rest) {
    if (/^\d{8}$/.test(part)) continue; // release date stamp
    const previous = words[words.length - 1];
    if (/^\d+$/.test(part) && previous && /^\d+(\.\d+)*$/.test(previous)) {
      words[words.length - 1] = `${previous}.${part}`; // "4-5" is version 4.5
    } else {
      words.push(formatModelIdPart(part));
    }
  }
  return [familyName, ...words].join(' ');
}
