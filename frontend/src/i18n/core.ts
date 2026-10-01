import { createContext, useCallback, useContext } from 'react';
import { BASE_EN } from './en';

/** Interface language. Chinese is the default; English is opt-in and remembered. */
export type Lang = 'zh' | 'en';
export const LANG_STORAGE_KEY = 'causalgraph.lang';

export const isLang = (value: unknown): value is Lang => value === 'zh' || value === 'en';

/** `?lang=en` (or `zh`) wins, then the saved choice, then Chinese. The browser's own language is not used. */
export function initialLang(): Lang {
  if (typeof window === 'undefined') return 'zh';
  try {
    const fromUrl = new URL(window.location.href).searchParams.get('lang');
    if (isLang(fromUrl)) return fromUrl;
  } catch { /* fall through */ }
  try {
    const saved = localStorage.getItem(LANG_STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch { /* storage can be blocked */ }
  return 'zh';
}

let current: Lang = initialLang();

const EN: Record<string, string> = { ...BASE_EN };

/** Adds a feature area's Chinese → English entries; called once when that area's code loads. */
export function registerEnglish(dictionary: Record<string, string>) {
  Object.assign(EN, dictionary);
}

/** Read by code outside React (label helpers, the class-based contract desk). */
export const currentLang = (): Lang => current;
export function setCurrentLang(lang: Lang) { current = lang; }

/**
 * Chinese text that arrives from data, helpers or the API (scenario names, stages, labels)
 * is translated through the dictionary; anything unknown is shown as it is, never guessed.
 */
export function tr(zh: string, lang: Lang = current): string {
  return lang === 'en' ? EN[zh] ?? zh : zh;
}

/** Inline pair for interface copy written in both languages next to each other. */
export function pick(zh: string, en: string, lang: Lang = current): string {
  return lang === 'en' ? en : zh;
}

export type I18nValue = { lang: Lang; setLang: (lang: Lang) => void };
export const I18nContext = createContext<I18nValue | null>(null);

export function useI18n() {
  const context = useContext(I18nContext);
  const lang = context?.lang ?? current;
  const tx = useCallback((zh: string, en: string) => pick(zh, en, lang), [lang]);
  const t = useCallback((zh: string) => tr(zh, lang), [lang]);
  return { lang, setLang: context?.setLang ?? setCurrentLang, tx, t };
}
