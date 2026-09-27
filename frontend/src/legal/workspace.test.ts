import { describe, expect, it } from 'vitest';
import type { Block, Decision, Finding } from './types';
import { clauseName, clauseOutline, deskStage, filterByTone, headingEnd, markerState, nextUndecided, numberFindings, pagesOf, paragraphRuns,
  placeLabel, redactionTokens, stepFinding, stepOf, toneCounts } from './workspace';

const block = (id: string, text: string, page: number | null = null): Block => ({ id, text, page });
const finding = (id: string, extra: Partial<Finding> = {}): Finding => ({ id, block_id: 'p1', original_quote: '', title: '合成意见', kind: 'commercial',
  severity: 'high', impact: '', reason: '', suggested_text: '', evidence_status: 'not_applicable', missing_facts: [], citations: [], policy_ids: [],
  verification_status: 'supported', ...extra });
const decided = (decision: string): Decision => ({ decision, text: '', version: 1 });

describe('desk stage and stepper', () => {
  it('follows the contract and review lifecycle', () => {
    expect(deskStage({ status: 'redaction_pending' }, null, 'work')).toBe('redaction');
    expect(deskStage({ status: 'ready' }, null, 'export')).toBe('setup');
    expect(deskStage({ status: 'ready' }, { status: 'running' }, 'setup')).toBe('running');
    expect(deskStage({ status: 'ready' }, { status: 'completed' }, 'setup')).toBe('setup');
    expect(deskStage({ status: 'ready' }, { status: 'partial' }, 'export')).toBe('export');
    expect(deskStage({ status: 'ready' }, { status: 'completed' }, 'work')).toBe('results');
  });
  it('never opens export for a review that did not finish', () => {
    expect(deskStage({ status: 'ready' }, { status: 'failed' }, 'export')).toBe('results');
    expect(stepOf('results')).toBe(3);
    expect(stepOf('export')).toBe(4);
  });
});

describe('finding numbers', () => {
  const blocks = [block('p1', '第一条 标的\n甲方采购设备。'), block('p2', '第二条 付款\n甲方预付全款，乙方另行通知交货。')];
  it('number open findings in reading order and keep rejected ones apart', () => {
    const later = finding('later', { block_id: 'p2', original_quote: '乙方另行通知交货' });
    const earlier = finding('earlier', { block_id: 'p2', original_quote: '甲方预付全款' });
    const first = finding('first', { block_id: 'p1', severity: 'low' });
    const missing = finding('missing', { block_id: null });
    const rejected = finding('rejected', { verification_status: 'rejected' });
    const { open, excluded } = numberFindings([missing, later, rejected, earlier, first], blocks);
    expect(open.map(x => [x.finding.id, x.n])).toEqual([['first', 1], ['earlier', 2], ['later', 3], ['missing', 4]]);
    expect(excluded.map(f => f.id)).toEqual(['rejected']);
  });
  it('counts and filters by tone', () => {
    const { open } = numberFindings([finding('a'), finding('b', { severity: 'medium' }), finding('c', { verification_status: 'uncertain' }), finding('d', { severity: 'low' })], blocks);
    expect(toneCounts(open)).toEqual({ all: 4, high: 1, mid: 1, low: 1, unconfirmed: 1 });
    expect(filterByTone(open, 'unconfirmed').map(x => x.finding.id)).toEqual(['c']);
    expect(filterByTone(open, 'all')).toBe(open);
  });
});

describe('keyboard navigation', () => {
  it('moves one step and stays at the ends', () => {
    expect(stepFinding(['a', 'b', 'c'], 'b', 1)).toBe('c');
    expect(stepFinding(['a', 'b', 'c'], 'c', 1)).toBe('c');
    expect(stepFinding(['a', 'b', 'c'], 'a', -1)).toBe('a');
    expect(stepFinding(['a', 'b'], null, 1)).toBe('a');
    expect(stepFinding(['a', 'b'], 'gone', -1)).toBe('b');
    expect(stepFinding([], 'a', 1)).toBeNull();
  });
  it('advances to the next undecided finding, wrapping to earlier ones', () => {
    const decisions = { b: decided('accepted'), c: decided('rejected'), a: decided('pending') };
    expect(nextUndecided(['a', 'b', 'c', 'd'], decisions, 'b')).toBe('d');
    expect(nextUndecided(['a', 'b', 'c'], decisions, 'c')).toBe('a');
    expect(nextUndecided(['a'], {}, 'a')).toBe('a');
  });
});

