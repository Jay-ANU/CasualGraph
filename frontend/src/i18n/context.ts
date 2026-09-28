import { createContext } from 'react';
import { translate, type Locale } from './locale';
export type I18n = { locale: Locale; setLocale: (locale: Locale) => void; t: (source: string, values?: Record<string, string | number>) => string };
export const LocaleContext = createContext<I18n>({ locale: 'zh-CN', setLocale: () => {}, t: (source, values) => translate(source, 'zh-CN', values) });
