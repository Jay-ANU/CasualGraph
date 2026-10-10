import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import type { Block, Review } from './types';
import { findingStatus, revisionState } from './findingStatus';
import { SourceDetails } from './ReviewDetails';
import { findingTone, kindLabel, toneLabel } from './labels';
import type { Numbered } from './workspace';
import { isDecided, markerState } from './workspace';
import { Marker } from './Marker';
import { Redline, RichText } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';
import { labelOf, serverText, type Pair } from './i18n';

type Props = {
  item: Numbered; review: Review; block?: Block; clause: string; busy: boolean; selected: boolean;
  onSelect: () => void; onLocate: (blockId: string) => void;
  onDecision: (value: string, text: string, legalBasis: boolean, manual: boolean) => void;
};

const LAW_STATUS: Record<string, Pair> = { source_matched: ['已对照官方原文', 'Matched to official text'], model_cited: ['模型引用，待核对', 'Model-cited, to verify'] };
const DECISION_LABEL: Record<string, Pair> = { accepted: ['已采纳', 'Accepted'], draft: ['已入稿，待确认', 'In draft, awaiting your choice'], rejected: ['保留原文', 'Original kept'] };
const DECISION_NOTE: Record<string, Pair> = {
  accepted: ['已采纳，正文已写入修订', 'Accepted; the edit is now in the text'],
  rejected: ['保留原文，不作修改', 'Original kept; no change'],
};

