import { afterEach, describe, expect, it } from 'vitest';
import { liveActivity, phaseDetail, phaseSteps, reviewPercent, reviewPhase } from './reviewActivity';
import { availableTiers } from './labels';
import { linkParagraphs } from './text';
import { ReviewReport } from './report';
import { serverText } from './i18n';
import { setCurrentLang } from '../i18n/core';
import type { LiveWriting, Review } from './types';

afterEach(() => setCurrentLang('zh'));

const review = (extra: Partial<Review> = {}): Review => ({ id: 'r1', status: 'running', stage: '', resumable: false, findings: [], coverage: [], sources: [],
  decisions: {}, policies: [], notice: '合成提示', review_tier: 'ultra_fast', engine: 'chat', ...extra });
const live = (extra: Partial<LiveWriting> = {}): LiveWriting => ({ step: 'review', activity: 'writing_memo', memo: '## 一、交易概况', written: 0, reasoning: 0, findings: 0, ...extra });

describe('chat-style review progress', () => {
  it('runs the steps a chat review has: one answer, or read, research and re-read', () => {
    expect(phaseSteps(review()).map(s => s.id)).toEqual(['intake', 'review']);
    expect(phaseSteps(review({ review_tier: 'fast' })).map(s => s.id)).toEqual(['intake', 'review', 'retrieval', 'coordination']);
    expect(reviewPhase(review({ review_tier: 'fast', progress: { phase: 'finalize', completed: 1, total: 2 } }))).toBe('coordination');
    expect(reviewPhase(review({ progress: { phase: 'review', completed: 0, total: 1 } }))).toBe('review');
  });
  it('moves the bar with the length of what the model has written and keeps each step in its band', () => {
    const at = (written: number, extra: Partial<Review> = {}) => reviewPercent(review({ progress: { phase: 'review', completed: 0, total: 1 }, live: live({ written }), ...extra }));
    expect(at(0)).toBe(5);
    expect(at(4000)).toBeGreaterThan(at(1000));
    expect(at(200000)).toBeLessThanOrEqual(95);
    const fast = { review_tier: 'fast' as const };
    expect(at(200000, fast)).toBeLessThanOrEqual(45);
    const rereading = reviewPercent(review({ ...fast, progress: { phase: 'finalize', completed: 1, total: 2 }, live: live({ step: 'final', written: 100 }) }));
    expect(rereading).toBeGreaterThan(55);
    expect(rereading).toBeLessThan(97);
    expect(reviewPercent(review({ ...fast, progress: { phase: 'retrieval', completed: 0, total: 3 } }))).toBe(46);
  });
  it('says what the model is doing in both languages', () => {
    expect(liveActivity(live({ activity: 'thinking' }))).toBe('模型正在通读合同');
    expect(liveActivity(live({ activity: 'thinking', reasoning: 1200 }))).toBe('模型正在思考 · 已思考 1200 字');
    expect(liveActivity(live({ written: 860 }))).toBe('正在撰写审查意见书 · 已写 860 字');
    expect(liveActivity(live({ activity: 'writing_result', findings: 7, step: 'final' }))).toBe('复读定稿 · 正在逐条写出修改 · 已写 7 条');
    expect(liveActivity(live({ activity: 'searching', step: 'research' }), 'en')).toBe('Searching official legal sources');
    expect(liveActivity(live({ activity: 'writing_result', findings: 1 }), 'en')).toBe('Writing the edits · 1 finding so far');
    expect(phaseDetail(review({ progress: { phase: 'review', completed: 0, total: 1 }, live: live({ written: 12 }) }))).toBe('正在撰写审查意见书 · 已写 12 字');
  });
});

describe('the review memo', () => {
  it('links the paragraphs the model cites, and only those of this contract', () => {
    const ids = new Set(['p1', 'p5']);
    expect(linkParagraphs('付款条款（p5）与P1冲突；p9 不存在。', ids)).toBe('付款条款（[p5](#paragraph-p5)）与[P1](#paragraph-p1)冲突；p9 不存在。');
    expect(linkParagraphs('见 [p5](#paragraph-p5) 与 http://x.test/p5 和 step5', ids)).toBe('见 [p5](#paragraph-p5) 与 http://x.test/p5 和 step5');
  });
  it('leads the exported report, one heading level down and escaped', () => {
    const text = ReviewReport(review({ status: 'completed', memo: '## 一、总体评价\n存在<高风险>条款。' }));
    expect(text).toContain('## 审查意见书（模型撰写，未经独立复核）');
    expect(text).toContain('### 一、总体评价\n存在&lt;高风险&gt;条款。');
    expect(text.indexOf('## 审查意见书')).toBeLessThan(text.indexOf('\n## 审查意见\n'));
  });
  it('explains research that was not run because no search service is configured', () => {
    const text = ReviewReport(review({ status: 'completed', review_tier: 'fast', research: { status: 'skipped', issues: [], reason: 'not_configured' } }));
    expect(text).toContain('未配置法规检索服务，本轮没有检索');
  });
});

describe('chat review wording', () => {
  it('describes the speed tiers as a chat-style review', () => {
    const [ultra, fast] = availableTiers({ review_tiers: ['ultra_fast', 'fast', 'standard', 'deep'] });
    expect(ultra.note).toContain('像在 AI 对话里上传合同');
    expect(fast.note).toContain('再复读全文自查定稿');
  });
  it('translates the engine’s stages, steps and messages', () => {
    setCurrentLang('en');
    expect(serverText('快速审查完成（已复读定稿，未做独立复核），修订稿已就绪，可直接查看、修改并导出'))
      .toBe('Fast review finished (re-read before finalising; no independent verification); your draft is ready to read, edit and export');
    expect(serverText('正在复读合同全文并定稿')).toBe('Re-reading the whole contract and finalising the review');
    expect(serverText('复读定稿')).toBe('Re-read and finalise');
    expect(serverText('全文通读与清单外问题')).toBe('Whole-contract read and other issues');
    expect(serverText('2 条模型意见格式不完整，未能采用；可新建审查重新生成。'))
      .toBe('2 model findings were incomplete and could not be used; start a new review to generate them again.');
    expect(serverText('模型的结构化结果多次无法读取（JSON 格式错误（x）），可重试。'))
      .toBe('The model’s structured result could not be read after several attempts. You can retry.');
  });
});
