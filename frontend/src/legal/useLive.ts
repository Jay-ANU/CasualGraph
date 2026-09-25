import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { Review } from './types';
import { agentStepKey, reviewEvents, reviewPercent } from './reviewActivity';
import type { ActivityEvent } from './reviewActivity';

/* One shared one-second clock for every live label, started only while something listens. */
let now = Date.now();
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!timer) {
    now = Date.now();
    timer = setInterval(() => { now = Date.now(); listeners.forEach(l => l()); }, 1000);
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size && timer) { clearInterval(timer); timer = undefined; }
  };
}
export const useNow = () => useSyncExternalStore(subscribe, () => now, () => now);

export type LiveReview = { percent: number; events: ActivityEvent[]; stepStartedAt: Record<string, number>; syncedAt: number };

const MAX_EVENTS = 6;
let sequence = 0;
const eventId = () => `live-${++sequence}`;

function start(r: Review, at: number): LiveReview {
  const events: ActivityEvent[] = [];
  if (r.status === 'running' && r.stage) events.push({ id: eventId(), at, text: r.stage, tone: 'ink' });
  if (r.created_at) events.push({ id: eventId(), at: r.created_at * 1000, text: '已提交审查', tone: 'ink' });
  return { percent: reviewPercent(r), events, syncedAt: at,
    stepStartedAt: Object.fromEntries((r.collaboration?.agents || []).map(a => [a.id, at])) };
}

function advance(state: LiveReview, before: Review, r: Review, at: number): LiveReview {
  const fresh = reviewEvents(before, r).map(e => ({ ...e, id: eventId(), at })).reverse();
  const previous = new Map((before.collaboration?.agents || []).map(a => [a.id, agentStepKey(a)]));
  const stepStartedAt = Object.fromEntries((r.collaboration?.agents || []).map(a =>
    [a.id, previous.get(a.id) === agentStepKey(a) ? state.stepStartedAt[a.id] ?? at : at]));
  return { percent: Math.max(state.percent, reviewPercent(r)), events: [...fresh, ...state.events].slice(0, MAX_EVENTS), stepStartedAt, syncedAt: at };
}

/** Live view of a running review, advanced on every poll result. */
export function useLiveReview(review: Review): LiveReview {
  const [live, setLive] = useState(() => start(review, Date.now()));
  const last = useRef(review);
  useEffect(() => {
    const before = last.current;
    if (before === review) return;
    last.current = review;
    const at = Date.now();
    setLive(state => before.id === review.id ? advance(state, before, review, at) : start(review, at));
  }, [review]);
  return live;
}
