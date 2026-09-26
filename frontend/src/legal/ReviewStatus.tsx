import type { CSSProperties } from 'react';
import { ArrowRight, RotateCcw } from 'lucide-react';
import type { Review } from './types';
import { findingCounts, findingStatus } from './findingStatus';
import { AGENT_STATUS, findingTone, researchGaps, reviewOutcome, reviewStatusLabel, TONE_LABEL } from './labels';
import type { Tone } from './labels';
import { agentLine, formatClock, PHASE_STEPS, phaseDetail, remainingLabel, remainingSeconds, reviewPhase } from './reviewActivity';
import type { Agent } from './reviewActivity';
import { useLiveReview, useNow } from './useLive';
import { ReviewingSheet } from './art';
import { CountUp, DrawnCheck } from './ui';
import { ic } from './icon';

function Clock({ createdAt, percent }: { createdAt?: number; percent: number }) {
  const now = useNow();
  if (!createdAt) return null;
  const elapsed = Math.max(0, now / 1000 - createdAt);
  const left = remainingLabel(remainingSeconds(percent, elapsed));
  return <dl className="lv-live-clock">
    <div><dt>已用时</dt><dd>{formatClock(elapsed)}</dd></div>
    {left && <div><dt>预计剩余</dt><dd>{left}</dd></div>}
  </dl>;
}

function StepTimer({ since }: { since?: number }) {
  const now = useNow();
  return since ? <span className="lv-agent-time">本项已进行 {formatClock((now - since) / 1000)}</span> : null;
}

/** A heartbeat for each poll result, so a long model call never looks like a frozen page. */
function SyncStatus({ at }: { at: number }) {
  const seconds = Math.max(0, (useNow() - at) / 1000);
  const stale = seconds > 20;
  return <span className={`lv-sync ${stale ? 'is-stale' : ''}`}>
    <i key={at} aria-hidden="true" />
    {stale ? '同步延迟，正在重试' : seconds < 5 ? '刚刚同步' : seconds < 60 ? `${Math.floor(seconds)} 秒前同步` : `${Math.floor(seconds / 60)} 分钟前同步`}
  </span>;
}

function AgentCard({ agent, since }: { agent: Agent; since?: number }) {
  const running = agent.status === 'running';
  const slots = Math.min(agent.total, 12);
  const filled = agent.total > 12 ? Math.round((agent.completed / agent.total) * 12) : agent.completed;
  return <li className={`lv-agent is-${agent.status}`}>
    <div className="lv-agent-head">
      <strong>{agent.title}</strong>
      <span className="lv-agent-state">
        {running ? <i className="lv-live-dot" aria-hidden="true" /> : agent.status === 'completed' && <DrawnCheck />}
        {AGENT_STATUS[agent.status] || '—'}{agent.total > 0 && ` · ${agent.completed}/${agent.total}`}
      </span>
    </div>
    {slots > 0 && <div className="lv-agent-track" aria-hidden="true">
      {Array.from({ length: slots }, (_, i) => <span key={i} className={i < filled ? 'done' : i === filled && running ? 'active' : ''} />)}
    </div>}
    <p className="lv-agent-note">{agentLine(agent)}</p>
    {running && <StepTimer since={since} />}
  </li>;
}

const clockTime = (at: number) => new Date(at).toLocaleTimeString('zh-CN', { hour12: false });

export function ReviewProgress({ review, canCancel, busy, onCancel }: {
  review: Review; canCancel: boolean; busy: boolean; onCancel: () => void;
}) {
  const live = useLiveReview(review);
  const phase = reviewPhase(review);
  const queued = phase === 'queued';
  const step = PHASE_STEPS.findIndex(item => item.id === phase);
  const detail = phaseDetail(review);
  const interim = review.findings.filter(f => findingStatus(f) !== 'rejected').length;
  const agents = review.collaboration?.agents || [];
  const working = agents.filter(a => a.status !== 'not_applicable');
  const idle = agents.filter(a => a.status === 'not_applicable');
  return <section className="lv-live lv-enter" aria-label="审查进度">
    <div className="lv-live-head">
      <ReviewingSheet paused={queued} size={36} />
      <div className="lv-live-title">
        <h2>{queued ? '排队中' : '审查中'}</h2>
        <p>{review.stage}</p>
      </div>
      <Clock createdAt={review.created_at} percent={live.percent} />
    </div>
    <div className="lv-live-bar" role="progressbar" aria-label="审查完成度" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={Math.round(live.percent)} aria-valuetext={detail || undefined}>
      <span style={{ width: `${Math.max(2, live.percent)}%` }} />
    </div>
    <div className="lv-live-steps">
      <ol className="lv-phases" aria-label="审查阶段">
        {PHASE_STEPS.map((item, i) => <li key={item.id} className={i < step ? 'done' : i === step ? 'current' : ''} aria-current={i === step ? 'step' : undefined}>
          <span className="lv-phase-mark" aria-hidden="true">{i < step && <DrawnCheck />}</span>{item.label}
        </li>)}
      </ol>
      {detail && <span className="lv-live-detail">{detail}</span>}
    </div>
    {working.length > 0 && <ul className="lv-agents" aria-label="协作进度">
      {working.map(agent => <AgentCard key={agent.id} agent={agent} since={live.stepStartedAt[agent.id]} />)}
    </ul>}
    {idle.map(agent => <p key={agent.id} className="lv-agents-note">{agent.title}不适用：{agentLine(agent)}</p>)}
    <div className="lv-activity">
      <div className="lv-activity-head"><h3>实时动态</h3><SyncStatus at={live.syncedAt} /></div>
      <div role="log" aria-label="审查动态"><ol className="lv-activity-list">
        {live.events.map(event => <li key={event.id} className={`tone-${event.tone}`}>
          <time dateTime={new Date(event.at).toISOString()}>{clockTime(event.at)}</time><span>{event.text}</span>
        </li>)}
      </ol></div>
    </div>
    <div className="lv-progress-foot">
      <span>{interim > 0 && <>已发现 <strong>{interim}</strong> 条初步意见，审查完成后可逐条处理。</>}可关闭页面，审查将在后台继续。</span>
      {canCancel && <button className="lv-text-button" disabled={busy} onClick={onCancel}>停止审查</button>}
    </div>
  </section>;
}

