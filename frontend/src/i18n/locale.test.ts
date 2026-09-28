import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_LOCALE, LOCALE_KEY, localeFromLocation, normalizeLocale, readStoredLocale, translate } from './locale';
import { messages } from './messages';

afterEach(() => vi.unstubAllGlobals());
describe('Chinese-first interface locale', () => {
  it('defaults to Chinese, independently of the browser language', () => {
    vi.stubGlobal('window', { localStorage: { getItem: () => null } });
    vi.stubGlobal('navigator', { language: 'en-US' });
    expect(DEFAULT_LOCALE).toBe('zh-CN');
    expect(readStoredLocale()).toBe('zh-CN');
  });
  it('accepts supported choices and ignores invalid stored values', () => {
    expect(normalizeLocale('zh')).toBe('zh-CN');
    expect(normalizeLocale('en')).toBe('en');
    expect(normalizeLocale('fr')).toBeNull();
    vi.stubGlobal('window', { localStorage: { getItem: (key: string) => key === LOCALE_KEY ? 'en' : null } });
    expect(readStoredLocale()).toBe('en');
  });
  it('supports explicit shareable home and workspace language URLs', () => {
    expect(localeFromLocation('/en', '')).toBe('en');
    expect(localeFromLocation('/zh', '')).toBe('zh-CN');
    expect(localeFromLocation('/legal', '?contract=c1&lang=en')).toBe('en');
    expect(localeFromLocation('/legal', '?lang=invalid')).toBeNull();
  });
  it('survives unavailable preference storage', () => {
    vi.stubGlobal('window', { localStorage: { getItem: () => { throw new Error('blocked'); } } });
    expect(readStoredLocale()).toBe('zh-CN');
  });
  it('translates UI keys and substitutes counts, leaving unknown content verbatim', () => {
    expect(translate('合同类型', 'en')).toBe('Contract type');
    expect(translate('Sign in', 'zh-CN')).toBe('登录');
    expect(translate('{0} 个步骤未完成', 'en', { 0: 3 })).toBe('3 steps are incomplete');
    const source = '【脱敏1】应于签约后支付全部价款。';
    expect(translate(source, 'en')).toBe(source);
    expect(translate('constructor', 'en')).toBe('constructor');
  });
  it('keeps interpolation placeholders identical in both languages', () => {
    for (const [zh, en] of Object.entries(messages)) {
      expect([...zh.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort(), zh)
        .toEqual([...en.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort());
      expect(en.trim().length, zh).toBeGreaterThan(0);
    }
  });
});
