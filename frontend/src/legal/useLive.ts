import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { Review } from './types';
import { agentStepKey, reviewEvents, reviewPercent } from './reviewActivity';
import type { ActivityTone } from './reviewActivity';
import { serverText } from './i18n';
import type { Lang } from '../i18n/core';

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

/** A feed entry in both languages, so switching the interface language rewrites the whole feed. */
export type LiveEvent = { id: string; at: number; text: Record<Lang, string>; tone: ActivityTone };
export type LiveReview = { percent: number; events: LiveEvent[]; stepStartedAt: Record<string, number>; syncedAt: number };

const MAX_EVENTS = 6;
let sequence = 0;
const eventId = () => `live-${++sequence}`;

function start(r: Review, at: number): LiveReview {
  const events: LiveEvent[] = [];
  if (r.status === 'running' && r.stage) events.push({ id: eventId(), at, text: { zh: r.stage, en: serverText(r.stage, 'en') }, tone: 'ink' });
  if (r.created_at) events.push({ id: eventId(), at: r.created_at * 1000, text: { zh: '已提交审查', en: 'Review submitted' }, tone: 'ink' });
  return { percent: reviewPercent(r), events, syncedAt: at,
    stepStartedAt: Object.fromEntries((r.collaboration?.agents || []).map(a => [a.id, at])) };
}

function advance(state: LiveReview, before: Review, r: Review, at: number): LiveReview {
  const en = reviewEvents(before, r, 'en');
  const fresh = reviewEvents(before, r, 'zh').map((e, i) => ({ id: eventId(), at, tone: e.tone, text: { zh: e.text, en: en[i]?.text ?? e.text } })).reverse();
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
