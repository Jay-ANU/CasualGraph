import {
  PublicOffer,
  clockOf,
  copyFor,
  countdownTo,
  employmentLabel,
  formatAmount,
  formatLongDate,
  formatShortDate,
  formatTimestamp,
  greetingName,
  offerReference,
  parseIsoDate,
  periodLabel,
  referenceBars,
  referenceSeed,
  replyWindowLeft,
  tokenFromPath,
  twoDigits,
} from './offerContent';

describe('offer page wording', () => {
  it('greets by first name, and by full name in Chinese', () => {
    expect(greetingName('Ada Lovelace')).toBe('Ada');
    expect(greetingName('  张三 ')).toBe('张三');
    expect(greetingName('')).toBe('');
  });

  it('picks the copy for the offer language', () => {
    expect(copyFor('zh').accept).toBe('接受录用');
    expect(copyFor('en').accept).toBe('Accept the offer');
    expect(copyFor(undefined).greeting('Ada')).toBe('Ada, we would like you to join us.');
    expect(copyFor('en').greeting('')).toBe('We would like you to join us.');
    expect(copyFor('zh').greeting('张三').replace(/\u200b/g, '')).toBe('张三，我们诚挚邀请您加入。');
  });

  it('labels employment types and pay periods', () => {
    expect(employmentLabel('full_time', 'en')).toBe('Full-time');
    expect(employmentLabel('internship', 'zh')).toBe('实习');
    expect(employmentLabel('', 'en')).toBe('');
    expect(periodLabel('year', 'en')).toBe('per year');
    expect(periodLabel('month', 'zh')).toBe('每月');
  });

  it('keeps both languages complete', () => {
    const en = copyFor('en') as unknown as Record<string, unknown>;
    const zh = copyFor('zh') as unknown as Record<string, unknown>;
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
    expect(Object.keys(zh.card as object).sort()).toEqual(Object.keys(en.card as object).sort());
  });
});

describe('offer page numbers and dates', () => {
  it('formats salary amounts with grouping and cents only when needed', () => {
    expect(formatAmount(95000, 'en')).toBe('95,000');
    expect(formatAmount(42.5, 'en')).toBe('42.50');
    expect(formatAmount(182867.58, 'en', 0)).toBe('182,868');
  });

  it('parses dates as local calendar days', () => {
    const date = parseIsoDate('2026-10-05');
    expect(date && [date.getFullYear(), date.getMonth(), date.getDate()]).toEqual([2026, 9, 5]);
    expect(parseIsoDate('soon')).toBeNull();
    expect(formatLongDate('2026-10-05', 'en')).toContain('5 October 2026');
    expect(formatLongDate('', 'en')).toBe('');
    expect(formatShortDate('2026-10-05', 'en')).toBe('5 Oct 2026');
    expect(formatShortDate('2026-10-05', 'zh')).toBe('2026年10月5日');
    expect(formatTimestamp('2026-09-24T03:04:05+00:00', 'en', 'short')).toMatch(/^2[34] Sept? 2026$/);
    expect(formatTimestamp('not a date', 'en')).toBe('');
  });

  it('counts down to the end of the reply day', () => {
    const now = new Date(2026, 8, 28, 12, 0, 0);
    expect(countdownTo('2026-09-30', now)).toEqual({ days: 2, hours: 11, minutes: 59, seconds: 59, passed: false });
    expect(countdownTo('2026-09-27', now)).toEqual({ days: 0, hours: 0, minutes: 0, seconds: 0, passed: true });
    expect(countdownTo('', now)).toBeNull();
    expect(clockOf({ days: 2, hours: 11, minutes: 5, seconds: 9, passed: false })).toBe('11:05:09');
  });

  it('measures how much of the reply window is left', () => {
    const sent = new Date(2026, 8, 20, 12, 0, 0).toISOString();
    const halfway = new Date(2026, 8, 25, 17, 59, 59);
    expect(replyWindowLeft(sent, '2026-09-30', halfway)).toBeCloseTo(0.5, 2);
    expect(replyWindowLeft(sent, '2026-09-30', new Date(2026, 9, 5))).toBe(0);
    expect(replyWindowLeft(null, '2026-09-30', halfway)).toBeNull();
    expect(replyWindowLeft(sent, '', halfway)).toBeNull();
  });

  it('pads', () => {
    expect(twoDigits(7)).toBe('07');
    expect(twoDigits(12)).toBe('12');
  });
});

describe('offer reference', () => {
  const offer = { organisation: 'CausalGraph AI', candidate_name: 'Ada', position: 'Engineer' } as PublicOffer;

  it('reads the token from the page path only', () => {
    expect(tokenFromPath('/offer/BNMtV8a1a41-So6UU1B-hvVa7jtotwx')).toBe('BNMtV8a1a41-So6UU1B-hvVa7jtotwx');
    expect(tokenFromPath('/offer/short')).toBe('');
    expect(tokenFromPath('/admin/recruitment')).toBe('');
    expect(referenceSeed(offer, '/offer/BNMtV8a1a41-So6UU1B-hvVa7jtotwx')).toBe('BNMtV8a1a41-So6UU1B-hvVa7jtotwx');
    expect(referenceSeed(offer, '/admin/recruitment')).toBe('draft:CausalGraph AI|Ada|Engineer|');
  });

  it('derives a stable, readable reference and code strip from the token', () => {
    const reference = offerReference('BNMtV8a1a41-So6UU1B-hvVa7jtotwx');
    expect(reference).toMatch(/^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$/);
    expect(offerReference('BNMtV8a1a41-So6UU1B-hvVa7jtotwx')).toBe(reference);
    expect(offerReference('another-token-0123456789')).not.toBe(reference);

    const bars = referenceBars('BNMtV8a1a41-So6UU1B-hvVa7jtotwx');
    expect(bars).toHaveLength(30);
    expect(bars.every(([bar, gap]) => bar >= 1 && bar <= 3 && gap >= 1 && gap <= 2)).toBe(true);
    expect(referenceBars('BNMtV8a1a41-So6UU1B-hvVa7jtotwx')).toEqual(bars);
  });
});
