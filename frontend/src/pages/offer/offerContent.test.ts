import {
  copyFor,
  countdownTo,
  easeOutExpo,
  employmentLabel,
  formatAmount,
  formatLongDate,
  greetingName,
  parseIsoDate,
  periodLabel,
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
    expect(copyFor('en').accept).toBe('Accept offer');
    expect(copyFor(undefined).greeting('Ada')).toBe('Welcome aboard, Ada.');
  });

  it('labels employment types and pay periods', () => {
    expect(employmentLabel('full_time', 'en')).toBe('Full-time');
    expect(employmentLabel('internship', 'zh')).toBe('实习');
    expect(employmentLabel('', 'en')).toBe('');
    expect(periodLabel('year', 'en')).toBe('per year');
    expect(periodLabel('month', 'zh')).toBe('每月');
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
  });

  it('counts down to the end of the reply day', () => {
    const now = new Date(2026, 8, 28, 12, 0, 0);
    expect(countdownTo('2026-09-30', now)).toEqual({ days: 2, hours: 11, minutes: 59, seconds: 59, passed: false });
    expect(countdownTo('2026-09-27', now)).toEqual({ days: 0, hours: 0, minutes: 0, seconds: 0, passed: true });
    expect(countdownTo('', now)).toBeNull();
  });

  it('pads and eases', () => {
    expect(twoDigits(7)).toBe('07');
    expect(twoDigits(12)).toBe('12');
    expect(easeOutExpo(0)).toBe(0);
    expect(easeOutExpo(1)).toBe(1);
    expect(easeOutExpo(0.5)).toBeGreaterThan(0.9);
  });
});
