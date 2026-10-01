import { useI18n, type Lang } from '../i18n/core';

const OPTIONS: { value: Lang; label: string; htmlLang: string }[] = [
  { value: 'zh', label: '中文', htmlLang: 'zh-CN' },
  { value: 'en', label: 'EN', htmlLang: 'en' },
];

/** 中文 / EN. Chinese is the default; the choice is remembered on this device. */
export default function LanguageSwitch({ tone = 'light', className = '' }: { tone?: 'light' | 'dark'; className?: string }) {
  const { lang, setLang, tx } = useI18n();
  return (
    <div role="group" aria-label={tx('界面语言', 'Interface language')} className={`cg-lang cg-lang-${tone} ${className}`}>
      {OPTIONS.map(option => (
        <button
          key={option.value}
          type="button"
          lang={option.htmlLang}
          aria-pressed={lang === option.value}
          onClick={() => setLang(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
