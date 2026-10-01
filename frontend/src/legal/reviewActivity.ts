import type { Collaboration, Review } from './types';
import { findingTone, tierOf } from './labels';
import type { Tone } from './labels';
import { currentLang, pick, type Lang } from '../i18n/core';
import { plural, serverText } from './i18n';

/**
 * Live progress for a running review, derived only from fields the review API
 * already returns: phase and stage, per-agent status and counts, model calls
 * started and interim findings. Nothing here is simulated; when a signal is
 * missing the estimate simply moves less.
 */

export type PhaseId = 'queued' | 'intake' | 'retrieval' | 'review' | 'coordination' | 'complete';
export type Agent = Collaboration['agents'][number];

export type PhaseStep = { id: 'intake' | 'retrieval' | 'review' | 'coordination'; label: string };

const PHASE_STEPS: { id: PhaseStep['id']; zh: string; en: string }[] = [
  { id: 'intake', zh: '读取合同', en: 'Read' },
  { id: 'retrieval', zh: '检索法规', en: 'Research' },
  { id: 'review', zh: '分项审查', en: 'Review' },
  { id: 'coordination', zh: '汇总复核', en: 'Finalise' },
];

/** The steps a review actually runs, in the current language: faster tiers skip research and the final pass. */
export function phaseSteps(r: Review, lang: Lang = currentLang()): PhaseStep[] {
  const tier = tierOf(r);
  const steps = tier === 'ultra_fast' ? PHASE_STEPS.filter(s => s.id === 'intake' || s.id === 'review')
    : tier === 'fast' ? PHASE_STEPS.filter(s => s.id !== 'retrieval').map(s => s.id === 'coordination' ? { ...s, zh: '逐项复核', en: 'Verify' } : s)
    : PHASE_STEPS;
  return steps.map(s => ({ id: s.id, label: pick(s.zh, s.en, lang) }));
}

const SUPPORT_AGENTS = new Set(['critic', 'arbiter']);
const clamp = (n: number, low = 0, high = 1) => Math.min(high, Math.max(low, Number.isFinite(n) ? n : 0));
const sum = (agents: Agent[], key: 'completed' | 'total') => agents.reduce((n, a) => n + (a[key] || 0), 0);

/** Specialists that actually have work this round (critic and arbiter excluded). */
export const specialists = (r: Review) => (r.collaboration?.agents || []).filter(a => !SUPPORT_AGENTS.has(a.id) && a.status !== 'not_applicable');

export function reviewPhase(r: Review): PhaseId {
  if (r.status === 'queued') return 'queued';
  if (r.status !== 'running') return 'complete';
  const p = r.progress;
  if (p?.phase === 'arbitration' || r.collaboration?.agents.some(a => a.id === 'arbiter' && a.status === 'running')) return 'coordination';
  if (p?.phase === 'collaboration') return 'review';
  // Single-agent reviews run their last group as the whole-contract consistency check.
  if (p?.phase === 'review' || p?.phase === 'verification') return p.total > 1 && p.completed >= p.total - 1 ? 'coordination' : 'review';
  if (p?.phase === 'retrieval') return 'retrieval';
  return 'intake';
}

/** Share of the review finished, 0–100. Callers keep the maximum so it never moves backwards. */
export function reviewPercent(r: Review): number {
  const phase = reviewPhase(r);
  if (phase === 'queued') return 0;
  if (phase === 'complete') return 100;
  if (phase === 'intake') return 3;
  const p = r.progress;
  if (phase === 'retrieval') {
    const total = Math.max(1, p?.total || 0);
    return 6 + 14 * clamp(Math.max((p?.completed || 0) / total, (r.retrieval?.length || 0) / total), 0, .95);
  }
  if (r.collaboration) {
    const team = specialists(r);
    const tasks = Math.max(1, sum(team, 'total'));
    const running = team.filter(a => a.status === 'running').length
      + (r.collaboration.agents.some(a => a.id === 'arbiter' && a.status === 'running') ? 1 : 0);
    // Every task is one specialist call plus one verification call; intake and arbitration add three.
    const finishedCalls = Math.max(0, (r.metrics?.model_calls || 0) - running);
    if (phase === 'review') {
      const byCalls = (finishedCalls - 1) / (2 * tasks);
      const byTasks = sum(team, 'completed') / tasks;
      return 20 + 68 * clamp(Math.max(byCalls, byTasks), 0, .98);
    }
    return 88 + 10 * clamp((finishedCalls - 1 - 2 * tasks) / 2, 0, .95);
  }
  const groups = Math.max(1, p?.total || 1);
  return 20 + 78 * clamp(((p?.completed || 0) + (p?.phase === 'verification' ? .5 : 0)) / groups, 0, .98);
}

