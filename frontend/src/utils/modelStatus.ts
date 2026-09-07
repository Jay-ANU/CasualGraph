export interface ModelConfiguration {
  provider: string;
  model: string;
  configured: boolean;
  modes: Record<'flash' | 'deep', { model: string; configured: boolean; thinking: boolean }>;
}

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

export function modelDisplayName(model: string): string {
  if (model === 'deepseek-v4-pro') return 'DeepSeek V4 Pro';
  if (model === 'deepseek-v4-flash') return 'DeepSeek V4 Flash';
  return model || 'Model not configured';
}
