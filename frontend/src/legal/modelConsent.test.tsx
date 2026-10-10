import { afterEach, describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { setCurrentLang } from '../i18n/core';
import { FollowUp } from './FollowUp';
import { ReleasePanel } from './ReleasePanel';
import { ModelSelect } from './ui';
import { serverText } from './i18n';
import type { Catalog, Contract, ModelProvider, Review } from './types';

const noop = () => undefined;
const contract: Contract = { id: 'c1', matter_id: 'm1', org_id: 'o1', name: 'synthetic.txt', status: 'ready', format: 'txt', revision: 1,
  blocks: [], warnings: [], replacement_count: 0, reviews: [] };
const review = (provider?: ModelProvider): Review => ({
  id: 'r1', status: 'completed', stage: '', resumable: false, findings: [], coverage: [], sources: [], decisions: {}, policies: [], notice: '',
  profile: provider ? { model: { id: provider === 'anthropic' ? 'claude-fixture' : 'glm-fixture', provider } } : {},
});
afterEach(() => setCurrentLang('zh'));

describe('rendered model recipient disclosure', () => {
  for (const provider of ['anthropic', 'ydata'] as const) {
    it(`uses the frozen ${provider} recipient for questions and optional checks`, () => {
      setCurrentLang('en');
      const r = review(provider);
      const question = renderToStaticMarkup(<FollowUp review={r} blocks={[]} answers={[]} question="Synthetic question" busy={false} consent={false}
        onQuestion={noop} onConsent={noop} onAsk={noop} onLocate={noop} />);
      const release = renderToStaticMarkup(<ReleasePanel review={r} contract={contract} open={[]} busy={false}
        onCheck={noop} onReport={noop} onDraft={noop} onBack={noop} />);
      for (const html of [question, release]) {
        expect(html).toContain(provider === 'anthropic' ? 'Anthropic official API' : 'YData gateway');
        expect(html).not.toContain(provider === 'anthropic' ? 'YData' : 'Anthropic');
      }
    });
  }
  it('keeps export available when an older review has no recorded model recipient', () => {
    const html = renderToStaticMarkup(<ReleasePanel review={review()} contract={contract} open={[]} busy={false}
      onCheck={noop} onReport={noop} onDraft={noop} onBack={noop} />);
    const download = html.match(/<button\b[^>]*>导出修订文本<\/button>/)?.[0];
    expect(download).toBeDefined();
    expect(download).not.toContain('disabled');
    expect(html.match(/<button\b[^>]*>开始复核<\/button>/)?.[0]).toContain('disabled');
  });
  it('shows a failed provider while preserving the healthy provider’s model choice', () => {
    setCurrentLang('en');
    const catalog: Catalog = { provider: 'ydata', models: [{ id: 'glm-fixture', family: 'GLM', provider: 'ydata' }],
      families: ['GLM'], default_model: 'glm-fixture', notice: '', unavailable_families: ['Claude'],
      provider_errors: [{ provider: 'anthropic', code: 'anthropic_unauthorized', message: 'Anthropic 拒绝访问，请管理员检查官方密钥及模型权限。' }] };
    const html = renderToStaticMarkup(<ModelSelect catalog={catalog} value="glm-fixture" loading={false} disabled={false} onChange={noop} onRefresh={noop} />);
    expect(html).toContain('Recipient: YData gateway');
    expect(html).toContain('Claude unavailable for now');
    expect(html).toContain('Anthropic refused access. Ask an administrator');
    expect(html.match(/<select\b[^>]*>/)?.[0]).not.toContain('disabled');
  });
  it('translates route-change and official-provider errors without losing the recovery instruction', () => {
    expect(serverText('所选模型的处理方已变化，请重新选择模型并确认外部处理方。', 'en')).toContain('confirm its recipient');
    expect(serverText('本轮模型处理方已变化或尚未授权，请选择模型并新建审查。历史稿件仍可查看和导出。', 'en')).toContain('still read and export');
    expect(serverText('Anthropic 请求失败（HTTP 502）；没有自动切换模型或提供方。', 'en')).toBe('The Anthropic request failed (HTTP 502); no other model or provider was used instead.');
  });
});
