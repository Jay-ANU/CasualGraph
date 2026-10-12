import { useEffect } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { ArrowRight, FileSearch } from 'lucide-react';
import type { Answer, Block, Finding, Review } from './types';
import { revisionState } from './findingStatus';
import { pendingDecisions } from './deskLogic';
import { findingTone, researchGaps, reviewOutcome, tierOf, toneLabel } from './labels';
import type { Numbered, ToneFilter } from './workspace';
import { filterByTone, isDecided, stepFinding, TONE_FILTERS, toneCounts } from './workspace';
import { FindingItem } from './FindingItem';
import { FollowUp } from './FollowUp';
import { ReviewDetails } from './ReviewDetails';
import { ReviewMemo } from './ReviewMemo';
import { ReviewIssue } from './ReviewStatus';
import { CountUp } from './ui';
import { ic } from './icon';
import { pick, useI18n } from '../i18n/core';
import { plural } from './i18n';

export type RailTab = 'memo' | 'notes' | 'qa' | 'basis';

type Props = {
  review: Review; blocks: Block[]; open: Numbered[]; clauseOf: (blockId: string | null) => string;
  selected: string | null; tone: ToneFilter; tab: RailTab; busy: boolean; followup: boolean;
  answers: Answer[]; question: string; questionBusy: boolean; questionConsent: boolean;
  onTab: (tab: RailTab) => void; onTone: (tone: ToneFilter) => void; onSelect: (id: string) => void; onLocate: (blockId: string) => void;
  onSource?: (blockId: string) => void;
  onDecision: (f: Finding, value: string, text: string, legalBasis: boolean, manual: boolean) => void;
  onExport: () => void; onResume: () => void; onHint: (text: string) => void;
  onQuestion: (value: string) => void; onQuestionConsent: (value: boolean) => void; onAsk: () => void;
};

const typing = (target: EventTarget | null) => target instanceof HTMLElement && Boolean(target.closest('input, textarea, select, [contenteditable="true"]'));

function Notes(p: Props & { done: boolean }) {
  const { tx } = useI18n();
  const counts = toneCounts(p.open);
  const shown = filterByTone(p.open, p.tone);
  const ids = shown.map(x => x.finding.id);
  const handled = p.open.length - pendingDecisions(p.review);
  // J/K move through the list, A adopts the selected suggestion, R keeps the original:
  // only while the pointer or focus is in the desk and nothing is being typed.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target) || document.querySelector('dialog[open]')) return;
      const desk = document.querySelector('.lv-workspace');
      if (!desk || !(desk.matches(':hover') || desk.contains(document.activeElement))) return;
      const q = p, list = ids;
      const key = event.key.toLowerCase();
      if (key === 'j' || key === 'k') {
        const next = stepFinding(list, q.selected, key === 'j' ? 1 : -1);
        if (next) { event.preventDefault(); q.onSelect(next); }
        return;
      }
      const item = q.open.find(x => x.finding.id === q.selected);
      if (!item || (key !== 'a' && key !== 'r') || isDecided(q.review.decisions[item.finding.id])) return;
      const f = item.finding;
      const done = ['completed', 'partial'].includes(q.review.status);
      if (!done || q.busy) return;
      event.preventDefault();
      if (key === 'r') { q.onDecision(f, 'rejected', '', false, false); return; }
      const original = q.blocks.find(b => b.id === f.block_id)?.text || '';
      const text = q.review.decisions[f.id]?.text || f.suggested_text;
      const state = revisionState(f, { done, busy: q.busy, text, original });
      if (state.canSubmit) q.onDecision(f, 'accepted', text, false, false);
      else q.onHint(state.issue || pick('请在批注中补充修订文本。', 'Add revision text in the note.'));
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });
  return <>
    {p.open.length > 1 && <div className="lv-filters" role="group" aria-label={tx('按风险筛选', 'Filter by risk')}>
      {TONE_FILTERS.filter(t => t === 'all' || counts[t] > 0).map(t => <button key={t} aria-pressed={p.tone === t} className={p.tone === t ? 'selected' : ''} onClick={() => p.onTone(t)}>
        {t !== 'all' && <i className={`lv-sq tone-${t}`} aria-hidden="true" />}{t === 'all' ? tx('全部', 'All') : toneLabel(t)}<span className="lv-mono">{counts[t]}</span>
      </button>)}
    </div>}
    <div className="lv-rail-body lv-notes" id="legal-notes">
      {shown.length > 0 && <ol className="lv-note-list" aria-label={tx('批注', 'Notes')}>
        {shown.map(item => <FindingItem key={`${item.finding.id}-${p.review.decisions[item.finding.id]?.version || 0}`} item={item} review={p.review}
          block={p.blocks.find(b => b.id === item.finding.block_id)} clause={p.clauseOf(item.finding.block_id)} busy={p.busy} selected={p.selected === item.finding.id}
          onSelect={() => p.onSelect(item.finding.id)} onLocate={p.onLocate} onSource={p.onSource}
          onDecision={(value, text, legalBasis, manualEdit) => p.onDecision(item.finding, value, text, legalBasis, manualEdit)} />)}
      </ol>}
      {!p.open.length && <div className="lv-empty-result">
        <span className="lv-tile is-gray" aria-hidden="true"><FileSearch size={28} strokeWidth={1.5} /></span>
        <p>{p.done ? tx('未形成可采纳的修改意见。该结果不代表合同不存在风险。', 'No edits were proposed for adoption. This does not mean the contract carries no risk.') : tx('暂无审查意见。', 'No findings yet.')}</p>
      </div>}
      {p.open.length > 0 && !shown.length && <div className="lv-empty-result"><p>{tx('没有符合条件的批注', 'No notes match this filter')}</p>
        <button className="lv-secondary lv-btn-sm" onClick={() => p.onTone('all')}>{tx('清除筛选', 'Clear filter')}</button></div>}
    </div>
    <div className="lv-rail-foot">
      <div className="lv-handled">
        <span>{tx('已处理 ', 'Handled ')}<strong className="lv-mono"><CountUp value={handled} />/{p.open.length}</strong></span>
        <span className="lv-handled-bar" aria-hidden="true"><i style={{ width: `${p.open.length ? Math.round((handled / p.open.length) * 100) : 100}%` }} /></span>
        <button className="lv-primary lv-btn-sm" disabled={!p.done || p.busy} onClick={p.onExport}>{tx('导出', 'Export')}<ArrowRight {...ic} size={14} /></button>
      </div>
      <p className="lv-keys" aria-hidden="true">{tx('J / K 切换 · A 采纳 · R 保留原文', 'J / K move · A accept · R keep original')}</p>
    </div>
  </>;
}

