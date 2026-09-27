import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import type { Block, Review } from './types';
import { findingStatus, revisionState } from './findingStatus';
import { SourceDetails } from './ReviewDetails';
import { findingTone, KIND_LABEL, TONE_LABEL } from './labels';
import type { Numbered } from './workspace';
import { markerState } from './workspace';
import { Marker } from './Marker';
import { Redline, RichText } from './ui';
import { ic } from './icon';

type Props = {
  item: Numbered; review: Review; block?: Block; clause: string; busy: boolean; selected: boolean;
  legalOk: boolean; manualOk: boolean; onLegal: (value: boolean) => void; onManual: (value: boolean) => void;
  onSelect: () => void; onLocate: (blockId: string) => void;
  onDecision: (value: string, text: string, legalBasis: boolean, manual: boolean) => void;
};

const LAW_STATUS: Record<string, string> = { source_matched: '已对照官方原文', model_cited: '模型引用，待核对' };
const DECISION_LABEL: Record<string, string> = { accepted: '已采纳', draft: '人工修订', rejected: '保留原文' };
const DECISION_NOTE: Record<string, string> = { accepted: '已采纳，正文已写入修订', draft: '已保存为人工修订，导出前核验', rejected: '保留原文，不作修改' };

/** One finding in the rail: a single line until selected, then its reasoning, basis and the revision to decide on. */
export function FindingItem({ item: { finding: f, n }, review: r, block, clause, busy, selected, legalOk, manualOk, onLegal, onManual, onSelect, onLocate, onDecision }: Props) {
  const decision = r.decisions[f.id];
  const decided = Boolean(decision && decision.decision !== 'pending');
  const original = block?.text || '';
  const [text, setText] = useState(decision?.text || f.suggested_text || original);
  const [editing, setEditing] = useState(false);
  const done = ['completed', 'partial'].includes(r.status);
  const status = findingStatus(f);
  const tone = findingTone(f);
  const legal = f.requires_legal_confirmation === true || ((r.engine_version || 0) >= 2 && f.kind === 'legal');
  const revisable = done && status !== 'rejected' && !!f.block_id;
  const drafting = editing || text !== f.suggested_text;
  const state = revisionState(f, { done, busy, text, original, legalBasis: legalOk, manual: manualOk });
  const showRevision = revisable && (!!f.suggested_text || editing || decision?.decision === 'draft');
  const sources = f.citations.map(c => ({ c, source: r.sources.find(x => x.id === c.source_id) })).filter(x => x.source);
  const policies = f.policy_ids.map(id => r.policies.find(x => x.id === id)).filter(Boolean);
  const laws = f.law_refs || [];
  const unsupported = legal && f.evidence_status === 'unverified' ? '未提供可核对的法律依据。' : '';
  return <li id={`legal-finding-${f.id}`} className={`lv-note-item${selected ? ' is-selected' : ''}${decision?.decision === 'rejected' ? ' is-kept' : ''}`}>
    <button className="lv-note-row" aria-expanded={selected} onClick={onSelect}>
      <Marker n={n} finding={f} state={markerState(decision, false)} />
      <span className="lv-note-main">
        <span className="lv-note-meta">
          <span className={`lv-note-risk tone-${tone}`}>{TONE_LABEL[tone]}</span><span aria-hidden="true">·</span><span>{KIND_LABEL[f.kind] || '其他'}</span>
          {status === 'quick' && <span className="lv-note-flag">未复核</span>}
          {decided && <span className={`lv-note-decision is-${decision!.decision}`}>{DECISION_LABEL[decision!.decision]}</span>}
          <span className="lv-note-clause"><RichText text={clause} /></span>
        </span>
        <span className="lv-note-title">{f.title}</span>
        <span className="lv-note-impact">{f.impact}</span>
      </span>
    </button>
    {selected && <div className="lv-note-body">
      <div className="lv-note-sec"><span className="lv-note-label">风险说明</span><p>{f.reason}</p></div>
      {f.missing_facts.length > 0 && <div className="lv-note-sec"><span className="lv-note-label">待补充</span><p className="is-warn">{f.missing_facts.join('；')}</p></div>}
      {(laws.length > 0 || sources.length > 0 || policies.length > 0 || unsupported) && <div className="lv-note-sec"><span className="lv-note-label">依据</span>
        {laws.map((ref, i) => <div className="lv-basis" key={`${ref.law}-${ref.article}-${i}`}>
          <div className="lv-basis-head"><strong>{ref.law}{ref.article && ` ${ref.article}`}</strong>
            <span className={`lv-pill ${ref.status === 'source_matched' ? 'is-ok' : 'is-mid'}`}>{LAW_STATUS[ref.status] || LAW_STATUS.model_cited}</span></div>
          {ref.point && <p>{ref.point}</p>}
        </div>)}
        {sources.map(({ c, source }, i) => <details className="lv-basis lv-citation" key={`${c.source_id}-${i}`}>
          <summary>官方原文：{source!.title}</summary>
          <blockquote>{c.supporting_quote}</blockquote>
          <a href={source!.url} target="_blank" rel="noreferrer noopener">查看来源<ExternalLink {...ic} size={13} /></a>
          <SourceDetails source={source!} />
        </details>)}
        {policies.map(p => <details className="lv-basis lv-citation" key={p!.id}>
          <summary>公司规范：{p!.title}（v{p!.version}）</summary>
          <p>{p!.text}</p><small>内部规范，非法律规定。</small>
        </details>)}
        {unsupported && <p className="is-warn">{unsupported}</p>}
      </div>}
      {status === 'unconfirmed' && f.verification_note && <div className="lv-note-sec"><span className="lv-note-label">复核</span><p className="lv-muted">{f.verification_note}</p></div>}
      {showRevision && <div className="lv-note-sec">
        <span className="lv-note-label lv-note-label-row">{f.suggested_text && !drafting ? '修改建议' : '修订文本'}
          {!decided && <button className="lv-text-button" onClick={() => setEditing(!editing)}>{editing ? '查看对比' : '编辑'}</button>}</span>
        {editing ? <textarea className="lv-textarea lv-serif" aria-label="编辑本段修订" rows={6} value={text} maxLength={12000} onChange={e => { setText(e.target.value); onManual(false); }} />
          : <div className="lv-redline-box" role="group" aria-label="原文与修订对比"><Redline before={original || f.original_quote} after={decided && decision!.text ? decision!.text : text} /></div>}
      </div>}
      {f.validation_warnings?.map((w, i) => <p key={i} className="lv-note is-warn">{w}</p>)}
      {f.conflict_group && <p className="lv-note is-warn">该段落有多条修改建议，只能采纳其中一条。</p>}
      {f.cross_edit_status === 'unchecked' && f.revision_allowed && !decided && <p className="lv-note">{f.cross_edit_note || '与其他修改的交叉核对将在导出前完成。'}</p>}
      {!decided && <>
        {showRevision && legal && <label className="lv-check lv-check-sm"><input type="checkbox" checked={legalOk} onChange={e => onLegal(e.target.checked)} /><span>已核对引用法规的版本及适用性</span></label>}
        {showRevision && !state.adoptable && <label className="lv-check lv-check-sm"><input type="checkbox" checked={manualOk} onChange={e => onManual(e.target.checked)} /><span>保存为人工修订（导出前核验）</span></label>}
        <div className="lv-note-actions">
          {showRevision && <button className="lv-primary lv-btn-sm" aria-describedby={state.issue ? `finding-help-${f.id}` : undefined} disabled={!state.canSubmit}
            onClick={() => onDecision(state.decision, text, legalOk, manualOk)}>{state.adoptable ? '采纳修改' : '保存人工修订'}{state.adoptable && <kbd aria-hidden="true">A</kbd>}</button>}
          {revisable && !showRevision && <button className="lv-secondary lv-btn-sm" onClick={() => { setText(original); setEditing(true); }}>编辑本段</button>}
          <button className="lv-secondary lv-btn-sm" disabled={busy || !done} onClick={() => onDecision('rejected', '', false, false)}>保留原文<kbd aria-hidden="true">R</kbd></button>
          {f.block_id && <button className="lv-text-button lv-narrow-only" onClick={() => onLocate(f.block_id!)}>在正文中查看</button>}
        </div>
        {showRevision && state.issue && <p id={`finding-help-${f.id}`} className="lv-start-help">{state.issue}</p>}
      </>}
      {decided && <div className={`lv-decided is-${decision!.decision}`} role="status">
        <span>{DECISION_NOTE[decision!.decision]}</span>
        <button className="lv-text-button" disabled={busy || !done} onClick={() => onDecision('pending', '', false, false)}>撤销</button>
      </div>}
    </div>}
  </li>;
}
