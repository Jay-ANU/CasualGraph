import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setCurrentLang } from '../i18n/core';
import { uploadIssue } from './deskLogic';
import { revisionState } from './findingStatus';
import { availableTiers, contractStatusLabel, coverageStatusLabel, failedSteps, formatDate, kindLabel, reviewStatusLabel, tierLabel, toneLabel } from './labels';
import { ReviewReport } from './report';
import { agentLine, phaseDetail, phaseSteps, remainingLabel, reviewEvents } from './reviewActivity';
import { sourceKindLabel } from './sourceLabels';
import { clauseLabel } from './text';
import { clauseOutline, placeLabel, stepLabels } from './workspace';
import type { Block, Collaboration, Finding, Review } from './types';

const finding = (id: string, extra: Partial<Finding> = {}): Finding => ({ id, block_id: 'p1', original_quote: '合成原文', title: '签约即付清全款', kind: 'commercial',
  severity: 'high', impact: '预付风险', reason: '交付时间未约定', suggested_text: '合成修改', evidence_status: 'not_applicable', missing_facts: [], citations: [],
  policy_ids: [], verification_status: 'supported', ...extra });
const review = (extra: Partial<Review> = {}): Review => ({ id: 'r1', status: 'running', stage: '', resumable: false, findings: [], coverage: [], sources: [],
  decisions: {}, policies: [], notice: '', ...extra });
type AgentState = [status: string, completed: number, note?: string];
const team = (legal: AgentState, commercial: AgentState, critic: AgentState): Collaboration => ({
  version: 1, max_parallel: 3, call_budget: 40, agents: [
    { id: 'legal', title: '法律风险审查', status: legal[0], completed: legal[1], total: 2, note: legal[2] || '' },
    { id: 'commercial', title: '公司利益审查', status: commercial[0], completed: commercial[1], total: 2, note: commercial[2] || '' },
    { id: 'policy', title: '公司规范审查', status: 'not_applicable', completed: 0, total: 0, note: '本轮没有适用的公司规范。' },
    { id: 'critic', title: '证据与覆盖复核', status: critic[0], completed: critic[1], total: 4, note: critic[2] || '' },
    { id: 'arbiter', title: '全文协调与冲突检查', status: 'pending', completed: 0, total: 1, note: '' },
  ] });
const block = (id: string, text: string): Block => ({ id, text, page: null });

// Every test here runs in the English interface and switches back to the Chinese default afterwards.
beforeEach(() => setCurrentLang('en'));
afterEach(() => setCurrentLang('zh'));

describe('English tiers and steps', () => {
  it('names the review tiers and what each leaves out', () => {
    const tiers = availableTiers({ review_tiers: ['ultra_fast', 'fast', 'standard', 'deep'] });
    expect(tiers.map(t => t.title)).toEqual(['Ultra-fast', 'Fast', 'Standard', 'Deep']);
    expect(tiers[0].note).toContain('No legal research and no independent verification');
    expect(['ultra_fast', 'fast', 'standard', 'deep'].map(t => tierLabel(t as never))).toEqual(['Ultra-fast review', 'Fast review', 'Standard review', 'Deep review']);
    // The value sent to the API never changes with the language.
    expect(tiers.map(t => t.value)).toEqual(['ultra_fast', 'fast', 'standard', 'deep']);
  });
  it('labels the stepper and the live phases', () => {
    expect(stepLabels()).toEqual(['Redact', 'Set up', 'Review', 'Resolve', 'Export']);
    expect(stepLabels('zh')).toEqual(['脱敏', '设置', '审查', '处理', '导出']);
    expect(phaseSteps(review({ review_tier: 'ultra_fast' })).map(s => s.label)).toEqual(['Read', 'Review']);
    expect(phaseSteps(review({ review_tier: 'fast' })).map(s => s.label)).toEqual(['Read', 'Review', 'Verify']);
    expect(phaseSteps(review({ review_tier: 'deep' })).map(s => s.label)).toEqual(['Read', 'Research', 'Review', 'Finalise']);
  });
  it('states progress counts and time left', () => {
    expect(phaseDetail(review({ progress: { phase: 'collaboration', completed: 1, total: 5 }, collaboration: team(['running', 1], ['running', 0], ['running', 1]) })))
      .toBe('Reviewing · 1/4 done');
    expect(phaseDetail(review({ progress: { phase: 'verification', completed: 1, total: 4 } }))).toBe('Reviewing · group 2/4');
    expect(phaseDetail(review({ status: 'queued' }))).toBe('Waiting to start');
    expect(remainingLabel(300)).toBe('~5 min');
    expect(remainingLabel(40)).toBe('Almost done');
  });
});

