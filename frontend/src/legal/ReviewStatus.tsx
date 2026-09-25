import { ArrowRight, RotateCcw, StopCircle } from 'lucide-react';
import type { Collaboration, Review } from './types';
import { findingCounts, findingStatus } from './findingStatus';
import { pendingDecisions } from './deskLogic';
import { AGENT_STATUS, findingTone, TONE_LABEL } from './labels';
import type { Tone } from './labels';
import { Spinner } from './ui';
import { ic } from './icon';

export function Lanes({ collaboration, label }: { collaboration: Collaboration; label?: string }) {
  return <ul className="lv-lanes" aria-label={label}>
    {collaboration.agents.map(agent => <li key={agent.id} className={`is-${agent.status}`}>
      <strong>{agent.title}</strong>
      <span>{AGENT_STATUS[agent.status] || '状态待确认'}{agent.total > 0 && ` · ${agent.completed}/${agent.total}`}</span>
      {agent.note && <small>{agent.note}</small>}
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
      <Spinner />
      <div role="status"><h2>{review.status === 'queued' ? '正在排队' : '正在审查'}</h2><p>{review.stage}</p></div>
      {total > 0 && <span className="lv-progress-count">{progress?.completed} / {total} 步</span>}
    </div>
    {total > 0 && <div className="lv-progress-bar" role="progressbar" aria-label="审查完成度" aria-valuemin={0} aria-valuemax={total} aria-valuenow={progress?.completed || 0}>
      <span style={{ width: `${Math.min(100, Math.round(((progress?.completed || 0) / total) * 100))}%` }} />
    </div>}
    {review.collaboration && <Lanes collaboration={review.collaboration} label="协作进度" />}
    <p className="lv-hint">审查在服务器上进行，可以离开此页面，稍后在“我的合同”中继续查看。先出现的意见会显示在下方；尚未完成的部分不代表没有风险。</p>
    {canCancel && <button className="lv-quiet" disabled={busy} onClick={onCancel}><StopCircle {...ic} />停止后续步骤</button>}
  </section>;
}

export function ReviewIssue({ review, busy, onResume }: { review: Review; busy: boolean; onResume: () => void }) {
  const title = review.status === 'cancelled' ? '审查已停止' : review.status === 'failed' ? '审查暂停了' : '有步骤没有完成';
  return <section className="lv-note is-warn lv-review-issue">
    <strong>{title}</strong>
    {review.error ? <p>{review.error}</p> : review.stage && <p>{review.stage}</p>}
    {review.resumable && <button className="lv-secondary" disabled={busy} onClick={onResume}><RotateCcw {...ic} />重试未完成步骤</button>}
  </section>;
}

const TONES: Tone[] = ['high', 'mid', 'low', 'unconfirmed'];

export function ReviewSummary({ review, onPending, onUnconfirmed, onExport }: {
  review: Review; onPending: () => void; onUnconfirmed: () => void; onExport: () => void;
}) {
  const counts = findingCounts(review.findings);
  const pending = pendingDecisions(review);
  const accepted = Object.values(review.decisions).filter(d => d.decision === 'accepted').length;
  const tally = Object.fromEntries(TONES.map(t => [t, review.findings.filter(f => findingStatus(f) !== 'rejected' && findingTone(f) === t).length])) as Record<Tone, number>;
  const checked = review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length;
  const partial = review.status === 'partial';
  const scenario = review.profile?.scenario?.label || review.profile?.contract_type;
  return <section className="lv-summary" aria-label="本轮审查概览">
    <div className="lv-summary-head">
      <div>
        <p className="lv-summary-kicker">审查结果{scenario ? ` · ${scenario}` : ''}{review.profile?.our_role ? ` · 我方：${review.profile.our_role}` : ''}</p>
        <h2>{counts.actionable ? `这份合同有 ${counts.actionable} 处需要关注` : '本轮没有形成可采纳的修改意见'}</h2>
      </div>
      <span className={`lv-chip ${partial ? 'is-mid' : 'is-ink'}`}>{partial ? '部分完成' : '等待你复核'}</span>
    </div>
    {counts.actionable > 0 && <div className="lv-risk-summary">
      <div className="lv-riskbar" aria-hidden="true">{TONES.filter(t => tally[t] > 0).map(t => <span key={t} className={`tone-${t}`} style={{ flexGrow: tally[t] }} />)}</div>
      <ul className="lv-risk-legend" aria-label="风险分布">{TONES.map(t => <li key={t} className={tally[t] ? '' : 'is-zero'}><i className={`tone-${t}`} aria-hidden="true" />{TONE_LABEL[t]}<b>{tally[t]}</b></li>)}</ul>
    </div>}
    <p className="lv-summary-guide">
      {tally.high > 0 ? `建议先处理 ${tally.high} 项高风险条款，再看其余意见。` : counts.actionable > 0 ? '建议逐条对照合同原文，再决定是否修改。' : '没有可采纳的意见，不代表合同没有风险。可以查看下方的检查范围，必要时咨询律师。'}
    </p>
    {partial && <p className="lv-note is-warn">本轮检查没有全部完成。未完成或没有取得依据的部分，请人工核对。</p>}
    <div className="lv-metrics">
      <button onClick={onPending}><strong>{pending}</strong><span>待你处理<ArrowRight {...ic} size={13} /></span></button>
      <button onClick={onUnconfirmed}><strong>{counts.unconfirmed}</strong><span>待核实<ArrowRight {...ic} size={13} /></span><small>依据或事实不足</small></button>
      <button onClick={onExport}><strong>{accepted}</strong><span>已采纳修改<ArrowRight {...ic} size={13} /></span></button>
    </div>
    <div className="lv-summary-foot">
      <span>已检查 {checked} / {review.coverage.length} 个方面{counts.rejected > 0 ? ` · ${counts.rejected} 项疑点经复核排除` : ''}</span>
      <button className="lv-text-button" onClick={onExport}>去导出<ArrowRight {...ic} size={14} /></button>
    </div>
  </section>;
}
