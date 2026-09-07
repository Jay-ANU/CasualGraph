import { modelDisplayName, parseModelStatus } from './modelStatus';

const valid = {
  provider: 'deepseek', model: 'deepseek-v4-pro', configured: true,
  modes: {
    flash: { model: 'deepseek-v4-pro', configured: true, thinking: false },
    deep: { model: 'deepseek-v4-pro', configured: true, thinking: true },
  },
};

describe('model configuration, never an inferred connection', () => {
  it('accepts explicit false and true configuration states', () => {
    expect(parseModelStatus(valid)?.modes.deep.thinking).toBe(true);
    expect(parseModelStatus({ ...valid, configured: false })?.configured).toBe(false);
  });
  it.each([null, {}, 'HTML fallback', { ...valid, modes: {} }, { ...valid, configured: 'true' }])('rejects malformed status %s', value => {
    expect(parseModelStatus(value)).toBeNull();
  });
  it('labels only known models and preserves explicit overrides', () => {
    expect(modelDisplayName('deepseek-v4-pro')).toBe('DeepSeek V4 Pro');
    expect(modelDisplayName('custom-model')).toBe('custom-model');
    expect(modelDisplayName('')).toBe('Model not configured');
  });
});
