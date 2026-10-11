import { afterEach, describe, expect, it } from 'vitest';
import { legalLookups, toolAction, toolGroups, toolLine, toolOutcome } from './toolCalls';
import { liveActivity, phaseSteps, reviewEvents } from './reviewActivity';
import { availableTiers } from './labels';
import { ReviewReport } from './report';
import { serverText } from './i18n';
import { setCurrentLang } from '../i18n/core';
import type { LiveWriting, Review, ToolCall } from './types';

afterEach(() => setCurrentLang('zh'));

const call = (extra: Partial<ToolCall> = {}): ToolCall => ({ id: 'c1', step: 'review', name: 'search_law', detail: '民法典 违约金 调整', status: 'ok', count: 2, ...extra });
const review = (extra: Partial<Review> = {}): Review => ({ id: 'r1', status: 'completed', stage: '', resumable: false, findings: [], coverage: [], sources: [],
  decisions: {}, policies: [], notice: '合成提示', review_tier: 'ultra_fast', engine: 'chat', ...extra });
const live = (extra: Partial<LiveWriting> = {}): LiveWriting => ({ step: 'review', activity: 'tools', memo: '', written: 0, reasoning: 0, findings: 0, ...extra });

describe('tool calls', () => {
  it('say what the model asked for and what came back, in both languages', () => {
    expect(toolLine(call())).toBe('检索法规：民法典 违约金 调整');
    expect(toolLine(call(), 'en')).toBe('Searched the law: 民法典 违约金 调整');
    expect(toolOutcome(call()).text).toBe('取得 2 个官方来源');
    expect(toolOutcome(call({ count: 1 }), 'en').text).toBe('1 official source');
    expect(toolOutcome(call({ name: 'read_law_article' })).text).toBe('已取得官方原文');
    expect(toolOutcome(call({ name: 'find_in_contract', count: 3 }), 'en').text).toBe('3 paragraphs');
    expect(toolOutcome(call({ name: 'calculate', result: '300000' })).text).toBe('= 300000');
    expect(toolOutcome(call({ name: 'date_calc', count: 59, result: undefined })).text).toBe('相差 59 天');
    expect(toolOutcome(call({ name: 'date_calc', count: 59, result: undefined }), 'en').text).toBe('59 days apart');
    expect(toolOutcome(call({ name: 'check_revision', status: 'issues', problems: ['a', 'b'] }))).toEqual({ text: '未通过 · 2 个问题', tone: 'warn' });
    expect(toolOutcome(call({ status: 'rejected', reason: 'unsafe' }), 'en').text).toBe('not sent: the query named contract details');
    expect(toolOutcome(call({ status: 'rejected', reason: 'invalid' }))).toEqual({ text: '请求无效，未执行', tone: 'muted' });
    expect(toolOutcome(call({ status: 'empty' })).text).toBe('未取得官方原文');
    expect(toolOutcome(call({ name: 'find_in_contract', status: 'empty' })).text).toBe('未找到');
    expect(toolOutcome(call({ status: 'running' })).tone).toBe('running');
    expect(toolOutcome(call({ status: 'limit' })).text).toBe('已达上限，未执行');
    expect(toolAction({ name: 'something_new' }, 'en')).toBe('Called a tool');
  });
  it('count only the legal lookups that ran', () => {
    const calls = [call(), call({ id: 'c2', name: 'read_law_article' }), call({ id: 'c3', status: 'limit' }), call({ id: 'c4', status: 'rejected' }),
      call({ id: 'c5', name: 'calculate' })];
    expect(legalLookups(review({ tool_calls: calls }))).toBe(2);
  });
  it('group a fast review’s calls by the read that made them', () => {
    const calls = [call(), call({ id: 'c2', step: 'final', name: 'check_revision' })];
    expect(toolGroups(review({ review_tier: 'fast', tool_calls: calls })).map(g => [g.label, g.calls.length])).toEqual([['通读初审', 1], ['复读定稿', 1]]);
    expect(toolGroups(review({ review_tier: 'fast', tool_calls: calls }), 'en').map(g => g.label)).toEqual(['First read', 'Re-read']);
    expect(toolGroups(review({ tool_calls: calls })).map(g => g.label)).toEqual(['']);
    expect(toolGroups(review())).toEqual([]);
  });
});