export function ReviewIssue({ review, busy, onResume }: { review: Review; busy: boolean; onResume: () => void }) {
  // Missing official text is not a failed review: searching again costs no model call.
  const gapsOnly = !review.error && reviewOutcome(review) === 'evidence_gaps';
  const title = review.status === 'cancelled' ? '审查已停止' : review.status === 'failed' ? '审查已暂停'
    : gapsOnly ? `${researchGaps(review)} 个法律问题未取得官方原文` : '部分步骤未完成';
  const detail = gapsOnly ? '相关意见照常给出，法律依据标注为“模型引用，待核对”。可重新检索官方原文，不会重新调用模型。'
    : review.error || review.stage;
  return <section className={`lv-note ${gapsOnly ? '' : 'is-warn'} lv-review-issue`}>
    <strong>{title}</strong>
    {detail && <p>{detail}</p>}
    {review.resumable && <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onResume}><RotateCcw {...ic} size={14} />{gapsOnly ? '重新检索' : '重试'}</button>}
  </section>;
}

const TONES: Tone[] = ['high', 'mid', 'low', 'unconfirmed'];

export function ReviewSummary({ review, onExport }: { review: Review; onExport: () => void }) {
  const counts = findingCounts(review.findings);
  const tally = Object.fromEntries(TONES.map(t => [t, review.findings.filter(f => findingStatus(f) !== 'rejected' && findingTone(f) === t).length])) as Record<Tone, number>;
  const checked = review.coverage.filter(c => ['reviewed', 'not_applicable'].includes(c.status)).length;
  const outcome = reviewOutcome(review);
  // ReviewIssue explains the same outcome, with its action, whenever the review can be resumed.
  const issueShown = review.resumable || !!review.error;
  const scenario = review.profile?.scenario?.label || review.profile?.contract_type;
  return <section className="lv-summary" aria-label="审查结果概览">
    <div className="lv-summary-head">
      <h2>审查结果</h2>
      <span className="lv-summary-meta">{[scenario, review.profile?.our_role && `我方：${review.profile.our_role}`].filter(Boolean).join(' · ')}</span>
      <span className={`lv-chip ${outcome ? 'is-mid' : 'is-ink'}`}>{reviewStatusLabel(review)}</span>
    </div>
    {counts.actionable > 0 ? <>
      <dl className="lv-stats" aria-label="风险分布">
        <div className="lv-stat-total"><dt>审查意见</dt><dd><CountUp value={counts.actionable} /></dd></div>
        {TONES.map((t, i) => <div key={t} className={`tone-${t} ${tally[t] ? '' : 'is-zero'}`} style={{ '--i': i + 1 } as CSSProperties}><dt><i aria-hidden="true" />{TONE_LABEL[t]}</dt><dd><CountUp value={tally[t]} /></dd></div>)}
      </dl>
      <div className="lv-riskbar" aria-hidden="true">{TONES.filter(t => tally[t] > 0).map((t, i) => <span key={t} className={`tone-${t}`} style={{ flexGrow: tally[t], '--i': i } as CSSProperties} />)}</div>
    </> : <p className="lv-summary-empty">未形成可采纳的修改意见。该结果不代表合同不存在风险。</p>}
    {!issueShown && outcome === 'failed_steps' && <p className="lv-note is-warn">部分审查步骤未完成，未完成部分不能据此排除风险。</p>}
    {!issueShown && outcome === 'evidence_gaps' && <p className="lv-note">{researchGaps(review)} 个法律问题未检索到官方原文，相关依据标注为“模型引用，待核对”。</p>}
    <div className="lv-summary-foot">
      <span>审查范围 {checked}/{review.coverage.length}{counts.rejected > 0 ? ` · 已排除 ${counts.rejected} 项` : ''}</span>
      <button className="lv-text-button" onClick={onExport}>导出<ArrowRight {...ic} size={14} /></button>
    </div>
  </section>;
}
