import type { Finding, Profile, Review, ReviewTier, StepError } from './types';
import { findingStatus } from './findingStatus';
import { currentLang, pick, type Lang } from '../i18n/core';
import { labelOf, serverText, type Pair } from './i18n';

/** Contract-level status shown in “我的合同”. */
const CONTRACT_STATUS: Record<string, Pair> = {
  redaction_pending: ['待确认脱敏', 'Redaction pending'], ready: ['可审查', 'Ready'],
  queued: ['排队中', 'Queued'], running: ['审查中', 'In review'], completed: ['审查完成', 'Reviewed'], partial: ['部分完成', 'Partly done'],
  failed: ['已暂停', 'Paused'], cancelled: ['已停止', 'Stopped'],
};
export const contractStatusLabel = (status: string, lang: Lang = currentLang()) => labelOf(CONTRACT_STATUS, status, lang) ?? status;

/** Review-level status shown next to the open contract. */
const REVIEW_STATUS: Record<string, Pair> = {
  queued: ['排队中', 'Queued'], running: ['审查中', 'In review'], completed: ['待复核', 'Awaiting review'], partial: ['部分完成', 'Partly done'],
  failed: ['已暂停', 'Paused'], cancelled: ['已停止', 'Stopped'],
};

/**
 * Why a finished review is not a clean pass. Only failed steps mean the review is incomplete;
 * missing official text can be searched again, and items to confirm are a normal result.
 */
export type ReviewOutcome = 'failed_steps' | 'evidence_gaps' | 'to_confirm';

export function reviewOutcome(r: Pick<Review, 'status' | 'batch_errors' | 'retrieval' | 'coverage'>): ReviewOutcome | null {
  if (r.status !== 'partial') return null;
  if (Object.keys(r.batch_errors || {}).length > 0 || (r.coverage || []).some(c => c.status === 'not_reviewed')) return 'failed_steps';
  if ((r.retrieval || []).some(x => x.status !== 'retrieved')) return 'evidence_gaps';
  return 'to_confirm';
}

const STEP_NAMES: Record<string, Pair> = { research: ['法律检索规划', 'Legal research planning'], cross_check: ['修改兼容性核对', 'Edit compatibility check'] };

/** The steps a review could not finish and why; reviews from before named steps kept only the reason. */
export function failedSteps(r: Pick<Review, 'step_errors' | 'batch_errors'>, lang: Lang = currentLang()): StepError[] {
  if (r.step_errors?.length) return r.step_errors.map(step => ({ ...step, title: serverText(step.title, lang), message: serverText(step.message, lang) }));
  return Object.entries(r.batch_errors || {}).map(([id, message]) => ({
    id, title: labelOf(STEP_NAMES, id, lang) ?? pick('分项审查', 'Item review', lang), code: '', message: serverText(message, lang),
  }));
}

const OUTCOME_LABEL: Record<ReviewOutcome, Pair> = {
  failed_steps: ['部分完成', 'Partly done'], evidence_gaps: ['依据待核对', 'Basis to verify'], to_confirm: ['待确认', 'To confirm'],
};

export function reviewStatusLabel(r: Pick<Review, 'status' | 'batch_errors' | 'retrieval' | 'coverage' | 'review_tier' | 'profile'>, lang: Lang = currentLang()): string {
  const outcome = reviewOutcome(r);
  if (!outcome && r.status === 'completed' && tierOf(r) === 'ultra_fast') return pick('未复核', 'Unverified', lang);
  return outcome ? labelOf(OUTCOME_LABEL, outcome, lang)! : labelOf(REVIEW_STATUS, r.status, lang) ?? r.status;
}

/** Review tiers, fastest first, with what each one leaves out. */
const TIERS: { value: ReviewTier; title: Pair; label: Pair; note: Pair }[] = [
  { value: 'ultra_fast', title: ['极速', 'Ultra-fast'], label: ['极速审查', 'Ultra-fast review'],
    note: ['一轮并行审查，直接给出意见和修改建议；不检索法规、不做独立复核，采用前请逐条确认。',
      'One parallel pass that returns findings and suggested edits directly. No legal research and no independent verification, so confirm each finding before adopting it.'] },
  { value: 'fast', title: ['快速', 'Fast'], label: ['快速审查', 'Fast review'],
    note: ['分组审查后逐项独立复核；不检索法规，不做全文交叉核对。',
      'Reviews the contract in groups, then verifies each finding independently. No legal research and no whole-contract cross-check.'] },
  { value: 'standard', title: ['标准', 'Standard'], label: ['标准审查', 'Standard review'],
    note: ['分组审查与法规检索同时进行，逐项复核后核对各项修改能否同时采用。',
      'Reviews in groups while researching the law, verifies each finding, then checks that the edits can be adopted together.'] },
  { value: 'deep', title: ['深度', 'Deep'], label: ['深度审查', 'Deep review'],
    note: ['法律、商业与公司规范分别审查，再经独立复核与全文协调；耗时最长。',
      'Separate legal, commercial and company-policy reviews, then independent verification and a whole-contract pass. Takes the longest.'] },
];

