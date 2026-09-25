import { describe, expect, it } from 'vitest';
import { blockFragments, clauseLabel, partyCandidates, splitRedactions, truncateText } from './text';
import type { Block } from './types';

const block = (id: string, text: string): Block => ({ id, text, page: null });

describe('splitRedactions', () => {
  it('separates both kinds of placeholders from ordinary text', () => {
    expect(splitRedactions('甲方：【脱敏1】，联系人【补充脱敏2】。')).toEqual([
      { kind: 'text', text: '甲方：' }, { kind: 'redacted', text: '【脱敏1】' },
      { kind: 'text', text: '，联系人' }, { kind: 'redacted', text: '【补充脱敏2】' }, { kind: 'text', text: '。' },
    ]);
  });
  it('leaves text without placeholders untouched', () => {
    expect(splitRedactions('合同总价款为人民币十万元。')).toEqual([{ kind: 'text', text: '合同总价款为人民币十万元。' }]);
    expect(splitRedactions('')).toEqual([]);
  });
});

describe('truncateText', () => {
  it('never cuts a placeholder in half', () => {
    expect(truncateText('甲方应向【脱敏12】支付', 6)).toBe('甲方应向…');
    expect(truncateText('短文本', 10)).toBe('短文本');
  });
});

describe('clauseLabel', () => {
  it('uses the clause heading when the paragraph starts with one', () => {
    expect(clauseLabel(block('p4', '第二条 价款与支付\n合同总价款为人民币 1,280,000 元。'))).toBe('第二条 价款与支付');
    expect(clauseLabel(block('p5', '3.1 付款安排：验收后十日内付款'))).toBe('3.1 付款安排：验收后十日内付款');
  });
  it('falls back to a short opening snippet', () => {
    expect(clauseLabel(block('p1', '【脱敏1】应在签约后支付全部价款，交货时间另行通知。'))).toBe('【脱敏1】应在签约后支付全部价款…');
    expect(clauseLabel(undefined)).toBe('');
  });
});

describe('partyCandidates', () => {
  it('quotes party lines verbatim and skips representatives', () => {
    const blocks = [block('p1', '设备采购合同'), block('p2', '甲方（采购方）：【脱敏1】\n法定代表人：【脱敏3】\n乙方（供应方）：【脱敏2】'), block('p3', '甲方应在签约后付款。')];
    expect(partyCandidates(blocks).map(c => [c.blockId, c.quote])).toEqual([
      ['p2', '甲方（采购方）：【脱敏1】'], ['p2', '乙方（供应方）：【脱敏2】'],
    ]);
  });
  it('offers bare placeholders when no party line exists', () => {
    expect(partyCandidates([block('p1', '【脱敏1】应在签约后支付全部价款。')])).toEqual([{ blockId: 'p1', quote: '【脱敏1】', context: '【脱敏1】应在签约后支付全部价款。' }]);
    expect(partyCandidates([block('p2', '甲方：【脱敏1】')])[0].context).toBeUndefined();
  });
  it('returns quotes that are always contained in their paragraph', () => {
    const blocks = [block('a', '出租人：【脱敏1】\n承租人：张三'), block('b', '甲方（盖章）：【脱敏1】')];
    for (const c of partyCandidates(blocks)) expect(blocks.find(b => b.id === c.blockId)?.text.includes(c.quote)).toBe(true);
    expect(partyCandidates(blocks, 1)).toHaveLength(1);
  });
});

describe('blockFragments', () => {
  it('keeps the manual per-paragraph fragments', () => {
    expect(blockFragments(block('p', '甲方：【脱敏1】，乙方：【脱敏2】'))).toEqual(['甲方：【脱敏1】', '乙方：【脱敏2】']);
    expect(blockFragments(block('p', '【脱敏1】应在签约后付款'))).toEqual(['【脱敏1】']);
    expect(blockFragments(undefined)).toEqual([]);
  });
});
