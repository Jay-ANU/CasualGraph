import { messages } from './messages';

export type Locale = 'zh-CN' | 'en';
export const LOCALE_KEY = 'causalgraph.locale';
export const DEFAULT_LOCALE: Locale = 'zh-CN';
export function normalizeLocale(value: unknown): Locale | null {
  if (value === 'zh' || value === 'zh-CN') return 'zh-CN';
  return value === 'en' ? 'en' : null;
}
export function localeFromLocation(pathname: string, search: string): Locale | null {
  return normalizeLocale(new URLSearchParams(search).get('lang'))
    || (pathname === '/en' ? 'en' : pathname === '/zh' ? 'zh-CN' : null);
}
export function readStoredLocale(): Locale {
  try { return normalizeLocale(window.localStorage.getItem(LOCALE_KEY)) || DEFAULT_LOCALE; }
  catch { return DEFAULT_LOCALE; }
}
const reverse = new Map(Object.entries(messages).map(([zh, en]) => [en, zh]));
/** Explicit UI copy only. Never send contract text or user input to this function. */
export function translate(source: string, locale: Locale, values?: Record<string, string | number>): string {
  const result = locale === 'en' ? (Object.prototype.hasOwnProperty.call(messages, source) ? messages[source] : source) : reverse.get(source) ?? source;
  return values ? result.replace(/\{(\w+)\}/g, (match, key: string) => key in values ? String(values[key]) : match) : result;
}
