import { describe, expect, it } from 'vitest';
import { agentLine, formatClock, phaseDetail, remainingLabel, remainingSeconds, reviewEvents, reviewPercent, reviewPhase } from './reviewActivity';
import type { Collaboration, Finding, Review } from './types';

const finding = (id: string, extra: Partial<Finding> = {}): Finding => ({ id, block_id: 'p1', original_quote: '合成原文', title: '付款保障', kind: 'commercial', severity: 'high', impact: '预付风险', reason: '交付时间未约定', suggested_text: '合成修改', evidence_status: 'not_applicable', missing_facts: [], citations: [], policy_ids: [], verification_status: 'supported', ...extra });
type AgentState = [status: string, completed: number, note?: string];
const team = (legal: AgentState, commercial: AgentState, critic: AgentState, arbiter: AgentState): Collaboration => ({
  version: 1, max_parallel: 3, call_budget: 40, agents: [
    { id: 'legal', title: '法律风险审查', status: legal[0], completed: legal[1], total: 2, note: legal[2] || '' },
    { id: 'commercial', title: '公司利益审查', status: commercial[0], completed: commercial[1], total: 2, note: commercial[2] || '' },
    { id: 'policy', title: '公司规范审查', status: 'not_applicable', completed: 0, total: 0, note: '本轮没有适用的公司规范。' },
    { id: 'critic', title: '证据与覆盖复核', status: critic[0], completed: critic[1], total: 4, note: critic[2] || '' },
    { id: 'arbiter', title: '全文协调与冲突检查', status: arbiter[0], completed: arbiter[1], total: 1, note: arbiter[2] || '' },
  ] });
const review = (extra: Partial<Review>): Review => ({ id: 'r1', status: 'running', stage: '', resumable: false, findings: [], coverage: [], sources: [], decisions: {}, policies: [], notice: '', ...extra });
const idle = team(['pending', 0], ['pending', 0], ['pending', 0], ['pending', 0]);

describe('live review phases', () => {
  it('maps engine phases onto the four visible steps', () => {
    expect(reviewPhase(review({ status: 'queued' }))).toBe('queued');
    expect(reviewPhase(review({ progress: { phase: 'intake', completed: 0, total: 5 } }))).toBe('intake');
    expect(reviewPhase(review({ progress: { phase: 'retrieval', completed: 2, total: 6 } }))).toBe('retrieval');
    expect(reviewPhase(review({ progress: { phase: 'collaboration', completed: 0, total: 5 }, collaboration: idle }))).toBe('review');
    const arbitrating = team(['completed', 2], ['completed', 2], ['completed', 4], ['running', 0]);
    expect(reviewPhase(review({ progress: { phase: 'collaboration', completed: 4, total: 5 }, collaboration: arbitrating }))).toBe('coordination');
    expect(reviewPhase(review({ progress: { phase: 'arbitration', completed: 4, total: 5 }, collaboration: idle }))).toBe('coordination');
    expect(reviewPhase(review({ progress: { phase: 'verification', completed: 1, total: 5 } }))).toBe('review');
    expect(reviewPhase(review({ progress: { phase: 'review', completed: 4, total: 5 } }))).toBe('coordination');
    expect(reviewPhase(review({ status: 'completed' }))).toBe('complete');
  });
});

describe('live review percent', () => {
  it('moves with every finished model call while the step count stays frozen', () => {
    // Old engines never update progress.completed during collaboration; calls still move the bar.
    const frozen = { phase: 'collaboration', completed: 0, total: 5 };
    const working = team(['running', 0], ['running', 0], ['pending', 0], ['pending', 0]);
    const values = [4, 6, 8].map(calls => reviewPercent(review({ progress: frozen, collaboration: working, metrics: { model_calls: calls } })));
    expect(values[0]).toBeGreaterThan(20);
    expect(values[1]).toBeGreaterThan(values[0]);
    expect(values[2]).toBeGreaterThan(values[1]);
    expect(values[2]).toBeLessThan(88);
  });
  it('uses finished tasks when calls were counted in an earlier attempt', () => {
    const halfDone = team(['running', 1], ['running', 1], ['running', 2], ['pending', 0]);
    expect(reviewPercent(review({ progress: { phase: 'collaboration', completed: 2, total: 5 }, collaboration: halfDone }))).toBeCloseTo(54, 0);
  });
  it('stays inside each phase band and ends at 100 only when complete', () => {
    const coordination = review({ progress: { phase: 'arbitration', completed: 4, total: 5 }, collaboration: team(['completed', 2], ['completed', 2], ['completed', 4], ['running', 0]), metrics: { model_calls: 11 } });
    expect(reviewPercent(coordination)).toBeGreaterThanOrEqual(88);
    expect(reviewPercent(coordination)).toBeLessThan(100);
    expect(reviewPercent(review({ status: 'queued' }))).toBe(0);
    expect(reviewPercent(review({ status: 'completed' }))).toBe(100);
    const retrieval = reviewPercent(review({ progress: { phase: 'retrieval', completed: 3, total: 6 } }));
    expect(retrieval).toBeGreaterThan(6);
    expect(retrieval).toBeLessThan(20);
  });
  it('follows single-agent groups and their verification half-steps', () => {
    const reviewing = reviewPercent(review({ progress: { phase: 'review', completed: 1, total: 4 } }));
    const verifying = reviewPercent(review({ progress: { phase: 'verification', completed: 1, total: 4 } }));
    expect(verifying).toBeGreaterThan(reviewing);
  });
});

