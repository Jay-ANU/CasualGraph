import type { Collaboration, Review } from './types';
import { findingTone, tierOf, TONE_LABEL } from './labels';

/**
 * Live progress for a running review, derived only from fields the review API
 * already returns: phase and stage, per-agent status and counts, model calls
 * started and interim findings. Nothing here is simulated; when a signal is
 * missing the estimate simply moves less.
 */

export type PhaseId = 'queued' | 'intake' | 'retrieval' | 'review' | 'coordination' | 'complete';
export type Agent = Collaboration['agents'][number];

export const PHASE_STEPS: { id: 'intake' | 'retrieval' | 'review' | 'coordination'; label: string }[] = [
  { id: 'intake', label: '读取合同' },
  { id: 'retrieval', label: '检索法规' },
  { id: 'review', label: '分项审查' },
  { id: 'coordination', label: '汇总复核' },
];

/** The steps a review actually runs: faster tiers skip research and the final pass. */
export function phaseSteps(r: Review): typeof PHASE_STEPS {
  const tier = tierOf(r);
  if (tier === 'ultra_fast') return PHASE_STEPS.filter(s => s.id === 'intake' || s.id === 'review');
  if (tier === 'fast') return PHASE_STEPS.filter(s => s.id !== 'retrieval').map(s => s.id === 'coordination' ? { ...s, label: '逐项复核' } : s);
  return PHASE_STEPS;
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
export function phaseDetail(r: Review): string {
  const phase = reviewPhase(r);
  if (phase === 'queued') return '等待开始';
  if (phase === 'intake') return ['ultra_fast', 'fast'].includes(tierOf(r)) ? '读取合同' : '读取合同，规划法律检索';
  if (phase === 'retrieval') return `法规检索 · 已检索 ${r.retrieval?.length || 0} 项`;
  if (r.collaboration) {
    const team = specialists(r);
    return phase === 'review' ? `分项审查 · 已完成 ${sum(team, 'completed')}/${sum(team, 'total')} 项` : '汇总复核 · 交叉检查各项结论';
  }
  const p = r.progress;
  if (!p?.total) return '';
  return `${phase === 'coordination' ? '汇总复核' : '分项审查'} · 第 ${Math.min(p.completed + 1, p.total)}/${p.total} 组`;
}

/** Rough time left from the pace so far; only once there is enough signal to be useful. */
export function remainingSeconds(percent: number, elapsedSeconds: number): number | null {
  if (percent < 25 || percent >= 99 || elapsedSeconds < 45) return null;
  return elapsedSeconds * (100 - percent) / percent;
}

export function remainingLabel(seconds: number | null): string {
  if (seconds == null) return '';
  return seconds < 60 ? '即将完成' : `约 ${Math.ceil(seconds / 60)} 分钟`;
}

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

export type ActivityTone = 'ink' | 'ok' | 'warn' | 'high' | 'mid' | 'low';
export type ActivityEvent = { id: string; at: number; text: string; tone: ActivityTone };
type Draft = Omit<ActivityEvent, 'id' | 'at'>;

/** What changed between two polls of the same review, in reading order. */
export function reviewEvents(prev: Review | null, next: Review): Draft[] {
  if (!prev || prev.id !== next.id) return [];
  const out: Draft[] = [];
  if (prev.status === 'queued' && next.status === 'running') out.push({ text: '开始审查', tone: 'ink' });
  // Multi-agent stage text only adds a counter while agents work; agent events already say it.
  const counterOnly = Boolean(next.collaboration) && reviewPhase(next) === 'review' && reviewPhase(prev) === 'review';
  if (next.stage && next.stage !== prev.stage && !counterOnly) out.push({ text: next.stage, tone: 'ink' });
  const before = new Map((prev.collaboration?.agents || []).map(a => [a.id, a]));
  for (const a of next.collaboration?.agents || []) {
    const b = before.get(a.id);
    if (!b) continue;
    if (a.status !== b.status) {
      if (a.status === 'running') out.push({ text: `${a.title}开始工作`, tone: 'ink' });
      else if (a.status === 'completed') out.push({ text: `${a.title}已完成`, tone: 'ok' });
      else if (a.status === 'partial') out.push({ text: `${a.title}部分完成`, tone: 'warn' });
      else if (a.status === 'paused') out.push({ text: `${a.title}已暂停`, tone: 'warn' });
    }
    if (a.status === 'running' && a.completed > b.completed) out.push({ text: `${a.title}完成第 ${a.completed}/${a.total} 项`, tone: 'ok' });
    // The verification agent's note already names what it checks.
    if (a.status === 'running' && a.note && a.note !== b.note) out.push({ text: a.id === 'critic' ? a.note : `${a.title} · ${a.note}`, tone: 'ink' });
  }
  const known = new Set(prev.findings.map(f => f.id));
  const fresh = next.findings.filter(f => !known.has(f.id) && findingTone(f) !== 'excluded');
  for (const f of fresh.slice(0, 2)) {
    const tone = findingTone(f);
    out.push({ text: `发现${TONE_LABEL[tone]}意见：${f.title}`, tone: tone === 'high' ? 'high' : tone === 'mid' ? 'mid' : 'low' });
  }
  if (fresh.length > 2) out.push({ text: `另有 ${fresh.length - 2} 条新意见`, tone: 'ink' });
  return out;
}

/** Changes whenever an agent moves to another item, so its timer shows time on the current item. */
export const agentStepKey = (a: Agent) => `${a.status}|${a.completed}|${a.note}`;

/** One line under each agent: the engine's note when it sends one, otherwise counts. */
export function agentLine(a: Agent): string {
  if (a.note) return a.note;
  const counts = `${a.completed}/${a.total} 项`;
  switch (a.status) {
    case 'running':
      return a.id === 'arbiter' ? '正在交叉检查各项结论' : a.id === 'critic' ? `已复核 ${counts}` : `正在审查第 ${Math.min(a.completed + 1, a.total)}/${a.total} 项`;
    case 'pending':
      return a.id === 'arbiter' ? '分项审查完成后开始' : a.id === 'critic' ? '随各项审查逐项复核' : '等待开始';
    case 'completed': return a.id === 'arbiter' ? '已完成' : `已完成 ${counts}`;
    case 'partial': return `部分完成 ${counts}`;
    case 'paused': return '已暂停，可恢复';
    default: return '本轮不适用';
  }
}
