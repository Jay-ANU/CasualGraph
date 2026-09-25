import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { Capabilities, Catalog, Review } from './types';
import { Icon, ModelSelect } from './parts';
import { findingCounts } from './findingStatus';
import { pendingDecisions } from './deskLogic';

/** Native modal supplies focus containment, Escape and return-focus behavior. */
export function ConfirmDialog({ title, children, confirmLabel, busy, onCancel, onConfirm }: {
  title: string; children: ReactNode; confirmLabel: string; busy: boolean;
  onCancel: () => void; onConfirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    // React autofocus runs while the native dialog is still closed. Focus after showModal.
    cancelRef.current?.focus();
    const frame = requestAnimationFrame(() => cancelRef.current?.focus());
    return () => { cancelAnimationFrame(frame); dialog?.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={ref} className="lv-dialog" aria-labelledby="lv-dialog-title"
    onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'));
      if (!items.length) { event.preventDefault(); return; }
      const index = items.indexOf(document.activeElement as HTMLElement);
      if ((event.shiftKey && index <= 0) || (!event.shiftKey && (index === items.length - 1 || index < 0))) {
        event.preventDefault(); items[event.shiftKey ? items.length - 1 : 0].focus();
      }
    }}
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <div className="lv-dialog-heading"><span className="lv-dialog-icon"><Icon name="lock" /></span>
      <button type="button" className="lv-icon" aria-label="关闭确认窗口" disabled={busy} onClick={onCancel}><Icon name="close" /></button></div>
    <h2 id="lv-dialog-title">{title}</h2><div className="lv-dialog-body">{children}</div>
    <div className="lv-dialog-actions"><button ref={cancelRef} type="button" className="lv-secondary" disabled={busy} onClick={onCancel}>取消</button>
      <button type="button" className="lv-primary" disabled={busy} onClick={onConfirm}>{busy && <span className="lv-spinner" />}{busy ? '正在处理…' : confirmLabel}</button></div>
  </dialog>;
}