describe('English live activity', () => {
  const before = review({ progress: { phase: 'collaboration', completed: 0, total: 5 }, stage: '多个审查 Agent 正在分别检查合同',
    collaboration: team(['running', 0, '第 1/2 项：交付、验收与付款'], ['pending', 0], ['pending', 0]) });
  const after = review({ progress: { phase: 'collaboration', completed: 1, total: 5 }, stage: '多个审查 Agent 正在分别检查合同',
    collaboration: team(['running', 1, '第 2/2 项：违约、赔偿与免责'], ['running', 0, '第 1/2 项：交付、验收与付款'], ['running', 1, '复核法律风险审查：交付、验收与付款']),
    findings: [finding('f1')] });
  it('writes feed lines in English and keeps the model’s finding titles as written', () => {
    expect(reviewEvents(before, after).map(e => e.text)).toEqual([
      'Legal risk review finished item 1/2',
      'Legal risk review · Item 2/2: Breach, damages and exclusions',
      'Commercial interest review started',
      'Commercial interest review · Item 1/2: Delivery, acceptance and payment',
      'Evidence and coverage check started',
      'Evidence and coverage check finished item 1/4',
      'Verifying Legal risk review: Delivery, acceptance and payment',
      'New high-risk finding: 签约即付清全款',
    ]);
  });
  it('can still write the Chinese feed for a language switch', () => {
    expect(reviewEvents(before, after, 'zh').map(e => e.text)).toEqual([
      '法律风险审查完成第 1/2 项', '法律风险审查 · 第 2/2 项：违约、赔偿与免责', '公司利益审查开始工作', '公司利益审查 · 第 1/2 项：交付、验收与付款',
      '证据与覆盖复核开始工作', '证据与覆盖复核完成第 1/4 项', '复核法律风险审查：交付、验收与付款', '发现高风险意见：签约即付清全款',
    ]);
  });
  it('summarises bursts, translates stage changes and agent lines', () => {
    const many = ['a', 'b', 'c', 'd'].map(id => finding(id, { severity: 'medium', title: '付款保障' }));
    expect(reviewEvents(review(), review({ findings: many })).map(e => e.text)).toEqual(['New medium-risk finding: 付款保障', 'New medium-risk finding: 付款保障', '2 more new findings']);
    expect(reviewEvents(review({ stage: '等待执行' }), review({ stage: '正在读取合同并分项审查' }))).toEqual([{ text: 'Reading the contract and reviewing it item by item', tone: 'ink' }]);
    const [legal, , policy, critic, arbiter] = team(['running', 1], ['pending', 0], ['pending', 0]).agents;
    expect(agentLine(legal)).toBe('Reviewing item 2/2');
    expect(agentLine(policy)).toBe('No company policy applies this round.');
    expect(agentLine(critic)).toBe('Verifies each item as it finishes');
    expect(agentLine(arbiter)).toBe('Starts after the item reviews');
    expect(agentLine({ ...critic, status: 'running', completed: 3 })).toBe('Verified 3/4');
    expect(agentLine({ ...legal, status: 'partial' })).toBe('Partly done 1/2');
  });
});

