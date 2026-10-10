import { describe, expect, it } from 'vitest';
import { modelRouteKey, processingConsent, processingProvider, providerLabel, refreshedModelSelection, reviewRouteKey, selectedModel } from './modelProcessing';
import type { Catalog, Model, Review } from './types';

const claude: Model = { id: 'claude-fixture', family: 'Claude', provider: 'anthropic' };
const glm: Model = { id: 'glm-fixture', family: 'GLM', provider: 'ydata' };
const catalog = (models: Model[] = [claude, glm], extra: Partial<Catalog> = {}): Catalog => ({
  models, families: ['Claude', 'GLM'], provider: 'mixed', default_model: claude.id, notice: '', ...extra,
});
const review = (provider?: string): Review => ({
  id: 'r1', status: 'completed', stage: '', resumable: false, findings: [], coverage: [], sources: [], decisions: {}, policies: [], notice: '',
  profile: provider ? { model: { id: claude.id, provider } } : {},
});

describe('model processing recipient', () => {
  it('uses each catalogue row, never the aggregate gateway or the model name', () => {
    const mixed = catalog();
    expect(processingProvider(selectedModel(mixed, claude.id))).toBe('anthropic');
    expect(processingProvider(selectedModel(mixed, glm.id))).toBe('ydata');
    expect(processingProvider({ id: claude.id, provider: 'ydata' })).toBe('ydata');
    expect(processingProvider({ id: claude.id })).toBeNull();
    expect(processingProvider({ id: claude.id, provider: 'mixed' })).toBeNull();
    expect(processingProvider(selectedModel(mixed, 'missing'))).toBeNull();
  });
  it('retains consent only when the selected model and actual recipient are unchanged', () => {
    const current = catalog();
    expect(refreshedModelSelection(current, catalog([claude, glm], { default_model: glm.id }), claude.id, true))
      .toEqual({ modelId: claude.id, consent: true });
    expect(refreshedModelSelection(current, current, claude.id, false).consent).toBe(false);
    const rerouted = catalog([{ ...claude, provider: 'ydata' }, glm]);
    expect(refreshedModelSelection(current, rerouted, claude.id, true)).toEqual({ modelId: claude.id, consent: false });
    expect(refreshedModelSelection(rerouted, current, claude.id, true).consent).toBe(false);
  });
  it('withdraws consent when the selected model disappears or has no verified recipient', () => {
    const current = catalog();
    expect(refreshedModelSelection(current, catalog([glm], { default_model: glm.id }), claude.id, true))
      .toEqual({ modelId: glm.id, consent: false });
    expect(refreshedModelSelection(current, catalog([]), claude.id, true)).toEqual({ modelId: '', consent: false });
    expect(refreshedModelSelection(null, current, claude.id, true).consent).toBe(false);
    const unversioned = catalog([{ id: claude.id, family: 'Claude' } as Model]);
    expect(refreshedModelSelection(current, unversioned, claude.id, true).consent).toBe(false);
  });
  it('binds follow-up and optional-check consent to the frozen review recipient and review id', () => {
    expect(reviewRouteKey(review('anthropic'))).not.toBe(reviewRouteKey(review('ydata')));
    expect(reviewRouteKey(review('anthropic'))).not.toBe(reviewRouteKey({ ...review('anthropic'), id: 'r2' }));
    expect(reviewRouteKey(review('anthropic'))).toContain(modelRouteKey(claude));
    expect(reviewRouteKey(review())).toBe('');
    expect(reviewRouteKey(review('unknown'))).toBe('');
  });
});

describe('recipient disclosure in both languages', () => {
  for (const lang of ['zh', 'en'] as const) {
    it(`names the actual recipient in every ${lang} consent`, () => {
      for (const action of ['review', 'check', 'question'] as const) {
        const official = processingConsent(action, 'anthropic', lang);
        const ydata = processingConsent(action, 'ydata', lang);
        expect(official).toContain(providerLabel('anthropic', lang));
        expect(official).not.toContain('YData');
        expect(ydata).toContain(providerLabel('ydata', lang));
        expect(ydata).not.toContain('Anthropic');
      }
      expect(processingConsent('review', null, lang)).toContain(lang === 'zh' ? '处理方尚未确认' : 'recipient is not confirmed');
      expect(providerLabel(null, lang)).toBe(lang === 'zh' ? '处理方未确认' : 'Recipient not confirmed');
    });
  }
});
