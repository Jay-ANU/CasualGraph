import type { TokenRow } from './workspace';
import { useI18n } from '../i18n/core';

/** Check the placeholders before anything reaches a model; confirming locks them. */
export function RedactionPanel({ tokens, comparing, whereOf, busy, terms, excludedTerms, onTerms, onExcluded, onPreview, onConfirm }: {
  tokens: TokenRow[]; comparing: boolean; whereOf: (blockId: string) => string; busy: boolean;
  terms: string; excludedTerms: string;
  onTerms: (value: string) => void; onExcluded: (value: string) => void; onPreview: () => void; onConfirm: () => void;
}) {
  const { tx } = useI18n();
  return <section className="lv-rail-panel" aria-labelledby="legal-redaction-title">
    <div className="lv-rail-head">
      <h2 id="legal-redaction-title">{tx('脱敏核对', 'Redaction check')}</h2>
      <p>{tx('确认后锁定，模型只会收到脱敏后的文本。', 'Confirming locks the redaction; models only ever receive the redacted text.')}</p>
    </div>
    <div className="lv-rail-body">
      <div className="lv-rail-group">
        <div className="lv-rail-label"><span>{tx('已脱敏', 'Redacted')}</span><span className="lv-mono">{tokens.length}</span></div>
        {tokens.length ? <ul className="lv-token-list">{tokens.map(t => <li key={t.token}>
          <span className="lv-redacted">{t.token.slice(1, -1)}</span>
          <span className={`lv-token-value${comparing && t.value ? ' is-shown' : ''}`}>{comparing ? t.value || tx('未对应到原文', 'Not matched to the original') : tx('已隐藏', 'Hidden')}</span>
          <span className="lv-token-where">{whereOf(t.blockId)}</span>
        </li>)}</ul> : <p className="lv-rail-empty">{tx('未识别到需脱敏的信息，请对照正文核对。', 'Nothing was found to redact. Check the text yourself.')}</p>}
      </div>
      <details className="lv-disclosure" open={Boolean(terms || excludedTerms) || undefined}>
        <summary>{tx('手动调整', 'Adjust manually')}</summary>
        <div className="lv-disclosure-body lv-stack">
          <label className="lv-field"><span className="lv-field-label">{tx('追加脱敏', 'Also redact')}</span>
            <textarea className="lv-textarea" aria-label={tx('补充脱敏词', 'Terms to redact')} rows={2} value={terms} onChange={e => onTerms(e.target.value)} placeholder={tx('每行一项', 'One per line')} /></label>
          <label className="lv-field"><span className="lv-field-label">{tx('撤销脱敏', 'Unredact')}</span>
            <textarea className="lv-textarea" aria-label={tx('撤销过度脱敏词', 'Terms to unredact')} rows={2} value={excludedTerms} onChange={e => onExcluded(e.target.value)} placeholder={tx('每行一项', 'One per line')} /></label>
          <p className="lv-hint is-warn">{tx('撤销脱敏的内容将随正文提交模型分析。', 'Unredacted terms are sent to the model with the text.')}</p>
          <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onPreview}>{tx('更新预览', 'Update preview')}</button>
        </div>
      </details>
    </div>
    <div className="lv-rail-foot">
      <button className="lv-primary lv-wide" disabled={busy} onClick={onConfirm}>{tx('确认脱敏', 'Confirm redaction')}</button>
    </div>
  </section>;
}
