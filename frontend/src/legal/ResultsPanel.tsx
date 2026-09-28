import { useI18n } from '../i18n/useI18n';
import { useEffect, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { ArrowRight, ChevronDown } from 'lucide-react';
import type { Answer, Block, Finding, Review } from './types';
import { revisionState } from './findingStatus';
import { pendingDecisions } from './deskLogic';
import { findingTone, researchGaps, reviewOutcome, tierOf, TONE_LABEL } from './labels';
import type { Numbered, ToneFilter } from './workspace';
import { filterByTone, isDecided, stepFinding, TONE_FILTERS, toneCounts } from './workspace';
import { FindingItem } from './FindingItem';
import { FollowUp } from './FollowUp';
import { ReviewDetails } from './ReviewDetails';
import { ReviewIssue } from './ReviewStatus';
import { CountUp, RichText } from './ui';
import { NoMatchSheet } from './art';
import { ic } from './icon';

export type RailTab = 'notes' | 'qa' | 'basis';

type Props = {
  review: Review; blocks: Block[]; open: Numbered[]; excluded: Finding[]; clauseOf: (blockId: string | null) => string;
  selected: string | null; tone: ToneFilter; tab: RailTab; busy: boolean; followup: boolean;
  answers: Answer[]; question: string; questionBusy: boolean; questionConsent: boolean;
  onTab: (tab: RailTab) => void; onTone: (tone: ToneFilter) => void; onSelect: (id: string) => void; onLocate: (blockId: string) => void;
  onDecision: (f: Finding, value: string, text: string, legalBasis: boolean, manual: boolean) => void;
  onExport: () => void; onResume: () => void; onHint: (text: string) => void;
  onQuestion: (value: string) => void; onQuestionConsent: (value: boolean) => void; onAsk: () => void;
};

const typing = (target: EventTarget | null) => target instanceof HTMLElement && Boolean(target.closest('input, textarea, select, [contenteditable="true"]'));

function Notes(p: Props & { done: boolean }) {
  const { t } = useI18n();
  const [legal, setLegal] = useState<Record<string, boolean>>({});
  const [manual, setManual] = useState<Record<string, boolean>>({});
  const [showExcluded, setShowExcluded] = useState(false);
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
      const q = p, ok = legal, list = ids;
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
      const state = revisionState(f, { done, busy: q.busy, text: f.suggested_text, original, legalBasis: Boolean(ok[f.id]), manual: false });
      if (state.adoptable && !state.issue) q.onDecision(f, 'accepted', f.suggested_text, Boolean(ok[f.id]), false);
      else q.onHint(state.issue || '这条意见需在批注中编辑后保存为人工修订。');
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });
  return <>
    {p.open.length > 1 && <div className="lv-filters" role="group" aria-label={t("按风险筛选")}>
      {TONE_FILTERS.filter(t => t === 'all' || counts[t] > 0).map(tone => <button key={tone} aria-pressed={p.tone === tone} className={p.tone === tone ? 'selected' : ''} onClick={() => p.onTone(tone)}>
        {tone !== 'all' && <i className={`lv-sq tone-${tone}`} aria-hidden="true" />}{tone === 'all' ? t("全部") : t(TONE_LABEL[tone])}<span className="lv-mono">{counts[tone]}</span>
      </button>)}
    </div>}
    <div className="lv-rail-body lv-notes" id="legal-notes">
      {shown.length > 0 && <ol className="lv-note-list" aria-label={t("批注")}>
        {shown.map(item => <FindingItem key={`${item.finding.id}-${p.review.decisions[item.finding.id]?.version || 0}`} item={item} review={p.review}
          block={p.blocks.find(b => b.id === item.finding.block_id)} clause={p.clauseOf(item.finding.block_id)} busy={p.busy} selected={p.selected === item.finding.id}
          legalOk={Boolean(legal[item.finding.id])} manualOk={Boolean(manual[item.finding.id])}
          onLegal={value => setLegal(state => ({ ...state, [item.finding.id]: value }))} onManual={value => setManual(state => ({ ...state, [item.finding.id]: value }))}
          onSelect={() => p.onSelect(item.finding.id)} onLocate={p.onLocate}
          onDecision={(value, text, legalBasis, manualEdit) => p.onDecision(item.finding, value, text, legalBasis, manualEdit)} />)}
      </ol>}
      {!p.open.length && <div className="lv-empty-result">
        <NoMatchSheet />
        <p>{p.done ? t("未形成可采纳的修改意见。该结果不代表合同不存在风险。") : t("暂无审查意见。")}</p>
      </div>}
      {p.open.length > 0 && !shown.length && <div className="lv-empty-result"><p>{t("没有符合条件的批注")}</p>
        <button className="lv-secondary lv-btn-sm" onClick={() => p.onTone('all')}>{t("清除筛选")}</button></div>}
      {p.excluded.length > 0 && <div className="lv-excluded">
        <button className="lv-excluded-toggle" aria-expanded={showExcluded} onClick={() => setShowExcluded(!showExcluded)}>{t("复核排除")}{' '}{p.excluded.length}{' '}{t("项")}<ChevronDown {...ic} size={15} /></button>
        {showExcluded && <ul>{p.excluded.map(f => <li key={f.id}>
          <strong>{f.title}<span className="lv-muted"> · <RichText text={p.clauseOf(f.block_id)} /></span></strong>
          {f.verification_note && <p>{t("复核认为：")}{f.verification_note}</p>}
        </li>)}</ul>}
      </div>}
    </div>
    {p.open.length > 0 && <div className="lv-rail-foot">
      <div className="lv-handled">
        <span>{t("已处理")}{' '}<strong className="lv-mono"><CountUp value={handled} />/{p.open.length}</strong></span>
        <span className="lv-handled-bar" aria-hidden="true"><i style={{ width: `${Math.round((handled / p.open.length) * 100)}%` }} /></span>
        <button className="lv-primary lv-btn-sm" disabled={!p.done} onClick={p.onExport}>{t("导出")}<ArrowRight {...ic} size={14} /></button>
      </div>
      <p className="lv-keys" aria-hidden="true">{t("J / K 切换 · A 采纳 · R 保留原文")}</p>
    </div>}
  </>;
}

