import { afterEach, describe, expect, it } from 'vitest';
import { setCurrentLang, tr } from '../i18n/core';
import { labelOf, plural, serverText } from './i18n';

afterEach(() => setCurrentLang('zh'));

describe('review service text', () => {
  it('stays exactly as sent in the Chinese interface', () => {
    for (const text of ['正在读取合同并分项审查', '分项审查已完成 2/5 项，正在复核其余各项', '法律风险审查', '第 1/2 项：交付、验收与付款']) {
      expect(serverText(text)).toBe(text);
    }
  });
  it('translates fixed messages, agent titles and catalogue values in English', () => {
    setCurrentLang('en');
    expect(serverText('全文协调与冲突检查')).toBe('Whole-contract consistency check');
    expect(serverText('审查已暂停，已完成的步骤已保存')).toBe('Review paused; finished steps are saved');
    expect(serverText('交易日期未提供，法律时间适用仍需核验。')).toBe('The transaction date was not given; which version of the law applies still needs checking.');
    expect(tr('销售合同')).toBe('Sales agreement');
    expect(tr('谈判中')).toBe('In negotiation');
    expect(tr('账期、对账与扣款')).toBe('Credit terms, reconciliation and deductions');
  });
  it('translates stages built from counts and catalogue titles', () => {
    expect(serverText('分项审查已完成 2/5 项，正在复核其余各项', 'en')).toBe('Item review: 2/5 finished; verifying the rest');
    expect(serverText('分项审查已完成 5/5 项', 'en')).toBe('Item review: 5/5 finished');
    expect(serverText('已规划法律检索：3 个问题，正在通过 公开搜索 检索', 'en')).toBe('Legal research planned: 3 issues, searching with public web search');
    expect(serverText('正在分项审查：主体、授权与合同效力、销售合同：核心履行安排、账期、对账与扣款、跨条款与遗漏复查', 'en'))
      .toBe('Reviewing: Parties, authority and validity; Sales agreement: core performance terms; Credit terms, reconciliation and deductions; Cross-clause conflicts and omissions');
    expect(serverText('正在分项审查：法律风险审查、公司利益审查、全文协调与冲突检查', 'en'))
      .toBe('Reviewing: Legal risk review; Commercial interest review; Whole-contract consistency check');
    expect(serverText('协作检查完成，其中 1 项意见需人工确认', 'en')).toBe('Team review finished; 1 finding needs your confirmation');
    expect(serverText('极速审查完成（未做法规检索和独立复核），请逐项确认', 'en'))
      .toBe('Ultra-fast review finished (no legal research or independent verification); confirm each finding');
    expect(serverText('本轮检查部分完成：2 个步骤未完成，可重试；已完成的意见可先处理', 'en'))
      .toBe('Review partly finished: 2 steps did not finish and can be retried; you can work on the finished findings now');
  });
  it('translates agent notes, step titles, coverage titles and skill reasons', () => {
    expect(serverText('第 1/2 项：交付、验收与付款、违约、赔偿与免责', 'en')).toBe('Item 1/2: Delivery, acceptance and payment; Breach, damages and exclusions');
    expect(serverText('复核法律风险审查：交付、验收与付款', 'en')).toBe('Verifying Legal risk review: Delivery, acceptance and payment');
    expect(serverText('核对 1 项拟议修改能否同时成立', 'en')).toBe('Checking that 1 proposed edit can stand together');
    expect(serverText('分项审查：违约、赔偿与免责；期限、续约与退出', 'en')).toBe('Item review: Breach, damages and exclusions; Term, renewal and exit');
    expect(serverText('法律风险审查 / 交付、验收与付款', 'en')).toBe('Legal risk review / Delivery, acceptance and payment');
    expect(serverText('通用审查方法；合同场景：销售合同', 'en')).toBe('General review method; Contract type: Sales agreement');
  });
  it('never guesses: unknown text, model output and half-known lists stay as sent', () => {
    expect(serverText('付款条件未与确定的交货期限挂钩。', 'en')).toBe('付款条件未与确定的交货期限挂钩。');
    // A company policy's own title is not in the dictionary, so the list after the known frame stays whole.
    expect(serverText('第 1/1 项：预付款比例上限', 'en')).toBe('Item 1/1: 预付款比例上限');
    expect(serverText('正在分项审查：交付、验收与付款、预付款比例上限', 'en')).toBe('Reviewing: 交付、验收与付款、预付款比例上限');
    expect(serverText('复核某个环节：交付、验收与付款', 'en')).toBe('复核某个环节：交付、验收与付款');
    expect(serverText('Already English', 'en')).toBe('Already English');
    expect(serverText('', 'en')).toBe('');
    expect(serverText(undefined, 'en')).toBe('');
  });
});

describe('bilingual helpers', () => {
  it('pick a label by key and language, and count in English', () => {
    const map = { ready: ['可审查', 'Ready'] } as const;
    expect(labelOf(map, 'ready', 'zh')).toBe('可审查');
    expect(labelOf(map, 'ready', 'en')).toBe('Ready');
    expect(labelOf(map, 'constructor', 'en')).toBeUndefined();
    expect(plural(1, 'note')).toBe('1 note');
    expect(plural(3, 'note')).toBe('3 notes');
    expect(plural(2, 'search', 'searches')).toBe('2 searches');
  });
});
