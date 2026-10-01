import { RotateCcw } from 'lucide-react';
import type { Review } from './types';
import { findingStatus } from './findingStatus';
import { agentStatusLabel, failedSteps, researchGaps, reviewOutcome, tierLabel, tierOf } from './labels';
import { agentLine, formatClock, phaseDetail, phaseSteps, remainingLabel, remainingSeconds, reviewPhase } from './reviewActivity';
import type { Agent } from './reviewActivity';
import { useLiveReview, useNow } from './useLive';
import { ReviewingSheet } from './art';
import { DrawnCheck, Spinner } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';
import { plural, serverText } from './i18n';

function Clock({ createdAt, percent }: { createdAt?: number; percent: number }) {
  const { tx } = useI18n();
  const now = useNow();
  if (!createdAt) return null;
  const elapsed = Math.max(0, now / 1000 - createdAt);
  return <dl className="lv-live-clock">
    <div><dt>{tx('已用时', 'Elapsed')}</dt><dd>{formatClock(elapsed)}</dd></div>
    <div><dt>{tx('预计剩余', 'Time left')}</dt><dd>{remainingLabel(remainingSeconds(percent, elapsed)) || '—'}</dd></div>
  </dl>;
}

/** A heartbeat for each poll result, so a long model call never looks like a frozen page. */
function SyncStatus({ at }: { at: number }) {
  const { tx } = useI18n();
  const seconds = Math.max(0, (useNow() - at) / 1000);
  const stale = seconds > 20;
  return <span className={`lv-sync${stale ? ' is-stale' : ''}`}>
    <i key={at} aria-hidden="true" />
    {stale ? tx('同步延迟，正在重试', 'Sync delayed, retrying') : seconds < 5 ? tx('刚刚同步', 'Synced just now')
      : seconds < 60 ? tx(`${Math.floor(seconds)} 秒前同步`, `Synced ${Math.floor(seconds)}s ago`) : tx(`${Math.floor(seconds / 60)} 分钟前同步`, `Synced ${Math.floor(seconds / 60)} min ago`)}
  </span>;
}

function AgentRow({ agent }: { agent: Agent }) {
  const percent = agent.total ? Math.round((agent.completed / agent.total) * 100) : agent.status === 'completed' ? 100 : 0;
  return <li className={`lv-agent is-${agent.status}`}>
    <div className="lv-agent-head">
      <strong>{serverText(agent.title)}</strong>
      <span className="lv-agent-state">{agent.status === 'completed' && <DrawnCheck size={11} />}
        {agent.total > 0 ? `${agent.completed}/${agent.total}` : agentStatusLabel(agent.status) || '—'}</span>
    </div>
    <span className="lv-agent-bar" aria-hidden="true"><i style={{ width: `${percent}%` }} /></span>
    <p>{agentLine(agent)}</p>
  </li>;
}

const clockTime = (at: number) => new Date(at).toLocaleTimeString('zh-CN', { hour12: false });

