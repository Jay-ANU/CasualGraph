import { currentLang, pick, type Lang } from '../i18n/core';
import type { Catalog, ModelProvider, Review } from './types';

type ModelRoute = { id: string; provider?: string };

/** Only the server's model row or frozen review profile can name the recipient. */
export function processingProvider(model?: ModelRoute | null): ModelProvider | null {
  return model?.provider === 'anthropic' || model?.provider === 'ydata' ? model.provider : null;
}

export const selectedModel = (catalog: Catalog | null, id: string) => catalog?.models.find(model => model.id === id);

export function modelRouteKey(model?: ModelRoute | null): string {
  const provider = processingProvider(model);
  return model?.id && provider ? JSON.stringify([model.id, provider]) : '';
}

export function reviewRouteKey(review: Review | null): string {
  const key = modelRouteKey(review?.profile?.model);
  return review && key ? `${review.id}:${key}` : '';
}

/** A refresh can change the recipient without changing the visible model identifier. */
export function refreshedModelSelection(previous: Catalog | null, catalog: Catalog, modelId: string, consent: boolean) {
  const nextId = selectedModel(catalog, modelId)?.id || selectedModel(catalog, catalog.default_model)?.id || catalog.models[0]?.id || '';
  const previousKey = modelRouteKey(selectedModel(previous, modelId));
  const nextKey = modelRouteKey(selectedModel(catalog, nextId));
  return { modelId: nextId, consent: Boolean(consent && nextKey && nextKey === previousKey) };
}

export function providerLabel(provider: ModelProvider | null, lang: Lang = currentLang()): string {
  return provider === 'anthropic' ? pick('Anthropic 官方 API', 'Anthropic official API', lang)
    : provider === 'ydata' ? pick('YData 网关', 'YData gateway', lang)
    : pick('处理方未确认', 'Recipient not confirmed', lang);
}

export function processingConsent(action: 'review' | 'check' | 'question', provider: ModelProvider | null, lang: Lang = currentLang()): string {
  if (!provider) return pick('处理方尚未确认，请刷新模型列表并重新选择。', 'The recipient is not confirmed. Refresh the model list and choose again.', lang);
  if (action === 'review') return provider === 'anthropic'
    ? pick('同意将脱敏后的合同文本、审查重点及适用的公司规范提交 Anthropic 官方 API，由所选 Claude 模型分析',
      'I agree to send the redacted contract, my review focus and the applicable company policies to the selected Claude model through the Anthropic official API', lang)
    : pick('同意将脱敏后的合同文本、审查重点及适用的公司规范经 YData 网关提交所选模型分析',
      'I agree to send the redacted contract, my review focus and the applicable company policies to the selected model through the YData gateway', lang);
  if (action === 'check') return provider === 'anthropic'
    ? pick('同意将当前修改（脱敏）提交 Anthropic 官方 API，由原审查模型复核',
      'I agree to send the current edits (redacted) to the review model through the Anthropic official API', lang)
    : pick('同意将当前修改（脱敏）经 YData 网关提交原审查模型复核',
      'I agree to send the current edits (redacted) to the review model through the YData gateway', lang);
  return provider === 'anthropic'
    ? pick('同意将问题及脱敏材料提交 Anthropic 官方 API，由原审查模型回答',
      'I agree to send my question and the redacted material to the review model through the Anthropic official API', lang)
    : pick('同意将问题及脱敏材料经 YData 网关提交原审查模型回答',
      'I agree to send my question and the redacted material to the review model through the YData gateway', lang);
}
