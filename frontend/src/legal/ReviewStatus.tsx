import { useEffect, useRef } from 'react';
import { RotateCcw } from 'lucide-react';
import type { Review } from './types';
import { findingStatus } from './findingStatus';
import { agentStatusLabel, failedSteps, researchGaps, reviewOutcome, tierLabel, tierOf } from './labels';
import { agentLine, chatTier, formatClock, liveActivity, phaseDetail, phaseSteps, remainingLabel, remainingSeconds, reviewPhase } from './reviewActivity';
import type { Agent } from './reviewActivity';
import { useLiveReview, useNow } from './useLive';
import { DrawnCheck, ProgressRing, Spinner } from './ui';
import { MemoText } from './ReviewMemo';
import { ToolList } from './ToolList';
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

/**
 * A chat-style review shows what the model is writing as it writes it: the review memo,
 * kept scrolled to its newest line, the tools it calls, or what it is doing before any text arrives.
 */
function LiveWriting({ review }: { review: Review }) {
  const { tx } = useI18n();
  const live = review.live;
  const box = useRef<HTMLDivElement>(null);
  const memo = live?.memo || '';
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [memo]);
  if (!live) return null;
  const calls = live.tools || [];
  const earlier = Math.max(0, (live.tool_count || 0) - calls.length);
  return <section className="lv-writing" aria-label={tx('模型撰写进度', 'What the model is writing')}>
    <div className="lv-activity-head"><h3>{liveActivity(live)}</h3></div>
    {calls.length > 0 && <>
      {earlier > 0 && <p className="lv-hint">{tx(`另有 ${earlier} 次较早的工具调用`, `${plural(earlier, 'earlier tool call')} not shown`)}</p>}
      <ToolList calls={calls} label={tx('模型调用的工具', 'Tools the model called')} />
    </>}
    {memo ? <div ref={box} className="lv-writing-box lv-memo-text" lang="zh-CN" aria-live="off"><MemoText text={memo} /></div>
      : <p className="lv-writing-wait"><Spinner />{live.step === 'research' ? tx('正在检索法规原文，完成后复读全文定稿。', 'Searching official legal sources; the model then re-reads the contract to finalise.')
        : live.activity === 'tools' ? tx('模型正在调用工具，结果会交回模型继续审查。', 'The model is calling tools; the results go back to it as it reviews.')
        : tx('模型正在通读整份合同，审查意见书会在这里逐字出现。', 'The model is reading the whole contract; its review memo will appear here as it writes.')}</p>}
  </section>;
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
        <ProgressRing percent={live.percent} paused={queued} />
        <div className="lv-live-title">
          <h2>{queued ? tx('排队中', 'Queued') : tx('审查中', 'Reviewing')}</h2>
          <p>{tierLabel(tierOf(review))}{!chatTier(tierOf(review)) ? tx(' · 发现的意见会直接标在正文上', ' · findings are marked on the text as they come in')
            : review.tools_offered ? tx(' · 模型通读全文，按需调用工具，写出完整审查和修订稿', ' · the model reads the whole contract, calls tools as it needs them and writes the full review and draft')
            : tx(' · 模型通读全文，写出完整审查和修订稿', ' · the model reads the whole contract and writes the full review and draft')}</p>
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
      {chatTier(tierOf(review)) && !queued && <LiveWriting review={review} />}
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
