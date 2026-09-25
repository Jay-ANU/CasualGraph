import { ArrowRight, RotateCcw } from 'lucide-react';
import type { Collaboration, Review } from './types';
import { findingCounts, findingStatus } from './findingStatus';
import { AGENT_STATUS, findingTone, TONE_LABEL } from './labels';
import type { Tone } from './labels';
import { ReviewingSheet } from './art';
import { ic } from './icon';

export function Lanes({ collaboration, label }: { collaboration: Collaboration; label?: string }) {
  return <ul className="lv-lanes" aria-label={label}>
    {collaboration.agents.map(agent => <li key={agent.id} className={`is-${agent.status}`}>
      <strong>{agent.title}</strong>
      <span>{AGENT_STATUS[agent.status] || '—'}{agent.total > 0 && ` · ${agent.completed}/${agent.total}`}</span>
    </li>)}
  </ul>;
}

export function ReviewProgress({ review, canCancel, busy, onCancel }: {
  review: Review; canCancel: boolean; busy: boolean; onCancel: () => void;
}) {
  const progress = review.progress;
  const total = progress?.total || 0;
  return <section className="lv-progress-card" aria-label="审查进度">
    <div className="lv-progress-head">
      <ReviewingSheet paused={review.status === 'queued'} />
      <div role="status"><h2>{review.status === 'queued' ? '排队中' : '审查中'}</h2><p>{review.stage}</p></div>
      {total > 0 && <span className="lv-progress-count">{progress?.completed}/{total}</span>}
    </div>
    {total > 0 && <div className="lv-progress-bar" role="progressbar" aria-label="审查完成度" aria-valuemin={0} aria-valuemax={total} aria-valuenow={progress?.completed || 0}>
      <span style={{ width: `${Math.min(100, Math.round(((progress?.completed || 0) / total) * 100))}%` }} />
    </div>}
    {review.collaboration && <Lanes collaboration={review.collaboration} label="协作进度" />}
    <div className="lv-progress-foot">
      <span>可关闭页面，审查将在后台继续。</span>
      {canCancel && <button className="lv-text-button" disabled={busy} onClick={onCancel}>停止审查</button>}
    </div>
  </section>;
}

export function ReviewIssue({ review, busy, onResume }: { review: Review; busy: boolean; onResume: () => void }) {
  const title = review.status === 'cancelled' ? '审查已停止' : review.status === 'failed' ? '审查已暂停' : '部分步骤未完成';
  return <section className="lv-note is-warn lv-review-issue">
    <strong>{title}</strong>
    {review.error ? <p>{review.error}</p> : review.stage && <p>{review.stage}</p>}
    {review.resumable && <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onResume}><RotateCcw {...ic} size={14} />重试</button>}
  </section>;
}

const TONES: Tone[] = ['high', 'mid', 'low', 'unconfirmed'];

export function ReviewSummary({ review, onExport }: { review: Review; onExport: () => void }) {
  const counts = findingCounts(review.findings);
  const tally = Object.fromEntries(TONES.map(t => [t, review.findings.filter(f => findingStatus(f) !== 'rejected' && findingTone(f) === t).length])) as Record<Tone, number>;
  const checked = review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length;
  const partial = review.status === 'partial';
  const scenario = review.profile?.scenario?.label || review.profile?.contract_type;
  return <section className="lv-summary" aria-label="审查结果概览">
    <div className="lv-summary-head">
      <h2>审查结果</h2>
      <span className="lv-summary-meta">{[scenario, review.profile?.our_role && `我方：${review.profile.our_role}`].filter(Boolean).join(' · ')}</span>
      <span className={`lv-chip ${partial ? 'is-mid' : 'is-ink'}`}>{partial ? '部分完成' : '待复核'}</span>
    </div>
    {counts.actionable > 0 ? <>
      <dl className="lv-stats" aria-label="风险分布">
        <div className="lv-stat-total"><dt>审查意见</dt><dd>{counts.actionable}</dd></div>
        {TONES.map(t => <div key={t} className={`tone-${t} ${tally[t] ? '' : 'is-zero'}`}><dt><i aria-hidden="true" />{TONE_LABEL[t]}</dt><dd>{tally[t]}</dd></div>)}
      </dl>
      <div className="lv-riskbar" aria-hidden="true">{TONES.filter(t => tally[t] > 0).map(t => <span key={t} className={`tone-${t}`} style={{ flexGrow: tally[t] }} />)}</div>
    </> : <p className="lv-summary-empty">未形成可采纳的修改意见。该结果不代表合同不存在风险。</p>}
    {partial && <p className="lv-note is-warn">部分审查未完成，相关条款请人工复核。</p>}
    <div className="lv-summary-foot">
      <span>审查范围 {checked}/{review.coverage.length}{counts.rejected > 0 ? ` · 已排除 ${counts.rejected} 项` : ''}</span>
      <button className="lv-text-button" onClick={onExport}>导出<ArrowRight {...ic} size={14} /></button>
    </div>
  </section>;
}
