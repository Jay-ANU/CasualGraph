import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LocaleContext } from './context';
import { LOCALE_KEY, localeFromLocation, normalizeLocale, readStoredLocale, translate, type Locale } from './locale';

export default function LocaleProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const explicit = localeFromLocation(location.pathname, location.search);
  const [saved, setSaved] = useState<Locale>(() => explicit || readStoredLocale());
  const locale = explicit || saved;
  useEffect(() => {
    document.documentElement.lang = locale;
    try { window.localStorage.setItem(LOCALE_KEY, locale); } catch { /* Private browsing still supports an in-memory choice. */ }
    // A shared language URL also becomes the preference for subsequent routes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- synchronize a URL-driven preference without remounting forms
    setSaved(locale);
  }, [locale]);
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === LOCALE_KEY) setSaved(normalizeLocale(event.newValue) || 'zh-CN'); };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  const setLocale = useCallback((next: Locale) => {
    setSaved(next);
    // The desk updates its contract deep link without remounting the router.
    const current = new URL(window.location.href);
    const params = current.searchParams;
    const home = ['/', '/home', '/zh', '/en'].includes(location.pathname);
    if (home) params.delete('lang'); else params.set('lang', next);
    navigate({ pathname: home ? (next === 'en' ? '/en' : '/zh') : location.pathname,
      search: params.toString() ? `?${params}` : '', hash: current.hash }, { replace: true, state: location.state });
  }, [location, navigate]);
  const value = useMemo(() => ({ locale, setLocale, t: (source: string, values?: Record<string, string | number>) => translate(source, locale, values) }), [locale, setLocale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}