/** Concrete counts for the current phase; also the progress bar's spoken value. */
export function phaseDetail(r: Review, lang: Lang = currentLang()): string {
  const say = (zh: string, en: string) => pick(zh, en, lang);
  const phase = reviewPhase(r);
  if (phase === 'queued') return say('等待开始', 'Waiting to start');
  if (phase === 'intake') return ['ultra_fast', 'fast'].includes(tierOf(r)) ? say('读取合同', 'Reading the contract') : say('读取合同，规划法律检索', 'Reading the contract and planning legal research');
  if (phase === 'retrieval') return say(`法规检索 · 已检索 ${r.retrieval?.length || 0} 项`, `Researching the law · ${r.retrieval?.length || 0} searched`);
  if (r.collaboration) {
    const team = specialists(r);
    const done = sum(team, 'completed'), total = sum(team, 'total');
    return phase === 'review' ? say(`分项审查 · 已完成 ${done}/${total} 项`, `Reviewing · ${done}/${total} done`)
      : say('汇总复核 · 交叉检查各项结论', 'Finalising · cross-checking the findings');
  }
  const p = r.progress;
  if (!p?.total) return '';
  const group = `${Math.min(p.completed + 1, p.total)}/${p.total}`;
  return phase === 'coordination' ? say(`汇总复核 · 第 ${group} 组`, `Finalising · group ${group}`) : say(`分项审查 · 第 ${group} 组`, `Reviewing · group ${group}`);
}

/** Rough time left from the pace so far; only once there is enough signal to be useful. */
export function remainingSeconds(percent: number, elapsedSeconds: number): number | null {
  if (percent < 25 || percent >= 99 || elapsedSeconds < 45) return null;
  return elapsedSeconds * (100 - percent) / percent;
}

export function remainingLabel(seconds: number | null, lang: Lang = currentLang()): string {
  if (seconds == null) return '';
  const minutes = Math.ceil(seconds / 60);
  return seconds < 60 ? pick('即将完成', 'Almost done', lang) : pick(`约 ${minutes} 分钟`, `~${minutes} min`, lang);
}

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

export type ActivityTone = 'ink' | 'ok' | 'warn' | 'high' | 'mid' | 'low';
export type ActivityEvent = { id: string; at: number; text: string; tone: ActivityTone };
type Draft = Omit<ActivityEvent, 'id' | 'at'>;

const NEW_FINDING: Record<Exclude<Tone, 'excluded'>, [string, string]> = {
  high: ['发现高风险意见', 'New high-risk finding'], mid: ['发现中风险意见', 'New medium-risk finding'],
  low: ['发现提示意见', 'New advisory finding'], unconfirmed: ['发现待核实意见', 'New finding to verify'],
};

/**
 * What changed between two polls of the same review, in reading order, in the given
 * language. The service's stage and notes are translated when known; finding titles are
 * the model's own words and stay as written.
 */