describe('clause outline', () => {
  it('names clauses from their heading line', () => {
    expect(clauseName('第二条 价款与支付')).toEqual({ no: '第二条', name: '价款与支付' });
    expect(clauseName('第五条 数据：乙方可使用甲方数据。')).toEqual({ no: '第五条', name: '数据' });
    expect(clauseName('一、交付')).toEqual({ no: '一', name: '交付' });
    expect(clauseName('2.1 付款安排')).toEqual({ no: '2.1', name: '付款安排' });
    expect(clauseName('3. 验收')).toEqual({ no: '3', name: '验收' });
    expect(clauseName('甲方：【脱敏1】')).toBeNull();
  });
  it('groups paragraphs under the heading before them, with a 首部 for the preamble', () => {
    const outline = clauseOutline([block('p0', '甲方：【脱敏1】'), block('p1', '第一条 标的'), block('p2', '设备清单见附件。'), block('p3', '第二条 付款：预付。')]);
    expect(outline.map(e => [e.no, e.name, e.blockIds, e.kind])).toEqual([['首部', '当事人', ['p0'], 'preamble'], ['第一条', '标的', ['p1', 'p2'], 'clause'], ['第二条', '付款', ['p3'], 'clause']]);
  });
  it('lists paragraphs when the contract has no headings', () => {
    const outline = clauseOutline([block('a', '双方同意如下'), block('b', '价款为合同附件所列')]);
    expect(outline.map(e => [e.no, e.name, e.kind])).toEqual([['1', '双方同意如下', 'paragraph'], ['2', '价款为合同附件所列', 'paragraph']]);
    expect(placeLabel(outline, 'b')).toBe('第 2 段');
  });
  it('names where a finding sits', () => {
    const outline = clauseOutline([block('p0', '甲方：【脱敏1】'), block('p1', '第一条 标的'), block('p2', '2.1 付款安排\n预付。')]);
    expect(['p0', 'p1', 'p2', null, 'gone'].map(id => placeLabel(outline, id))).toEqual(['首部', '第一条', '2.1 付款安排', '全文', '全文']);
  });
  it('draws markers by decision, and as preliminary while the review runs', () => {
    expect(markerState(undefined, true)).toBe('prelim');
    expect(markerState({ decision: 'draft', text: '', version: 1 }, false)).toBe('revised');
    expect(markerState({ decision: 'rejected', text: '', version: 1 }, false)).toBe('kept');
    expect(markerState({ decision: 'pending', text: '', version: 2 }, false)).toBe('open');
  });
});

describe('paragraph runs', () => {
  it('marks quoted passages and keeps the rest as plain text', () => {
    const f = finding('f', { original_quote: '预付全款' });
    const runs = paragraphRuns('甲方预付全款，乙方交货。', [{ quote: f.original_quote, finding: f }]);
    expect(runs.map(r => [r.text, r.finding?.id])).toEqual([['甲方', undefined], ['预付全款', 'f'], ['，乙方交货。', undefined]]);
  });
  it('keeps the earlier of two overlapping quotes and ignores quotes not in the text', () => {
    const a = finding('a'), b = finding('b'), c = finding('c');
    const runs = paragraphRuns('ABCDEF', [{ quote: 'CDE', finding: b }, { quote: 'ABCD', finding: a }, { quote: 'XYZ', finding: c }]);
    expect(runs.map(r => [r.text, r.finding?.id])).toEqual([['ABCD', 'a'], ['EF', undefined]]);
  });
  it('flags only the heading line as heading, even inside a marked run', () => {
    const text = '第二条 付款\n甲方预付全款。';
    const f = finding('f');
    const runs = paragraphRuns(text, [{ quote: text, finding: f }], headingEnd(text));
    expect(runs).toEqual([{ text: '第二条 付款', finding: f, heading: true }, { text: '\n甲方预付全款。', finding: f }]);
    expect(headingEnd('甲方预付全款。\n乙方交货。')).toBe(0);
  });
  it('carries party candidates for picking our side', () => {
    const runs = paragraphRuns('甲方：【脱敏1】\n乙方：【脱敏2】', [{ quote: '乙方：【脱敏2】', party: '乙方：【脱敏2】' }]);
    expect(runs.map(r => [r.text, r.party])).toEqual([['甲方：【脱敏1】\n', undefined], ['乙方：【脱敏2】', '乙方：【脱敏2】']]);
  });
});

describe('redaction list and pages', () => {
  const blocks = [block('p1', '甲方：【脱敏1】，乙方：【脱敏2】'), block('p2', '【脱敏1】应付款。')];
  it('lists each placeholder once, where it first appears', () => {
    expect(redactionTokens(blocks)).toEqual([{ token: '【脱敏1】', blockId: 'p1' }, { token: '【脱敏2】', blockId: 'p1' }]);
  });
  it('reads original values from the loaded original text', () => {
    const originals = [block('p1', '甲方：星湖精密，乙方：云岭科技'), block('p2', '星湖精密应付款。')];
    expect(redactionTokens(blocks, originals).map(r => [r.token, r.value])).toEqual([['【脱敏1】', '星湖精密'], ['【脱敏2】', '云岭科技']]);
  });
  it('groups paragraphs into sheets by page', () => {
    expect(pagesOf([block('a', '', null), block('b', '', 1), block('c', '', 2), block('d', '', null)]).map(p => [p.page, p.blocks.map(b => b.id)]))
      .toEqual([[1, ['a', 'b']], [2, ['c', 'd']]]);
    expect(pagesOf([block('a', ''), block('b', '')]).length).toBe(1);
  });
});