describe('a review whose model calls tools', () => {
  it('has no separate research step: the model researches as it reads', () => {
    expect(phaseSteps(review({ review_tier: 'fast', status: 'running', tools_offered: true })).map(s => s.label)).toEqual(['读取合同', '通读初审', '复读定稿']);
    expect(phaseSteps(review({ review_tier: 'fast', status: 'running' })).map(s => s.id)).toEqual(['intake', 'review', 'retrieval', 'coordination']);
  });
  it('says it is calling tools', () => {
    expect(liveActivity(live())).toBe('正在调用工具');
    expect(liveActivity(live({ tool_count: 3, step: 'final' }))).toBe('复读定稿 · 正在调用工具 · 本轮已调用 3 次');
    expect(liveActivity(live({ tool_count: 1 }), 'en')).toBe('Calling tools · 1 call so far');
  });
  it('logs each call once, as it starts', () => {
    const before = review({ status: 'running', live: live({ tools: [call()] }) });
    const after = review({ status: 'running', live: live({ tools: [call(), call({ id: 'c2', name: 'calculate', detail: '1+1', status: 'running' })] }) });
    expect(reviewEvents(before, after).map(e => e.text)).toEqual(['计算：1+1']);
    expect(reviewEvents(after, after)).toEqual([]);
    const many = review({ status: 'running', live: live({ tools: ['a', 'b', 'c', 'd', 'e'].map(id => call({ id })) }) });
    expect(reviewEvents(review({ status: 'running', live: live() }), many, 'en').map(e => e.text).slice(-1)).toEqual(['2 more tool calls']);
  });
  it('reports the calls and the research the model did itself', () => {
    const calls = [call(), call({ id: 'c2', name: 'calculate', detail: '1000000 * 30%', result: '300000' })];
    const text = ReviewReport(review({ research: { status: 'tools', issues: [] }, tool_calls: calls, tools_offered: true }));
    expect(text).toContain('模型在审查中按需查阅官方法规原文 1 次');
    expect(text).toContain('## 模型调用的工具');
    expect(text).toContain('- 检索法规：民法典 违约金 调整（取得 2 个官方来源）');
    expect(text).toContain('- 计算：1000000 * 30%（= 300000）');
    const english = ReviewReport(review({ research: { status: 'tools', issues: [] }, tool_calls: calls }), 'en');
    expect(english).toContain('- Searched the law: 民法典 违约金 调整 (2 official sources)');
    expect(english).toContain('The model looked up official legal text 1 time as it reviewed');
  });
});

describe('tier wording with tools', () => {
  it('mentions tools only when the service offers them', () => {
    const tiers = { review_tiers: ['ultra_fast', 'fast', 'standard', 'deep'] as const };
    const [ultra, fast] = availableTiers({ review_tiers: [...tiers.review_tiers], chat_tools: true });
    expect(ultra.note).toContain('需要时自己检索法规原文、计算金额和日期');
    expect(fast.note).toContain('边审边按需检索法规原文');
    const [plainUltra] = availableTiers({ review_tiers: [...tiers.review_tiers] });
    expect(plainUltra.note).toContain('不检索法规、不做独立复核');
    const [englishUltra] = availableTiers({ review_tiers: [...tiers.review_tiers], chat_tools: true }, 'en');
    expect(englishUltra.note).toContain('looking up official legal text and working out sums and dates');
  });
  it('translates the new stage and notes', () => {
    setCurrentLang('en');
    expect(serverText('极速审查完成（按需调用工具，未做独立复核），修订稿已就绪，可直接查看、修改并导出'))
      .toBe('Ultra-fast review finished (tools used as needed; no independent verification); your draft is ready to read, edit and export');
    expect(serverText('本档位由模型通读全文、按需调用检索等工具并复读定稿，未做独立复核；你可以修改并导出。')).toContain('calls search and other tools');
    expect(serverText('模型反复调用工具，没有写出审查结果；已保留检查点，可重试。')).toBe('The model kept calling tools without writing the review. Progress is saved; you can retry.');
  });
});
