import { describe, expect, it } from 'vitest';
import { diffText, phraseDiff } from './diff';

describe('redline diffs', () => {
  it('rebuilds both texts from the parts', () => {
    const before = '【脱敏1】应在签约后支付全部价款，交货时间另行通知。';
    const after = '【脱敏1】在交货验收后支付价款，交货应在签约后三十日内完成。';
    for (const parts of [diffText(before, after), phraseDiff(before, after)]) {
      expect(parts.filter(p => p.kind !== 'ins').map(p => p.text).join('')).toBe(before);
      expect(parts.filter(p => p.kind !== 'del').map(p => p.text).join('')).toBe(after);
    }
  });
  it('reads a reworded phrase as one deletion and one insertion', () => {
    const parts = phraseDiff('甲方应在签约后付款', '甲方在交货验收后付款');
    expect(parts).toEqual([{ kind: 'same', text: '甲方' }, { kind: 'del', text: '应在签约' }, { kind: 'ins', text: '在交货验收' }, { kind: 'same', text: '后付款' }]);
  });
  it('keeps longer unchanged runs and leaves identical text alone', () => {
    expect(phraseDiff('付款期限三十日', '付款期限六十日')).toEqual([{ kind: 'same', text: '付款期限' }, { kind: 'del', text: '三' }, { kind: 'ins', text: '六' }, { kind: 'same', text: '十日' }]);
    expect(phraseDiff('不变', '不变')).toEqual([{ kind: 'same', text: '不变' }]);
  });
});