describe('English finding and review status labels', () => {
  it('names tones, kinds and statuses, and falls back to the raw value when unknown', () => {
    expect((['high', 'mid', 'low', 'unconfirmed', 'excluded'] as const).map(t => toneLabel(t))).toEqual(['High risk', 'Medium risk', 'Advisory', 'To verify', 'Excluded']);
    expect(kindLabel('company_policy')).toBe('Company policy');
    expect(kindLabel('other')).toBeUndefined();
    expect(contractStatusLabel('redaction_pending')).toBe('Redaction pending');
    expect(contractStatusLabel('archived')).toBe('archived');
    expect(coverageStatusLabel('needs_information')).toBe('Needs information');
    expect(reviewStatusLabel(review({ status: 'completed', review_tier: 'ultra_fast' }))).toBe('Unverified');
    expect(reviewStatusLabel(review({ status: 'partial', retrieval: [{ rule_id: 'i1', status: 'no_verified_source', provider: 'bing_rss', warnings: [] }] }))).toBe('Basis to verify');
    expect(reviewStatusLabel(review({ status: 'completed' }), 'zh')).toBe('待复核');
  });
  it('explains why a revision cannot be saved yet', () => {
    const base = { done: true, busy: false, original: '甲方应在验收后90日内付款。', legalBasis: false, manual: false };
    const unconfirmed = finding('f', { suggested_text: '甲方应在验收后60日内付款。', verification_status: 'uncertain' });
    expect(revisionState(unconfirmed, { ...base, text: unconfirmed.suggested_text }).issue).toBe('Confirm saving this as a manual revision.');
    const legal = finding('l', { kind: 'legal', suggested_text: '甲方应在验收后60日内付款。', revision_allowed: true, evidence_status: 'model_cited' });
    expect(revisionState(legal, { ...base, text: legal.suggested_text }).issue).toBe('First confirm you have checked the version and applicability of the law.');
    expect(revisionState(legal, { ...base, text: legal.suggested_text }, 'zh').issue).toBe('请先确认已核对法规版本及适用性。');
  });
  it('names unfinished steps from the service and from older reviews', () => {
    const named = review({ status: 'partial', batch_errors: { '2': '此步骤尚未完成。' },
      step_errors: [{ id: '2', title: '分项审查：违约、赔偿与免责；期限、续约与退出', code: 'not_finished', message: '此步骤尚未完成。' }] });
    expect(failedSteps(named)).toEqual([{ id: '2', title: 'Item review: Breach, damages and exclusions; Term, renewal and exit', code: 'not_finished', message: 'This step did not finish.' }]);
    expect(failedSteps(review({ batch_errors: { cross_check: '超时', research: '失败', '3': '中断' } })).map(s => s.title))
      .toEqual(['Item review', 'Edit compatibility check', 'Legal research planning']);
  });
});

describe('English places, sources, dates and upload checks', () => {
  it('names where a finding sits; contract headings stay as written', () => {
    const outline = clauseOutline([block('p0', '甲方：【脱敏1】'), block('p1', '第一条 标的'), block('p2', '2.1 付款安排\n预付。')]);
    expect(outline[0]).toMatchObject({ no: 'Preamble', name: 'Parties', kind: 'preamble' });
    expect(['p0', 'p1', 'p2', null].map(id => placeLabel(outline, id))).toEqual(['Preamble', '第一条', '2.1 付款安排', 'Whole contract']);
    const plain = clauseOutline([block('a', '双方同意如下'), block('b', '价款为合同附件所列')]);
    expect(placeLabel(plain, 'b')).toBe('Paragraph 2');
    expect(clauseLabel(block('p9', '   '))).toBe('Paragraph p9');
  });
  it('labels sources and dates', () => {
    const source = { id: 's', title: '民法典', url: 'https://example.com', retrieved_at: '2025-01-01', text: '', version_status: '' };
    expect(sourceKindLabel({ ...source, source_kind: 'commentary' })).toBe('Commentary or Q&A');
    expect(sourceKindLabel(source)).toBe('Type to verify');
    const noon = Date.UTC(2020, 2, 5, 12);
    expect(formatDate(noon)).toBe('5 Mar 2020');
    expect(formatDate(noon, 'zh')).toBe('2020年3月5日');
  });
  it('checks uploads in English, and in Chinese for the message the desk keeps', () => {
    expect(uploadIssue({ name: '合同.doc', size: 100 })).toBe('Only DOCX, text-based PDF and TXT files are supported. Save .doc files as .docx.');
    expect(uploadIssue({ name: '合同.txt', size: 0 })).toBe('The file is empty.');
    expect(uploadIssue({ name: '合同.txt', size: 10 * 1024 * 1024 + 1 })).toBe('The file is over the 10 MB limit.');
    expect(uploadIssue({ name: '合同.txt', size: 0 }, 'zh')).toBe('文件内容为空。');
  });
});

describe('English report', () => {
  it('translates the report’s labels and keeps the review’s own content', () => {
    const text = ReviewReport(review({ status: 'completed', review_tier: 'ultra_fast', notice: '合成提示', findings: [finding('f1', { verification_status: 'skipped', title: '合成风险' })],
      research: { status: 'skipped', issues: [] }, skills: [{ id: 'review-method', name: '合同审查方法', version: '1.0.0', reason: '通用审查方法' }] }));
    expect(text).toContain('# Contract review report');
    expect(text).toContain('Review depth: Ultra-fast review');
    expect(text).toContain('Contract review method (v1.0.0): General review method');
    expect(text).toContain('### 1. 合成风险');
    expect(text).toContain('risk level: High risk (not verified)');
    expect(text).toContain('Decision: Pending');
    expect(text).toContain('合成提示');
    expect(text).not.toContain('审查方式');
  });
});