/** One finding in the rail: a single line until selected, then its reasoning, basis and the revision to decide on. */
export function FindingItem({ item: { finding: f, n }, review: r, block, clause, busy, selected, onSelect, onLocate, onDecision }: Props) {
  const { tx } = useI18n();
  const decision = r.decisions[f.id];
  const decided = isDecided(decision);
  const original = block?.text || '';
  const [text, setText] = useState(decision?.text || f.suggested_text || original);
  const [editing, setEditing] = useState(false);
  const changed = text !== (decision?.text || f.suggested_text || original);
  const done = ['completed', 'partial'].includes(r.status);
  const status = findingStatus(f);
  const tone = findingTone(f);
  const legal = f.requires_legal_confirmation === true || ((r.engine_version || 0) >= 2 && f.kind === 'legal');
  const revisable = done && !!f.block_id;
  const drafting = editing || text !== f.suggested_text;
  const state = revisionState(f, { done, busy, text, original });
  const showRevision = revisable && (!!f.suggested_text || editing || decision?.decision === 'draft');
  const sources = f.citations.map(c => ({ c, source: r.sources.find(x => x.id === c.source_id) })).filter(x => x.source);
  const policies = f.policy_ids.map(id => r.policies.find(x => x.id === id)).filter(Boolean);
  const laws = f.law_refs || [];
  const unsupported = legal && f.evidence_status === 'unverified' ? tx('未提供可核对的法律依据。', 'No legal basis that can be checked was given.') : '';
  return <li id={`legal-finding-${f.id}`} className={`lv-note-item${selected ? ' is-selected' : ''}${decision?.decision === 'rejected' ? ' is-kept' : ''}`}>
    <button className="lv-note-row" aria-expanded={selected} onClick={onSelect}>
      <Marker n={n} finding={f} state={markerState(decision, false)} />
      <span className="lv-note-main">
        <span className="lv-note-meta">
          <span className={`lv-note-risk tone-${tone}`}>{toneLabel(tone)}</span><span aria-hidden="true">·</span><span>{kindLabel(f.kind) || tx('其他', 'Other')}</span>
          {status === 'quick' && <span className="lv-note-flag">{tx('未复核', 'Unverified')}</span>}
          {decision && decision.decision !== 'pending' && <span className={`lv-note-decision is-${decision.decision}`}>{labelOf(DECISION_LABEL, decision.decision)}</span>}
          <span className="lv-note-clause"><RichText text={clause} /></span>
        </span>
        <span className="lv-note-title">{f.title}</span>
        <span className="lv-note-impact">{f.impact}</span>
      </span>
    </button>
    {selected && <div className="lv-note-body">
      <div className="lv-note-sec"><span className="lv-note-label">{tx('风险说明', 'Why it matters')}</span><p>{f.reason}</p></div>
      {f.missing_facts.length > 0 && <div className="lv-note-sec"><span className="lv-note-label">{tx('待补充', 'Facts needed')}</span><p className="is-warn">{f.missing_facts.join('；')}</p></div>}
      {(laws.length > 0 || sources.length > 0 || policies.length > 0 || unsupported) && <div className="lv-note-sec"><span className="lv-note-label">{tx('依据', 'Basis')}</span>
        {laws.map((ref, i) => <div className="lv-basis" key={`${ref.law}-${ref.article}-${i}`}>
          <div className="lv-basis-head"><strong>{ref.law}{ref.article && ` ${ref.article}`}</strong>
            <span className={`lv-pill ${ref.status === 'source_matched' ? 'is-ok' : 'is-mid'}`}>{labelOf(LAW_STATUS, ref.status) ?? labelOf(LAW_STATUS, 'model_cited')}</span></div>
          {ref.point && <p>{ref.point}</p>}
        </div>)}
        {sources.map(({ c, source }, i) => <details className="lv-basis lv-citation" key={`${c.source_id}-${i}`}>
          <summary>{tx('官方原文：', 'Official text: ')}{source!.title}</summary>
          <blockquote>{c.supporting_quote}</blockquote>
          <a href={source!.url} target="_blank" rel="noreferrer noopener">{tx('查看来源', 'View source')}<ExternalLink {...ic} size={13} /></a>
          <SourceDetails source={source!} />
        </details>)}
        {policies.map(p => <details className="lv-basis lv-citation" key={p!.id}>
          <summary>{tx(`公司规范：${p!.title}（v${p!.version}）`, `Company policy: ${p!.title} (v${p!.version})`)}</summary>
          <p>{p!.text}</p><small>{tx('内部规范，非法律规定。', 'An internal policy, not law.')}</small>
        </details>)}
        {unsupported && <p className="is-warn">{unsupported}</p>}
      </div>}
      {(status === 'unconfirmed' || status === 'rejected') && f.verification_note && <div className="lv-note-sec"><span className="lv-note-label">{tx('模型复核意见', 'Model verification opinion')}</span><p className="lv-muted">{serverText(f.verification_note)}</p></div>}
      {decision?.source === 'model' && decision.decision === 'draft' && <p className="lv-note">{tx('这项修改已写入 AI 拟稿，你可以直接编辑、采纳或保留原文。', 'This edit is in the AI draft. You can edit it, accept it or keep the original.')}</p>}
      {showRevision && <div className="lv-note-sec">
        <span className="lv-note-label lv-note-label-row">{f.suggested_text && !drafting ? tx('修改建议', 'Suggested edit') : tx('修订文本', 'Revised text')}
          <button className="lv-text-button" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? tx('查看对比', 'Show changes') : tx('编辑', 'Edit')}</button></span>
        {editing ? <textarea className="lv-textarea lv-serif" aria-label={tx('编辑本段修订', 'Edit the revised paragraph')} rows={6} value={text} maxLength={12000} onChange={e => setText(e.target.value)} />
          : <div className="lv-redline-box" role="group" aria-label={tx('原文与修订对比', 'Original and revision compared')}><Redline before={original || f.original_quote} after={text} /></div>}
      </div>}
      {f.validation_warnings?.map((w, i) => <p key={i} className="lv-note is-warn">{serverText(w)}</p>)}
      {f.conflict_group && <p className="lv-note is-warn">{tx('该段落有多条修改建议，只能采纳其中一条。', 'This paragraph has more than one suggested edit; only one can be adopted.')}</p>}
      {(!decided || editing || changed) && <>
        <div className="lv-note-actions">
          {showRevision && <button className="lv-primary lv-btn-sm" aria-describedby={state.issue ? `finding-help-${f.id}` : undefined} disabled={!state.canSubmit}
            onClick={() => onDecision(state.decision, text, false, false)}>{editing || changed || !state.adoptable ? tx('保存修改', 'Save edit') : tx('采纳修改', 'Accept edit')}{state.adoptable && !editing && !changed && <kbd aria-hidden="true">A</kbd>}</button>}
          {revisable && !showRevision && <button className="lv-secondary lv-btn-sm" onClick={() => { setText(original); setEditing(true); }}>{tx('编辑本段', 'Edit paragraph')}</button>}
          <button className="lv-secondary lv-btn-sm" disabled={busy || !done} onClick={() => onDecision('rejected', '', false, false)}>{tx('保留原文', 'Keep original')}<kbd aria-hidden="true">R</kbd></button>
          {f.block_id && <button className="lv-text-button lv-narrow-only" onClick={() => onLocate(f.block_id!)}>{tx('在正文中查看', 'Show in text')}</button>}
        </div>
        {showRevision && state.issue && <p id={`finding-help-${f.id}`} className="lv-start-help">{state.issue}</p>}
        {changed && <p className="lv-start-help">{tx('保存后将更新正文和导出文件。', 'Save to update the document and exported file.')}</p>}
      </>}
      {decided && !editing && !changed && <div className={`lv-decided is-${decision!.decision}`} role="status">
        <span>{labelOf(DECISION_NOTE, decision!.decision)}</span>
        {decision!.decision !== 'rejected' && <button className="lv-text-button" disabled={busy || !done} onClick={() => onDecision('rejected', '', false, false)}>{tx('保留原文', 'Keep original')}</button>}
        <button className="lv-text-button" disabled={busy || !done} onClick={() => onDecision('pending', '', false, false)}>{tx('撤销', 'Undo')}</button>
      </div>}
    </div>}
  </li>;
}
