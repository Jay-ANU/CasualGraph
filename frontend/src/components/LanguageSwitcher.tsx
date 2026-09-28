import { Globe2 } from 'lucide-react';
import { useI18n } from '../i18n/useI18n';
import './LanguageSwitcher.css';

export default function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();
  return <div className="cg-language" role="group" aria-label={t('界面语言')}>
    <Globe2 size={15} aria-hidden="true" />
    <button type="button" lang="zh-CN" aria-pressed={locale === 'zh-CN'} onClick={() => setLocale('zh-CN')}>中文</button>
    <span aria-hidden="true">/</span>
    <button type="button" lang="en" aria-pressed={locale === 'en'} onClick={() => setLocale('en')}>EN</button>
  </div>;
}