/** The finished review in the rail: how many findings, what needs attention first, and three views of it. */
export function ResultsPanel(p: Props) {
  const { tx } = useI18n();
  const done = ['completed', 'partial'].includes(p.review.status);
  const outcome = reviewOutcome(p.review);
  const issueShown = p.review.resumable || Boolean(p.review.error) || ['failed', 'cancelled'].includes(p.review.status);
  const urgent = p.open.filter(x => findingTone(x.finding) === 'high' && !isDecided(p.review.decisions[x.finding.id])).length;
  const memo = Boolean(p.review.memo);
  const tabs: [RailTab, string][] = [...(memo ? [['memo', tx('意见书', 'Memo')] as [RailTab, string]] : []),
    ['notes', tx(`批注 ${p.open.length}`, `Notes ${p.open.length}`)], ...(p.followup ? [['qa', tx('问答', 'Q&A')] as [RailTab, string]] : []), ['basis', tx('依据', 'Basis')]];
  // A review without a memo (standard, deep, or from before chat-style reviews) opens on its notes.
  const tab: RailTab = p.tab === 'memo' && !memo ? 'notes' : p.tab;
  const move = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    const i = tabs.findIndex(([value]) => value === tab);
    const next = tabs[(i + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length][0];
    p.onTab(next);
    requestAnimationFrame(() => document.getElementById(`legal-tab-${next}`)?.focus());
  };
  const gaps = researchGaps(p.review);
  return <section className="lv-rail-panel lv-results" aria-label={tx('审查结果', 'Review results')}>
    <div className="lv-rail-head">
      <div className="lv-results-count">
        <span className="lv-big-number"><CountUp value={p.open.length} /></span><span className="lv-results-unit">{tx('条批注', p.open.length === 1 ? 'note' : 'notes')}</span>
        {urgent > 0 && <span className="lv-urgent">{tx(`${urgent} 项高风险建议优先处理`, `${plural(urgent, 'high-risk item')} to handle first`)}</span>}
      </div>
      {issueShown ? <ReviewIssue review={p.review} busy={p.busy} onResume={p.onResume} />
        : outcome === 'failed_steps' ? <p className="lv-note is-warn">{tx('部分审查步骤未完成，未完成部分不能据此排除风险。', 'Some review steps did not finish; they cannot rule out risk.')}</p>
        : outcome === 'evidence_gaps' ? <p className="lv-note">{tx(`${gaps} 个法律问题未取得官方原文，相关依据标注为“模型引用，待核对”。`,
          `No official text was found for ${plural(gaps, 'legal issue')}; the related basis is marked “model-cited, to verify”.`)}</p> : null}
      {['ultra_fast', 'fast'].includes(tierOf(p.review)) && done && <p className="lv-note">{tx('修订稿已就绪，可直接阅读、编辑和导出。模型拟稿尚未独立复核。',
        'Your draft is ready to read, edit and export. The model’s edits have not been independently verified.')}</p>}
      <div className="lv-tabs" role="tablist" aria-label={tx('审查结果视图', 'Result views')} onKeyDown={move}>
        {tabs.map(([value, label]) => <button key={value} id={`legal-tab-${value}`} role="tab" aria-selected={tab === value} aria-controls="legal-tabpanel"
          tabIndex={tab === value ? 0 : -1} className={tab === value ? 'selected' : ''} onClick={() => p.onTab(value)}>{label}</button>)}
      </div>
    </div>
    <div id="legal-tabpanel" role="tabpanel" aria-labelledby={`legal-tab-${tab}`} className="lv-tabpanel">
      {tab === 'memo' && <ReviewMemo review={p.review} blocks={p.blocks} onLocate={p.onLocate} />}
      {tab === 'notes' && <Notes {...p} done={done} />}
      {tab === 'qa' && <FollowUp review={p.review} blocks={p.blocks} answers={p.answers} question={p.question} busy={p.questionBusy} consent={p.questionConsent}
        onQuestion={p.onQuestion} onConsent={p.onQuestionConsent} onAsk={p.onAsk} onLocate={p.onLocate} />}
      {tab === 'basis' && <div className="lv-rail-body"><ReviewDetails review={p.review} onLocate={p.onLocate} /></div>}
    </div>
  </section>;
}