/** Tiers the backend offers, in the current language; a backend from before tiers only runs standard and deep reviews. */
export function availableTiers(caps: { review_tiers?: ReviewTier[] } | null, lang: Lang = currentLang()) {
  const offered: ReviewTier[] = caps?.review_tiers?.length ? caps.review_tiers : ['standard', 'deep'];
  return TIERS.filter(t => offered.includes(t.value))
    .map(t => ({ value: t.value, title: pick(...t.title, lang), note: pick(...t.note, lang) }));
}

/** “标准审查” / “Standard review”. */
export function tierLabel(tier: ReviewTier, lang: Lang = currentLang()): string {
  const found = TIERS.find(t => t.value === tier);
  return found ? pick(...found.label, lang) : tier;
}

/** The tier a review ran at; reviews from before tiers keep their original mode. */
export function tierOf(r?: { review_tier?: ReviewTier; profile?: Profile } | null): ReviewTier {
  return r?.review_tier || r?.profile?.review_tier || (r?.profile?.review_mode === 'multi_agent' ? 'deep' : 'standard');
}

/** Legal issues the research plan searched for without obtaining official text. */
export const researchGaps = (r: Pick<Review, 'retrieval'>) => (r.retrieval || []).filter(x => x.status !== 'retrieved').length;

const KIND_LABEL: Record<string, Pair> = { legal: ['法律风险', 'Legal'], commercial: ['商业利益', 'Commercial'], company_policy: ['公司规范', 'Company policy'] };
/** A finding's category; undefined for kinds this desk does not know. */
export const kindLabel = (kind: string, lang: Lang = currentLang()) => labelOf(KIND_LABEL, kind, lang);

const AGENT_STATUS: Record<string, Pair> = {
  pending: ['待开始', 'Not started'], running: ['进行中', 'In progress'], completed: ['已完成', 'Done'], partial: ['部分完成', 'Partly done'],
  paused: ['已暂停', 'Paused'], not_applicable: ['不适用', 'Not needed'],
};
export const agentStatusLabel = (status: string, lang: Lang = currentLang()) => labelOf(AGENT_STATUS, status, lang);

const COVERAGE_STATUS: Record<string, Pair> = {
  reviewed: ['已审查', 'Reviewed'], not_applicable: ['不适用', 'Not applicable'], needs_information: ['待补充', 'Needs information'], not_reviewed: ['未完成', 'Not finished'],
};
export const coverageStatusLabel = (status: string, lang: Lang = currentLang()) => labelOf(COVERAGE_STATUS, status, lang) ?? status;

export type Tone = 'high' | 'mid' | 'low' | 'unconfirmed' | 'excluded';

/** One visual tone per finding: evidence state first, then severity. */
export function findingTone(f: Finding): Tone {
  const status = findingStatus(f);
  if (status === 'rejected') return 'excluded';
  if (status === 'unconfirmed') return 'unconfirmed';
  return f.severity === 'high' ? 'high' : f.severity === 'medium' ? 'mid' : 'low';
}

const TONE_LABEL: Record<Tone, Pair> = {
  high: ['高风险', 'High risk'], mid: ['中风险', 'Medium risk'], low: ['提示', 'Advisory'], unconfirmed: ['待核实', 'To verify'], excluded: ['已排除', 'Excluded'],
};
export const toneLabel = (tone: Tone, lang: Lang = currentLang()) => labelOf(TONE_LABEL, tone, lang)!;

const TONE_RANK: Record<Tone, number> = { high: 0, mid: 1, unconfirmed: 2, low: 3, excluded: 9 };

/** The most urgent tone among a paragraph's open findings. */
export function strongestTone(findings: Finding[]): Tone | null {
  return findings.map(findingTone).filter(t => t !== 'excluded').sort((a, b) => TONE_RANK[a] - TONE_RANK[b])[0] || null;
}

export function formatDate(value: unknown, lang: Lang = currentLang()): string {
  const n = typeof value === 'number' ? (value < 1e12 ? value * 1000 : value) : typeof value === 'string' ? Date.parse(value) : NaN;
  if (!Number.isFinite(n)) return '';
  const date = new Date(n), now = new Date();
  if (lang === 'en') {
    if (date.toDateString() === now.toDateString()) return `Today ${date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`;
    return date.toLocaleDateString('en-GB', date.getFullYear() === now.getFullYear()
      ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' });
  }
  if (date.toDateString() === now.toDateString()) return `今天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
  return date.getFullYear() === now.getFullYear()
    ? `${date.getMonth() + 1}月${date.getDate()}日`
    : `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

export const fileTitle = (name: string) => name.replace(/\.(docx|pdf|txt)$/i, '');
