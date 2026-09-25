import { useState } from 'react';
import { ArrowRight, BookOpen, Check, ChevronDown, ExternalLink } from 'lucide-react';
import type { Block, Finding, Review } from './types';
import { diffText } from './diff';
import { findingStatus } from './findingStatus';
import { SourceDetails } from './ReviewDetails';
import { findingTone, KIND_LABEL, TONE_LABEL } from './labels';
import { clauseLabel } from './text';
import { RichText } from './ui';
import { ic } from './icon';

type Props = {
  finding: Finding; review: Review; block?: Block; busy: boolean; initiallyOpen: boolean;
  onLocate: (id: string) => void; onDecision: (value: string, text: string, legalBasis: boolean, manual: boolean) => void;
};

export function FindingCard({ finding: f, review: r, block, busy, initiallyOpen, onLocate, onDecision }: Props) {
  const decision = r.decisions[f.id];
  const [open, setOpen] = useState(initiallyOpen);
  const [text, setText] = useState(decision?.text || f.suggested_text);
  const [editing, setEditing] = useState(false);
  const [legalBasis, setLegalBasis] = useState(false);
  const [manual, setManual] = useState(false);
  const done = ['completed', 'partial'].includes(r.status);
  const changed = text !== f.suggested_text;
  const status = findingStatus(f);
  const tone = findingTone(f);
  const original = block?.text || '';
  const needsLegal = f.requires_legal_confirmation === true || ((r.engine_version || 0) >= 2 && f.kind === 'legal');
  const canAccept = status !== 'rejected' && done && !busy && !!f.block_id && !!f.suggested_text && !!text.trim()
    && f.revision_allowed !== false && f.missing_facts.length === 0 && f.evidence_status !== 'unverified'
    && (!needsLegal || legalBasis) && (!changed || manual);
  const acceptIssue = !done ? '审查完成后才能处理修改。'
    : status === 'rejected' || f.revision_allowed === false ? '这条建议没有通过复核，不能直接采纳。'
    : !f.block_id || !f.suggested_text ? '这条意见没有可直接替换的段落，请人工处理。'
    : f.missing_facts.length ? '请先核实上方“还需要确认”的信息。'
    : f.evidence_status === 'unverified' ? '依据尚未核实，暂不能直接采纳。'
    : !text.trim() ? '修改后的条款不能为空。'
    : needsLegal && !legalBasis ? '采纳前，请勾选确认已核对引用规定的版本和适用范围。'
    : changed && !manual ? '你编辑了建议内容，请勾选确认保存为待复核的手工修改。' : '';
  const accepted = decision?.decision === 'accepted';
  return <article id={`legal-finding-${f.id}`} tabIndex={-1} data-block-id={f.block_id || undefined}
    className={`lv-finding tone-${tone} ${accepted ? 'is-accepted' : ''} ${decision?.decision === 'rejected' ? 'is-kept' : ''}`}>
    <div className="lv-finding-tags">
      <span className={`lv-risk tone-${tone}`}>{TONE_LABEL[tone]}</span>
      <span className="lv-kind">{KIND_LABEL[f.kind] || '其他'}</span>
      {accepted && <span className="lv-decision"><Check {...ic} size={13} strokeWidth={2.25} />已纳入修订</span>}
      {decision?.decision === 'draft' && <span className="lv-decision is-draft">手工修改 · 待复核</span>}
      {decision?.decision === 'rejected' && <span className="lv-decision is-kept">已保留原文</span>}
    </div>
    <h3><button aria-expanded={open} onClick={() => setOpen(!open)}><span>{f.title}</span><ChevronDown {...ic} size={18} /></button></h3>
    <p className="lv-impact">{f.impact}</p>
    {f.block_id && <button className="lv-source-link" onClick={() => onLocate(f.block_id!)}>
      <span className="lv-sr">定位原文：</span><RichText text={clauseLabel(block) || `第 ${f.block_id} 段`} /><ArrowRight {...ic} size={14} />
    </button>}
    {open && <div className="lv-finding-body">
      {f.original_quote && <figure className="lv-quote"><figcaption>合同原文</figcaption><blockquote><RichText text={f.original_quote} /></blockquote></figure>}
      <section><h4>为什么需要关注</h4><p>{f.reason}</p></section>
      {f.missing_facts.length > 0 && <div className="lv-note is-warn"><strong>还需要确认</strong>{f.missing_facts.map((item, i) => <p key={i}>{item}</p>)}</div>}
      {f.validation_warnings?.map((w, i) => <p key={i} className="lv-note is-warn">{w}</p>)}
      {f.conflict_group && <p className="lv-note is-warn">这一段还有其他修改方案，请选择其一或手工合并；相互覆盖的建议不会同时写入。</p>}
      {(f.citations.length > 0 || f.policy_ids.length > 0) && <section className="lv-basis"><h4>依据</h4>
        {f.citations.map((citation, i) => { const source = r.sources.find(x => x.id === citation.source_id); return source ? <details className="lv-citation" key={`${citation.source_id}-${i}`}>
          <summary><BookOpen {...ic} size={14} />{source.title}</summary>
          <blockquote>{citation.supporting_quote}</blockquote>
          <a href={source.url} target="_blank" rel="noreferrer noopener">打开来源原文<ExternalLink {...ic} size={13} /></a>
          <SourceDetails source={source} />
        </details> : null; })}
        {f.policy_ids.map(id => { const p = r.policies.find(x => x.id === id); return p ? <details className="lv-citation" key={id}>
          <summary><BookOpen {...ic} size={14} />公司规范：{p.title} · 第 {p.version} 版</summary>
          <p>{p.text}</p><small>这是公司内部要求，不是法律规定。</small>
        </details> : null; })}
      </section>}
      {f.evidence_status === 'unverified' && <p className="lv-note is-warn">依据不足或复核未通过，暂不能直接采纳。</p>}
      {f.verification_note && <details className="lv-disclosure lv-verification"><summary>复核说明</summary><div className="lv-disclosure-body"><p>{f.verification_note}</p></div></details>}
      {f.suggested_text && <section className="lv-suggestion">
        <div className="lv-suggestion-head"><h4>建议修改为</h4>
          <button className="lv-text-button" onClick={() => setEditing(!editing)}>{editing ? '查看修改对比' : '编辑建议'}</button></div>
        {editing ? <label className="lv-field"><span className="lv-field-label">本段修改后的完整文字</span>
          <textarea className="lv-textarea" aria-label="编辑本段建议" rows={6} value={text} maxLength={12000} onChange={e => { setText(e.target.value); setManual(false); setLegalBasis(false); }} /></label>
          : <div className="lv-diff" role="group" aria-label="原文与建议修改对比">{diffText(original || f.original_quote, text).map((part, i) => part.kind === 'del' ? <del key={i}><span className="lv-sr">删除：</span>{part.text}</del> : part.kind === 'ins' ? <ins key={i}><span className="lv-sr">新增：</span>{part.text}</ins> : <span key={i}>{part.text}</span>)}</div>}
        <p className="lv-diff-legend"><del>删除</del><ins>新增</ins><span>导出 Word 合同时保留修订痕迹</span></p>
      </section>}
      {needsLegal && f.revision_allowed !== false && f.suggested_text && <label className="lv-check"><input type="checkbox" checked={legalBasis} onChange={e => setLegalBasis(e.target.checked)} /><span>我已核对所引规定的版本和适用范围。</span></label>}
      {changed && f.suggested_text && <label className="lv-check"><input type="checkbox" checked={manual} onChange={e => setManual(e.target.checked)} /><span>保存为待复核的手工修改；它不沿用原建议的核验结果。</span></label>}
      {acceptIssue && !accepted && <p id={`finding-help-${f.id}`} className="lv-start-help">{acceptIssue}</p>}
      <div className="lv-finding-actions">
        <button className="lv-primary" aria-describedby={acceptIssue ? `finding-help-${f.id}` : undefined} disabled={!canAccept || accepted}
          onClick={() => onDecision(changed ? 'draft' : 'accepted', text, legalBasis, manual)}><Check {...ic} />{accepted ? '已纳入修订' : changed ? '保存手工修改' : '接受修改'}</button>
        <button className="lv-secondary" disabled={busy || !done || decision?.decision === 'rejected'} onClick={() => onDecision('rejected', '', false, false)}>保留原文</button>
        {decision && <button className="lv-text-button" disabled={busy || !done} onClick={() => onDecision('pending', '', false, false)}>撤销决定</button>}
      </div>
      {f.agent_title && <p className="lv-provenance">由“{f.agent_title}”提出，是否成立以本条复核结果为准。</p>}
    </div>}
  </article>;
}
