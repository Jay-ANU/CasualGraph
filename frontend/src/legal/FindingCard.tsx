import { useState } from 'react';
import type { CSSProperties } from 'react';
import { Check, ChevronDown, ExternalLink } from 'lucide-react';
import type { Block, Finding, Review } from './types';
import { diffText } from './diff';
import { findingStatus, revisionState } from './findingStatus';
import { SourceDetails } from './ReviewDetails';
import { findingTone, KIND_LABEL, TONE_LABEL } from './labels';
import { clauseLabel } from './text';
import { RichText } from './ui';
import { ic } from './icon';

type Props = {
  finding: Finding; review: Review; block?: Block; busy: boolean; index: number; initiallyOpen: boolean;
  onLocate: (id: string) => void; onDecision: (value: string, text: string, legalBasis: boolean, manual: boolean) => void;
};

const LAW_STATUS: Record<string, string> = { source_matched: '已对照官方原文', model_cited: '模型引用，待核对' };

export function FindingCard({ finding: f, review: r, block, busy, index, initiallyOpen, onLocate, onDecision }: Props) {
  const decision = r.decisions[f.id];
  const original = block?.text || '';
  const [open, setOpen] = useState(initiallyOpen);
  const [text, setText] = useState(decision?.text || f.suggested_text || original);
  const [editing, setEditing] = useState(false);
  const [legalBasis, setLegalBasis] = useState(false);
  const [manual, setManual] = useState(false);
  const done = ['completed', 'partial'].includes(r.status);
  const status = findingStatus(f);
  const tone = findingTone(f);
  const legal = f.requires_legal_confirmation === true || ((r.engine_version || 0) >= 2 && f.kind === 'legal');
  const revisable = done && status !== 'rejected' && !!f.block_id;
  const drafting = editing || text !== f.suggested_text;
  const state = revisionState(f, { done, busy, text, original, legalBasis, manual });
  const accepted = decision?.decision === 'accepted';
  const sources = f.citations.map(c => ({ c, source: r.sources.find(x => x.id === c.source_id) })).filter(x => x.source);
  const policies = f.policy_ids.map(id => r.policies.find(x => x.id === id)).filter(Boolean);
  const laws = f.law_refs || [];
  const basis = legal && f.evidence_status === 'unverified' ? '未提供可核对的法律依据。' : '';
  const showRevision = revisable && (!!f.suggested_text || editing || decision?.decision === 'draft');
  return <article id={`legal-finding-${f.id}`} tabIndex={-1} data-block-id={f.block_id || undefined} style={{ '--i': Math.min(index, 8) } as CSSProperties}
    className={`lv-finding tone-${tone} ${accepted ? 'is-accepted' : ''} ${decision?.decision === 'rejected' ? 'is-kept' : ''}`}>
    <div className="lv-finding-meta">
      <span className={`lv-risk tone-${tone}`}>{TONE_LABEL[tone]}</span>
      <span className="lv-kind">{KIND_LABEL[f.kind] || '其他'}</span>
      {f.block_id && <button className="lv-clause-link" onClick={() => onLocate(f.block_id!)}>
        <span className="lv-sr">定位原文：</span><RichText text={clauseLabel(block) || `第 ${f.block_id} 段`} />
      </button>}
      {accepted && <span className="lv-decision"><Check {...ic} size={13} strokeWidth={2.25} />已采纳</span>}
      {decision?.decision === 'draft' && <span className="lv-decision is-draft">人工修订</span>}
      {decision?.decision === 'rejected' && <span className="lv-decision is-kept">保留原文</span>}
    </div>
    <h3><button aria-expanded={open} onClick={() => setOpen(!open)}><span>{f.title}</span><ChevronDown {...ic} size={18} /></button></h3>
    <p className="lv-impact">{f.impact}</p>
    {open && <div className="lv-finding-body">
      <dl className="lv-memo">
        {f.original_quote && <><dt>原文</dt><dd><blockquote className="lv-quote"><RichText text={f.original_quote} /></blockquote></dd></>}
        <dt>风险说明</dt><dd>{f.reason}</dd>
        {f.missing_facts.length > 0 && <><dt>待补充</dt><dd className="lv-memo-warn">{f.missing_facts.map((item, i) => <p key={i}>{item}</p>)}</dd></>}
        {(sources.length > 0 || policies.length > 0 || laws.length > 0 || basis) && <><dt>依据</dt><dd className="lv-basis">
          {laws.map((ref, i) => <div className="lv-lawref" key={`${ref.law}-${ref.article}-${i}`}>
            <div className="lv-lawref-head"><strong>{ref.law}{ref.article && ` ${ref.article}`}</strong>
              <span className={`lv-chip ${ref.status === 'source_matched' ? 'is-ok' : 'is-mid'}`}>{LAW_STATUS[ref.status] || LAW_STATUS.model_cited}</span></div>
            {ref.point && <p>{ref.point}</p>}
          </div>)}
          {sources.map(({ c, source }, i) => <details className="lv-citation" key={`${c.source_id}-${i}`}>
            <summary>官方原文：{source!.title}</summary>
            <blockquote>{c.supporting_quote}</blockquote>
            <a href={source!.url} target="_blank" rel="noreferrer noopener">查看来源<ExternalLink {...ic} size={13} /></a>
            <SourceDetails source={source!} />
          </details>)}
          {policies.map(p => <details className="lv-citation" key={p!.id}>
            <summary>公司规范：{p!.title}（v{p!.version}）</summary>
            <p>{p!.text}</p><small>内部规范，非法律规定。</small>
          </details>)}
          {basis && <p className="lv-memo-warn">{basis}</p>}
        </dd></>}
        {f.verification_note && <><dt>复核</dt><dd className="lv-memo-muted">{f.verification_note}</dd></>}
        {showRevision && <><dt>{f.suggested_text && !drafting ? '修改建议' : '修订文本'}</dt><dd>
          <div className="lv-suggestion">
            {editing ? <textarea className="lv-textarea" aria-label="编辑本段修订" rows={6} value={text} maxLength={12000} onChange={e => { setText(e.target.value); setManual(false); }} />
              : <div className="lv-diff" role="group" aria-label="原文与修订对比">{diffText(original || f.original_quote, text).map((part, i) => part.kind === 'del' ? <del key={i}><span className="lv-sr">删除：</span>{part.text}</del> : part.kind === 'ins' ? <ins key={i}><span className="lv-sr">新增：</span>{part.text}</ins> : <span key={i}>{part.text}</span>)}</div>}
            <button className="lv-text-button lv-suggestion-edit" onClick={() => setEditing(!editing)}>{editing ? '查看对比' : '编辑'}</button>
          </div>
        </dd></>}
      </dl>
      {f.validation_warnings?.map((w, i) => <p key={i} className="lv-note is-warn">{w}</p>)}
      {f.conflict_group && <p className="lv-note is-warn">该段落存在多条修改建议，仅可采纳其一。</p>}
      {f.cross_edit_status === 'unchecked' && f.revision_allowed && <p className="lv-note">{f.cross_edit_note || '尚未完成与其他修改的交叉核对；导出前仍会核验实际选择的修改组合。'}</p>}
      {revisable && !showRevision && <button className="lv-text-button" onClick={() => { setText(decision?.text || original); setEditing(true); }}>编辑本段</button>}
      {showRevision && (legal || !state.adoptable) ? <div className="lv-confirms">
        {legal && <label className="lv-check"><input type="checkbox" checked={legalBasis} onChange={e => setLegalBasis(e.target.checked)} /><span>已核对引用法规的版本及适用性</span></label>}
        {!state.adoptable && <label className="lv-check"><input type="checkbox" checked={manual} onChange={e => setManual(e.target.checked)} /><span>保存为人工修订（导出前核验）</span></label>}
      </div> : null}
      <div className="lv-finding-actions">
        {showRevision && <button className="lv-primary lv-btn-sm" aria-describedby={state.issue && !accepted ? `finding-help-${f.id}` : undefined} disabled={!state.canSubmit || accepted}
          onClick={() => onDecision(state.decision, text, legalBasis, manual)}>{accepted ? '已采纳' : state.adoptable ? '采纳修改' : '保存人工修订'}</button>}
        <button className="lv-secondary lv-btn-sm" disabled={busy || !done || decision?.decision === 'rejected'} onClick={() => onDecision('rejected', '', false, false)}>保留原文</button>
        {decision && <button className="lv-text-button" disabled={busy || !done} onClick={() => onDecision('pending', '', false, false)}>撤销</button>}
        {showRevision && state.issue && !accepted && <span id={`finding-help-${f.id}`} className="lv-start-help">{state.issue}</span>}
      </div>
    </div>}
  </article>;
}
