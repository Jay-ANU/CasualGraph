import { ArrowRight, Columns, FileText } from 'lucide-react';
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
  return <section className="lv-stage" aria-labelledby="legal-redaction-title">
    <h2 id="legal-redaction-title">检查自动脱敏的结果</h2>
    <p className="lv-stage-lede">
      {contract.replacement_count > 0 ? <>系统已把 <strong>{contract.replacement_count} 处</strong>信息替换成代号，</> : '系统没有自动识别到需要替换的信息，'}
      在正文中显示为 <RichText text={sample} />。请逐段核对公司名称、联系人、电话和账户是否都已隐藏；交易金额和期限会保留，以便审查。
    </p>
    <div className="lv-inline-actions">
      {!showingDocument && <button className="lv-secondary" onClick={onShowDocument}><FileText {...ic} />查看合同正文</button>}
      <button className="lv-quiet" aria-pressed={comparing} disabled={busy} onClick={onCompare}><Columns {...ic} />对照原件</button>
    </div>
    <p className="lv-hint">原件对照只在本页显示，不会发送给 AI 模型。仅有编辑权限的成员可以查看。</p>

    <details className="lv-disclosure" open={Boolean(terms || excludedTerms) || undefined}>
      <summary>调整脱敏范围</summary>
      <div className="lv-disclosure-body">
        <label className="lv-field"><span className="lv-field-label">还需要隐藏的内容</span>
          <textarea className="lv-textarea" aria-label="补充脱敏词" rows={2} value={terms} onChange={e => onTerms(e.target.value)} placeholder="每行一项，例如公司名称、联系人、项目代号" /></label>
        <label className="lv-field"><span className="lv-field-label">被误隐藏、需要恢复的内容</span>
          <textarea className="lv-textarea" aria-label="撤销过度脱敏词" rows={2} value={excludedTerms} onChange={e => onExcluded(e.target.value)} placeholder="每行一项，填写被错误遮盖的原文" />
          <span className="lv-hint">恢复后，这些内容会随正文一起发送给 AI 模型，请确认可以公开给模型。</span></label>
        <button className="lv-secondary" disabled={busy} onClick={onPreview}>更新预览</button>
      </div>
    </details>

    <div className="lv-stage-footer">
      <button className="lv-primary" disabled={busy} onClick={onConfirm}>已检查，确认脱敏<ArrowRight {...ic} /></button>
      <span>下一步：说明你的立场</span>
    </div>
  </section>;
}