export function reviewEvents(prev: Review | null, next: Review, lang: Lang = currentLang()): Draft[] {
  if (!prev || prev.id !== next.id) return [];
  const say = (zh: string, en: string) => pick(zh, en, lang);
  const out: Draft[] = [];
  if (prev.status === 'queued' && next.status === 'running') out.push({ text: say('开始审查', 'Review started'), tone: 'ink' });
  // Multi-agent stage text only adds a counter while agents work; agent events already say it.
  const counterOnly = Boolean(next.collaboration) && reviewPhase(next) === 'review' && reviewPhase(prev) === 'review';
  if (next.stage && next.stage !== prev.stage && !counterOnly) out.push({ text: serverText(next.stage, lang), tone: 'ink' });
  const before = new Map((prev.collaboration?.agents || []).map(a => [a.id, a]));
  for (const a of next.collaboration?.agents || []) {
    const b = before.get(a.id);
    if (!b) continue;
    const title = serverText(a.title, lang);
    if (a.status !== b.status) {
      if (a.status === 'running') out.push({ text: say(`${title}开始工作`, `${title} started`), tone: 'ink' });
      else if (a.status === 'completed') out.push({ text: say(`${title}已完成`, `${title} finished`), tone: 'ok' });
      else if (a.status === 'partial') out.push({ text: say(`${title}部分完成`, `${title} partly finished`), tone: 'warn' });
      else if (a.status === 'paused') out.push({ text: say(`${title}已暂停`, `${title} paused`), tone: 'warn' });
    }
    if (a.status === 'running' && a.completed > b.completed) {
      out.push({ text: say(`${title}完成第 ${a.completed}/${a.total} 项`, `${title} finished item ${a.completed}/${a.total}`), tone: 'ok' });
    }
    // The verification agent's note already names what it checks.
    if (a.status === 'running' && a.note && a.note !== b.note) {
      const note = serverText(a.note, lang);
      out.push({ text: a.id === 'critic' ? note : `${title} · ${note}`, tone: 'ink' });
    }
  }
  const known = new Set(prev.findings.map(f => f.id));
  const fresh = next.findings.filter(f => !known.has(f.id) && findingTone(f) !== 'excluded');
  for (const f of fresh.slice(0, 2)) {
    const tone = findingTone(f) as Exclude<Tone, 'excluded'>;
    out.push({ text: `${say(...NEW_FINDING[tone])}${say('：', ': ')}${f.title}`, tone: tone === 'high' ? 'high' : tone === 'mid' ? 'mid' : 'low' });
  }
  if (fresh.length > 2) out.push({ text: say(`另有 ${fresh.length - 2} 条新意见`, plural(fresh.length - 2, 'more new finding', 'more new findings')), tone: 'ink' });
  return out;
}

/** Changes whenever an agent moves to another item, so its timer shows time on the current item. */
export const agentStepKey = (a: Agent) => `${a.status}|${a.completed}|${a.note}`;

/** One line under each agent: the engine's note when it sends one, otherwise counts. */
export function agentLine(a: Agent, lang: Lang = currentLang()): string {
  if (a.note) return serverText(a.note, lang);
  const say = (zh: string, en: string) => pick(zh, en, lang);
  const counts = `${a.completed}/${a.total}`;
  switch (a.status) {
    case 'running':
      return a.id === 'arbiter' ? say('正在交叉检查各项结论', 'Cross-checking the findings')
        : a.id === 'critic' ? say(`已复核 ${counts} 项`, `Verified ${counts}`)
        : say(`正在审查第 ${Math.min(a.completed + 1, a.total)}/${a.total} 项`, `Reviewing item ${Math.min(a.completed + 1, a.total)}/${a.total}`);
    case 'pending':
      return a.id === 'arbiter' ? say('分项审查完成后开始', 'Starts after the item reviews')
        : a.id === 'critic' ? say('随各项审查逐项复核', 'Verifies each item as it finishes') : say('等待开始', 'Waiting to start');
    case 'completed': return a.id === 'arbiter' ? say('已完成', 'Done') : say(`已完成 ${counts} 项`, `Done ${counts}`);
    case 'partial': return say(`部分完成 ${counts} 项`, `Partly done ${counts}`);
    case 'paused': return say('已暂停，可恢复', 'Paused; can resume');
    default: return say('本轮不适用', 'Not needed this round');
  }
}