export function ReviewProgress({ review, canCancel, busy, onCancel }: {
  review: Review; canCancel: boolean; busy: boolean; onCancel: () => void;
}) {
  const { lang, tx } = useI18n();
  const live = useLiveReview(review);
  const phase = reviewPhase(review);
  const queued = phase === 'queued';
  const steps = phaseSteps(review);
  // A phase a tier does not run (e.g. the final pass in ultra-fast) shows as the last step.
  const step = Math.max(steps.findIndex(item => item.id === phase), phase === 'coordination' ? steps.length - 1 : -1);
  const detail = phaseDetail(review);
  const interim = review.findings.filter(f => findingStatus(f) !== 'rejected').length;
  const agents = review.collaboration?.agents || [];
  const working = agents.filter(a => a.status !== 'not_applicable');
  const idle = agents.filter(a => a.status === 'not_applicable');
  return <section className="lv-rail-panel lv-live" aria-label={tx('审查进度', 'Review progress')}>
    <div className="lv-rail-head">
      <div className="lv-live-head">
        <ReviewingSheet paused={queued} size={26} />
        <div className="lv-live-title">
          <h2>{queued ? tx('排队中', 'Queued') : tx('审查中', 'Reviewing')}</h2>
          <p>{tierLabel(tierOf(review))}{tx(' · 发现的意见会直接标在正文上', ' · findings are marked on the text as they come in')}</p>
        </div>
        <Clock createdAt={review.created_at} percent={live.percent} />
      </div>
      <div className="lv-live-bar" role="progressbar" aria-label={tx('审查完成度', 'Review completion')} aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(live.percent)} aria-valuetext={detail || undefined}>
        <span style={{ width: `${Math.max(2, live.percent)}%` }} />
      </div>
      <ol className="lv-phases" aria-label={tx('审查阶段', 'Review stages')} style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((item, i) => <li key={item.id} className={i < step ? 'done' : i === step ? 'current' : ''} aria-current={i === step ? 'step' : undefined}>
          <i aria-hidden="true" />{item.label}
        </li>)}
      </ol>
    </div>
    <div className="lv-rail-body">
      {working.length > 0 && <ul className="lv-agents" aria-label={tx('协作进度', 'Team progress')}>{working.map(agent => <AgentRow key={agent.id} agent={agent} />)}</ul>}
      {idle.map(agent => <p key={agent.id} className="lv-agents-note">{tx(`${agent.title}不适用：${agentLine(agent)}`, `${serverText(agent.title)} not needed: ${agentLine(agent)}`)}</p>)}
      <div className="lv-activity">
        <div className="lv-activity-head"><h3>{tx('实时动态', 'Live activity')}</h3><SyncStatus at={live.syncedAt} /></div>
        <div role="log" aria-label={tx('审查动态', 'Review activity')}><ol className="lv-activity-list">
          {live.events.map(event => <li key={event.id} className={`tone-${event.tone}`}>
            <time dateTime={new Date(event.at).toISOString()}>{clockTime(event.at)}</time><i aria-hidden="true" /><span>{event.text[lang]}</span>
          </li>)}
        </ol></div>
      </div>
    </div>
    <div className="lv-rail-foot lv-rail-foot-row">
      <span>{interim > 0 ? <>{tx('已标出 ', '')}<strong className="lv-mono">{interim}</strong>{tx(' 条初步意见 · ', interim === 1 ? ' preliminary finding marked · ' : ' preliminary findings marked · ')}</> : null}
        {tx('可关闭页面，审查在后台继续', 'You can close this page; the review carries on')}</span>
      {canCancel && <button className="lv-text-button" disabled={busy} onClick={onCancel}>{tx('停止审查', 'Stop review')}</button>}
    </div>
  </section>;
}

/** Why the review did not finish cleanly, with the one action that helps. */
export function ReviewIssue({ review, busy, onResume }: { review: Review; busy: boolean; onResume: () => void }) {
  const { tx } = useI18n();
  // Missing official text is not a failed review: searching again costs no model call.
  const gapsOnly = !review.error && reviewOutcome(review) === 'evidence_gaps';
  const steps = review.status === 'partial' && !gapsOnly ? failedSteps(review) : [];
  const gaps = researchGaps(review);
  const title = review.status === 'cancelled' ? tx('审查已停止', 'Review stopped') : review.status === 'failed' ? tx('审查已暂停', 'Review paused')
    : gapsOnly ? tx(`${gaps} 个法律问题未取得官方原文`, `No official text for ${plural(gaps, 'legal issue')}`)
    : steps.length ? tx(`${steps.length} 个步骤未完成`, `${plural(steps.length, 'step')} did not finish`) : tx('部分步骤未完成', 'Some steps did not finish');
  const detail = gapsOnly ? tx('相关依据标注为“模型引用，待核对”。重新检索不会重新调用模型。', 'The related basis is marked “model-cited, to verify”. Searching again does not call the model.')
    : serverText(review.error) || (steps.length ? tx('其余意见可先处理；重试只重新运行未完成的步骤。', 'You can work on the other findings now; retrying only reruns the unfinished steps.') : serverText(review.stage));
  return <div className={`lv-issue${gapsOnly ? '' : ' is-warn'}`} role="status">
    <div><strong>{title}</strong>
      {steps.length > 0 && <ul className="lv-issue-steps" aria-label={tx('未完成的步骤', 'Unfinished steps')}>{steps.map(step => <li key={step.id} title={step.code || undefined}>
        <span>{step.title}</span>{step.message}</li>)}</ul>}
      {detail && <p>{detail}</p>}</div>
    {review.resumable && <button className="lv-secondary lv-btn-sm" disabled={busy} onClick={onResume}>{busy ? <Spinner /> : <RotateCcw {...ic} size={14} />}{gapsOnly ? tx('重新检索', 'Search again') : tx('重试', 'Retry')}</button>}
  </div>;
}
