import { useI18n } from '../i18n/useI18n';
import type { TokenRow } from './workspace';

/** Check the placeholders before anything reaches a model; confirming locks them. */
export function RedactionPanel({ tokens, comparing, whereOf, busy, terms, excludedTerms, onTerms, onExcluded, onPreview, onConfirm }: {
  tokens: TokenRow[]; comparing: boolean; whereOf: (blockId: string) => string; busy: boolean;
  terms: string; excludedTerms: string;
  onTerms: (value: string) => void; onExcluded: (value: string) => void; onPreview: () => void; onConfirm: () => void;
}) {
  const { t } = useI18n();
  return <section className="lv-rail-panel" aria-labelledby="legal-redaction-title">
    <div className="lv-rail-head">
      <h2 id="legal-redaction-title">{t("脱敏核对")}</h2>
      <p>{t("确认后锁定，模型只会收到脱敏后的文本。")}</p>
    </div>
    <div className="lv-rail-body">
      <div className="lv-rail-group">
        <div className="lv-rail-label"><span>{t("已脱敏")}</span><span className="lv-mono">{tokens.length}</span></div>
        {tokens.length ? <ul className="lv-token-list">{tokens.map(token => <li key={token.token}>
          <span className="lv-redacted">{token.token.slice(1, -1)}</span>
          <span className={`lv-token-value${comparing && token.value ? ' is-shown' : ''}`}>{comparing ? token.value || t("未对应到原文") : t("已隐藏")}</span>
          <span className="lv-token-where">{whereOf(token.blockId)}</span>
        </li>)}</ul> : <p className="lv-rail-empty">{t("未识别到需脱敏的信息，请对照正文核对。")}</p>}
      </div>
      <details className="lv-disclosure" open={Boolean(terms || excludedTerms) || undefined}>
        <summary>{t("手动调整")}</summary>
        <div className="lv-disclosure-body lv-stack">
          <label className="lv-field"><span className="lv-field-label">{t("追加脱敏")}</span>
            <textarea className="lv-textarea" aria-label={t("补充脱敏词")} rows={2} value={terms} onChange={e => onTerms(e.target.value)} placeholder={t("每行一项")} /></label>
          <label className="lv-field"><span className="lv-field-label">{t("撤销脱敏")}</span>
            <textarea className="lv-textarea" aria-label={t("撤销过度脱敏词")} rows={2} value={excludedTerms} onChange={e => onExcluded(e.target.value)} placeholder={t("每行一项")} /></label>
          <p className="lv-hint is-warn">{t("撤销脱敏的内容将随正文提交模型分析。")}</p>
          <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onPreview}>{t("更新预览")}</button>
        </div>
      </details>
    </div>
    <div className="lv-rail-foot">
      <button className="lv-primary lv-wide" disabled={busy} onClick={onConfirm}>{t("确认脱敏")}</button>
    </div>
  </section>;
}