describe('live review labels', () => {
  it('states concrete counts and a rough time left only with enough signal', () => {
    expect(phaseDetail(review({ progress: { phase: 'collaboration', completed: 1, total: 5 }, collaboration: team(['running', 1], ['running', 0], ['running', 1], ['pending', 0]) }))).toBe('分项审查 · 已完成 1/4 项');
    expect(phaseDetail(review({ progress: { phase: 'verification', completed: 1, total: 4 } }))).toBe('分项审查 · 第 2/4 组');
    expect(remainingSeconds(10, 600)).toBeNull();
    expect(remainingSeconds(50, 30)).toBeNull();
    expect(remainingSeconds(50, 300)).toBe(300);
    expect(remainingLabel(300)).toBe('约 5 分钟');
    expect(remainingLabel(301)).toBe('约 6 分钟');
    expect(remainingLabel(40)).toBe('即将完成');
    expect(formatClock(75)).toBe('1:15');
    expect(formatClock(3725)).toBe('1:02:05');
  });
});

describe('live review activity', () => {
  it('reports agent starts, finished items, current items and new findings', () => {
    const before = review({ progress: { phase: 'collaboration', completed: 0, total: 5 }, stage: '多个审查 Agent 正在分别检查合同',
      collaboration: team(['running', 0, '第 1/2 项：付款'], ['pending', 0], ['pending', 0], ['pending', 0]) });
    const after = review({ progress: { phase: 'collaboration', completed: 1, total: 5 }, stage: '多个审查 Agent 正在分别检查合同（已完成 1/4 项）',
      collaboration: team(['running', 1, '第 2/2 项：违约责任'], ['running', 0, '第 1/2 项：付款'], ['running', 1, '复核法律风险审查：付款'], ['pending', 0]),
      findings: [finding('f1', { title: '签约即付清全款' })] });
    expect(reviewEvents(before, after).map(e => e.text)).toEqual([
      '法律风险审查完成第 1/2 项',
      '法律风险审查 · 第 2/2 项：违约责任',
      '公司利益审查开始工作',
      '公司利益审查 · 第 1/2 项：付款',
      '证据与覆盖复核开始工作',
      '证据与覆盖复核完成第 1/4 项',
      '复核法律风险审查：付款',
      '发现高风险意见：签约即付清全款',
    ]);
  });
  it('reports stage changes outside the counter-only collaboration updates, and completions', () => {
    const a = review({ progress: { phase: 'retrieval', completed: 0, total: 6 }, stage: '法律资料检索：付款' });
    const b = review({ progress: { phase: 'retrieval', completed: 1, total: 6 }, stage: '法律资料检索：违约' });
    expect(reviewEvents(a, b)).toEqual([{ text: '法律资料检索：违约', tone: 'ink' }]);
    const running = review({ progress: { phase: 'arbitration', completed: 4, total: 5 }, collaboration: team(['completed', 2], ['completed', 2], ['completed', 4], ['running', 0]) });
    const partial = review({ progress: { phase: 'arbitration', completed: 4, total: 5 }, collaboration: team(['completed', 2], ['completed', 2], ['completed', 4], ['partial', 0]) });
    expect(reviewEvents(running, partial)).toEqual([{ text: '全文协调与冲突检查部分完成', tone: 'warn' }]);
    expect(reviewEvents(null, b)).toEqual([]);
    expect(reviewEvents(review({ id: 'other' }), b)).toEqual([]);
  });
  it('summarises bursts of findings and skips excluded ones', () => {
    const many = ['a', 'b', 'c', 'd'].map(id => finding(id, { severity: 'medium' }));
    const texts = reviewEvents(review({}), review({ findings: [...many, finding('x', { verification_status: 'rejected' })] })).map(e => e.text);
    expect(texts).toEqual(['发现中风险意见：付款保障', '发现中风险意见：付款保障', '另有 2 条新意见']);
  });
});

describe('agent lines', () => {
  it('prefers the engine note and otherwise states counts', () => {
    const [legal, , policy, critic, arbiter] = team(['running', 1], ['pending', 0], ['pending', 0], ['pending', 0]).agents;
    expect(agentLine(legal)).toBe('正在审查第 2/2 项');
    expect(agentLine({ ...legal, note: '第 2/2 项：违约责任' })).toBe('第 2/2 项：违约责任');
    expect(agentLine(policy)).toBe('本轮没有适用的公司规范。');
    expect(agentLine(critic)).toBe('随各项审查逐项复核');
    expect(agentLine(arbiter)).toBe('分项审查完成后开始');
    expect(agentLine({ ...critic, status: 'running', completed: 3 })).toBe('已复核 3/4 项');
    expect(agentLine({ ...legal, status: 'completed', completed: 2 })).toBe('已完成 2/2 项');
    expect(agentLine({ ...legal, status: 'partial' })).toBe('部分完成 1/2 项');
  });
});
