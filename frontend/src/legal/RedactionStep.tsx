import { Columns, FileText } from 'lucide-react';
import type { Contract } from './types';
import { RichText } from './ui';
import { ic } from './icon';

export function RedactionStep({ contract, busy, comparing, showingDocument, terms, excludedTerms,
  onShowDocument, onCompare, onTerms, onExcluded, onPreview, onConfirm }: {
  contract: Contract; busy: boolean; comparing: boolean; showingDocument: boolean; terms: string; excludedTerms: string;
  onShowDocument: () => void; onCompare: () => void; onTerms: (value: string) => void; onExcluded: (value: string) => void;
  onPreview: () => void; onConfirm: () => void;
}) {
  const sample = contract.blocks.map(b => b.text.match(/【(?:补充)?脱敏\d+】/)?.[0]).find(Boolean) || '【脱敏1】';
  return <section className="lv-stage lv-enter" aria-labelledby="legal-redaction-title">
    <div className="lv-stage-head">
      <h2 id="legal-redaction-title">脱敏确认</h2>
      <div className="lv-inline-actions">
        {!showingDocument && <button className="lv-secondary lv-btn-sm" onClick={onShowDocument}><FileText {...ic} size={15} />查看正文</button>}
        <button className="lv-secondary lv-btn-sm" aria-pressed={comparing} disabled={busy} onClick={onCompare}><Columns {...ic} size={15} />对照原件</button>
      </div>
    </div>
    <p className="lv-stage-lede">
      {contract.replacement_count > 0 ? <>已自动脱敏 <strong>{contract.replacement_count}</strong> 处，以 <RichText text={sample} /> 标示。</> : '未识别到需脱敏的信息。'}
      请核对主体名称、联系人及账户信息。
    </p>
    <details className="lv-disclosure" open={Boolean(terms || excludedTerms) || undefined}>
      <summary>手动调整</summary>
      <div className="lv-disclosure-body">
        <div className="lv-grid-2">
          <label className="lv-field"><span className="lv-field-label">追加脱敏</span>
            <textarea className="lv-textarea" aria-label="补充脱敏词" rows={3} value={terms} onChange={e => onTerms(e.target.value)} placeholder="每行一项" /></label>
          <label className="lv-field"><span className="lv-field-label">撤销脱敏</span>
            <textarea className="lv-textarea" aria-label="撤销过度脱敏词" rows={3} value={excludedTerms} onChange={e => onExcluded(e.target.value)} placeholder="每行一项" /></label>
        </div>
        <p className="lv-hint">撤销脱敏的内容将随正文提交模型分析。</p>
        <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onPreview}>更新预览</button>
      </div>
    </details>
    <div className="lv-stage-footer">
      <button className="lv-primary" disabled={busy} onClick={onConfirm}>确认脱敏</button>
    </div>
  </section>;
}
