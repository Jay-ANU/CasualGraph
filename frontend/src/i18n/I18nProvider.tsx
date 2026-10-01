import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { I18nContext, LANG_STORAGE_KEY, currentLang, isLang, setCurrentLang, type Lang } from './core';

export default function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(currentLang);
  const setLang = useCallback((next: Lang) => {
    // Update the module value first so helpers read the new language during the re-render.
    setCurrentLang(next);
    try { localStorage.setItem(LANG_STORAGE_KEY, next); } catch { /* the choice still applies to this tab */ }
    setLangState(next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  }, [lang]);

  useEffect(() => {
    // Another tab changed the language.
    const onStorage = (event: StorageEvent) => {
      if (event.key === LANG_STORAGE_KEY && isLang(event.newValue)) {
        setCurrentLang(event.newValue);
        setLangState(event.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
