import { useState } from 'react';
import { Check, ChevronDown, ExternalLink } from 'lucide-react';
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
  const acceptIssue = !done ? '审查完成后方可操作。'
    : status === 'rejected' || f.revision_allowed === false ? '该建议未通过复核，不可采纳。'
    : !f.block_id || !f.suggested_text ? '无可替换段落，请人工处理。'
    : f.missing_facts.length ? '请先补充待确认信息。'
    : f.evidence_status === 'unverified' ? '依据未核实，暂不可采纳。'
    : !text.trim() ? '修订内容不能为空。'
    : needsLegal && !legalBasis ? '请先确认法规版本及适用性。'
    : changed && !manual ? '请确认保存为人工修订。' : '';
  const accepted = decision?.decision === 'accepted';
  const sources = f.citations.map(c => ({ c, source: r.sources.find(x => x.id === c.source_id) })).filter(x => x.source);
  const policies = f.policy_ids.map(id => r.policies.find(x => x.id === id)).filter(Boolean);
  return <article id={`legal-finding-${f.id}`} tabIndex={-1} data-block-id={f.block_id || undefined}
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
        {(sources.length > 0 || policies.length > 0) && <><dt>依据</dt><dd className="lv-basis">
          {sources.map(({ c, source }, i) => <details className="lv-citation" key={`${c.source_id}-${i}`}>
            <summary>{source!.title}</summary>
            <blockquote>{c.supporting_quote}</blockquote>
            <a href={source!.url} target="_blank" rel="noreferrer noopener">查看来源<ExternalLink {...ic} size={13} /></a>
            <SourceDetails source={source!} />
          </details>)}
          {policies.map(p => <details className="lv-citation" key={p!.id}>
            <summary>公司规范：{p!.title}（v{p!.version}）</summary>
            <p>{p!.text}</p><small>内部规范，非法律规定。</small>
          </details>)}
        </dd></>}
        {f.verification_note && <><dt>复核</dt><dd className="lv-memo-muted">{f.verification_note}</dd></>}
        {f.suggested_text && <><dt>修改建议</dt><dd>
          <div className="lv-suggestion">
            {editing ? <textarea className="lv-textarea" aria-label="编辑本段建议" rows={6} value={text} maxLength={12000} onChange={e => { setText(e.target.value); setManual(false); setLegalBasis(false); }} />
              : <div className="lv-diff" role="group" aria-label="原文与建议修改对比">{diffText(original || f.original_quote, text).map((part, i) => part.kind === 'del' ? <del key={i}><span className="lv-sr">删除：</span>{part.text}</del> : part.kind === 'ins' ? <ins key={i}><span className="lv-sr">新增：</span>{part.text}</ins> : <span key={i}>{part.text}</span>)}</div>}
            <button className="lv-text-button lv-suggestion-edit" onClick={() => setEditing(!editing)}>{editing ? '查看对比' : '编辑'}</button>
          </div>
        </dd></>}
      </dl>
      {f.validation_warnings?.map((w, i) => <p key={i} className="lv-note is-warn">{w}</p>)}
      {f.conflict_group && <p className="lv-note is-warn">该段落存在多条修改建议，仅可采纳其一。</p>}
      {(needsLegal && f.revision_allowed !== false && f.suggested_text) || (changed && f.suggested_text) ? <div className="lv-confirms">
        {needsLegal && f.revision_allowed !== false && f.suggested_text && <label className="lv-check"><input type="checkbox" checked={legalBasis} onChange={e => setLegalBasis(e.target.checked)} /><span>已核对引用法规的版本及适用性</span></label>}
        {changed && f.suggested_text && <label className="lv-check"><input type="checkbox" checked={manual} onChange={e => setManual(e.target.checked)} /><span>保存为人工修订（需重新核验）</span></label>}
      </div> : null}
      <div className="lv-finding-actions">
        <button className="lv-primary lv-btn-sm" aria-describedby={acceptIssue && !accepted ? `finding-help-${f.id}` : undefined} disabled={!canAccept || accepted}
          onClick={() => onDecision(changed ? 'draft' : 'accepted', text, legalBasis, manual)}>{accepted ? '已采纳' : changed ? '保存人工修订' : '采纳修改'}</button>
        <button className="lv-secondary lv-btn-sm" disabled={busy || !done || decision?.decision === 'rejected'} onClick={() => onDecision('rejected', '', false, false)}>保留原文</button>
        {decision && <button className="lv-text-button" disabled={busy || !done} onClick={() => onDecision('pending', '', false, false)}>撤销</button>}
        {acceptIssue && !accepted && <span id={`finding-help-${f.id}`} className="lv-start-help">{acceptIssue}</span>}
      </div>
    </div>}
  </article>;
}