/** The finished review in the rail: how many findings, what needs attention first, and three views of it. */
export function ResultsPanel(p: Props) {
  const { t } = useI18n();
  const done = ['completed', 'partial'].includes(p.review.status);
  const outcome = reviewOutcome(p.review);
  const issueShown = p.review.resumable || Boolean(p.review.error) || ['failed', 'cancelled'].includes(p.review.status);
  const urgent = p.open.filter(x => findingTone(x.finding) === 'high' && !isDecided(p.review.decisions[x.finding.id])).length;
  const tabs: [RailTab, string][] = [['notes', `${t('批注')} ${p.open.length}`], ...(p.followup ? [['qa', '问答'] as [RailTab, string]] : []), ['basis', '依据']];
  const move = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    const i = tabs.findIndex(([value]) => value === p.tab);
    const next = tabs[(i + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length][0];
    p.onTab(next);
    requestAnimationFrame(() => document.getElementById(`legal-tab-${next}`)?.focus());
  };
  return <section className="lv-rail-panel lv-results" aria-label={t("审查结果")}>
    <div className="lv-rail-head">
      <div className="lv-results-count">
        <span className="lv-big-number"><CountUp value={p.open.length} /></span><span className="lv-results-unit">{t("条批注")}</span>
        {urgent > 0 && <span className="lv-urgent">{urgent}{' '}{t("项高风险建议优先处理")}</span>}
      </div>
      {issueShown ? <ReviewIssue review={p.review} busy={p.busy} onResume={p.onResume} />
        : outcome === 'failed_steps' ? <p className="lv-note is-warn">{t("部分审查步骤未完成，未完成部分不能据此排除风险。")}</p>
        : outcome === 'evidence_gaps' ? <p className="lv-note">{researchGaps(p.review)}{' '}{t("个法律问题未取得官方原文，相关依据标注为“模型引用，待核对”。")}</p> : null}
      {tierOf(p.review) === 'ultra_fast' && done && <p className="lv-note">{t("极速审查未检索法规、未经独立复核，采用前请逐条确认。")}</p>}
      <div className="lv-tabs" role="tablist" aria-label={t("审查结果视图")} onKeyDown={move}>
        {tabs.map(([value, label]) => <button key={value} id={`legal-tab-${value}`} role="tab" aria-selected={p.tab === value} aria-controls="legal-tabpanel"
          tabIndex={p.tab === value ? 0 : -1} className={p.tab === value ? 'selected' : ''} onClick={() => p.onTab(value)}>{t(label)}</button>)}
      </div>
    </div>
    <div id="legal-tabpanel" role="tabpanel" aria-labelledby={`legal-tab-${p.tab}`} className="lv-tabpanel">
      {p.tab === 'notes' && <Notes {...p} done={done} />}
      {p.tab === 'qa' && <FollowUp review={p.review} blocks={p.blocks} answers={p.answers} question={p.question} busy={p.questionBusy} consent={p.questionConsent}
        onQuestion={p.onQuestion} onConsent={p.onQuestionConsent} onAsk={p.onAsk} onLocate={p.onLocate} />}
      {p.tab === 'basis' && <div className="lv-rail-body"><ReviewDetails review={p.review} onLocate={p.onLocate} /></div>}
    </div>
  </section>;
}