export function Welcome({ caps, catalog, modelId, modelLoading, disabled, instructions, contractType,
  onUpload, onDrop, onInstructions, onScenario, onModel, onRefresh }: {
  caps: Capabilities | null; catalog: Catalog | null; modelId: string; modelLoading: boolean; disabled: boolean;
  instructions: string; contractType: string; onUpload: () => void; onDrop: (files: FileList) => void;
  onInstructions: (value: string) => void; onScenario: (type: string) => void; onModel: (id: string) => void; onRefresh: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const scenes = caps?.scenario_catalog?.scenarios.filter(s => ['采购合同', '销售合同', '服务合同', '保密协议'].includes(s.label)) || [];
  return <main id="legal-main" tabIndex={-1} className="lv-welcome">
    <div className="lv-welcome-content">
      <div className="lv-welcome-kicker"><span className="lv-intro-mark"><Icon name="document" /></span>合同审查工作台</div>
      <h1>今天需要审查哪份合同？</h1>
      <p className="lv-subtitle">读懂条款里的风险，把修改的决定留给你。</p>
      <div className="lv-welcome-grid">
        <section className={`lv-upload-zone ${dragging ? 'is-dragging' : ''}`} aria-label="上传合同"
          onDragOver={e => { e.preventDefault(); if (!disabled && e.dataTransfer.types.includes('Files')) setDragging(true); }}
          onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
          onDrop={e => { e.preventDefault(); setDragging(false); if (!disabled) onDrop(e.dataTransfer.files); }}>
          <div className="lv-file-symbol"><Icon name="document" /><span>合同</span></div>
          <h2>{dragging ? '松开鼠标，选择这份合同' : '从一份合同开始'}</h2>
          <p>拖入文件，或从设备中选择</p>
          <button type="button" className="lv-primary lv-upload-cta" disabled={disabled} onClick={onUpload} aria-label="选择一份合同开始"><Icon name="plus" />上传合同</button>
          <span className="lv-file-hint">DOCX / 文字型 PDF / TXT · 最大 10 MB</span>
          <div className="lv-upload-note"><Icon name="lock" /><span>下一步先确认上传授权，再检查脱敏内容。<br />此时不会向审查模型发送合同。</span></div>
        </section>
        <aside className="lv-outcomes" aria-label="审查流程说明">
          <p className="lv-section-kicker">上传之后</p>
          <div><span>01</span><section><h2>检查隐私与审查立场</h2><p>核对脱敏正文，明确你代表哪一方。</p></section></div>
          <div><span>02</span><section><h2>逐条看风险、依据和改法</h2><p>并排对照合同。证据不足的意见单独标明。</p></section></div>
          <div><span>03</span><section><h2>决定修改，再导出</h2><p>报告可单独导出；DOCX 合同支持带修订痕迹的 Word。</p></section></div>
        </aside>
      </div>
      <section className="lv-preferences" aria-label="可选审查偏好">
        <div className="lv-preferences-heading"><h2>提前告诉我们你的关注点</h2><span>可选，上传后仍可调整</span></div>
        <div className="lv-starters" aria-label="常用合同类型">{scenes.map(scene => <button type="button" key={scene.id} aria-pressed={scene.label === contractType} className={scene.label === contractType ? 'selected' : ''} onClick={() => onScenario(scene.label)}><Icon name="file" />{scene.label}</button>)}</div>
        <label className="lv-focus-label" htmlFor="legal-focus">希望重点检查什么？</label>
        <textarea id="legal-focus" aria-label="审查关注点" value={instructions} maxLength={1500} rows={2} onChange={e => onInstructions(e.target.value)} placeholder="例如：我担心先付款收不到货，希望补充验收和退款安排。" />
        <div className="lv-preferences-footer"><span>本轮审查模型</span><ModelSelect catalog={catalog} value={modelId} loading={modelLoading} disabled={disabled} onChange={onModel} onRefresh={onRefresh} /></div>
      </section>
      <p className="lv-trust"><Icon name="lock" />原件上传后端后解析、加密保存并脱敏，不是浏览器本地脱敏。模型外发需要另行授权。</p>
      <p className="lv-bottom-note">AI 辅助审查，不替代专业法律判断；不会自动签署或修改你的原文件。</p>
    </div>
  </main>;
}

export function WorkflowSteps({ step }: { step: number }) {
  return <nav className="lv-workflow" aria-label="合同审查步骤"><ol>{['检查隐私', '确认立场', '逐条审查', '核验与导出'].map((label, index) =>
    <li key={label} className={index === step ? 'current' : index < step ? 'complete' : ''} aria-current={index === step ? 'step' : undefined}>
      <span>{index < step ? <Icon name="check" /> : index + 1}</span><strong>{label}</strong>
    </li>)}</ol></nav>;
}

export function ReviewOverview({ review, onPending, onUnconfirmed, onExport }: {
  review: Review; onPending: () => void; onUnconfirmed: () => void; onExport: () => void;
}) {
  const counts = findingCounts(review.findings);
  const pending = pendingDecisions(review);
  const accepted = Object.values(review.decisions).filter(d => d.decision === 'accepted').length;
  return <section className="lv-result-summary" aria-label="本轮审查概览">
    <div className="lv-overview-heading"><div><p className="lv-section-kicker">本轮审查结果</p>
      <h2>{counts.actionable ? `有 ${counts.actionable} 项值得进一步处理` : '本轮没有形成可采用的审查意见'}</h2></div><span className={`lv-status ${review.status === 'partial' ? 'warning' : ''}`}>{review.status === 'partial' ? '部分完成' : '等待你复核'}</span></div>
    <p>{counts.high > 0 ? `先看 ${counts.high} 项有依据的重点，再处理待核实内容。` : '先核对意见与合同原文，再决定是否修改。'}{counts.actionable === 0 && ' 没有可采用的意见，不代表合同没有风险。'}</p>
    {review.status === 'partial' && <p className="lv-inline-warning">本轮检查尚未完整完成。未取得依据或未完成的部分，仍需人工核对。</p>}
    <div className="lv-overview-metrics"><button onClick={onPending}><strong>{pending}</strong><span>待你处理<Icon name="arrow-right" /></span></button><button onClick={onUnconfirmed}><strong>{counts.unconfirmed}</strong><span>待核实<Icon name="arrow-right" /></span></button><button onClick={onExport}><strong>{accepted}</strong><span>已纳入修订<Icon name="arrow-right" /></span></button></div>
    <div className="lv-overview-footer"><span>{review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length} / {review.coverage.length} 项检查 · {counts.rejected} 项候选被否定</span><button className="lv-text-button" onClick={onExport}>核验与导出<Icon name="arrow-right" /></button></div>
  </section>;
}
