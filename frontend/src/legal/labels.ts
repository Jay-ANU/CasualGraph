import type { Finding, Profile, Review, ReviewTier } from './types';
import { findingStatus } from './findingStatus';

/** Contract-level status shown in “我的合同”. */
export const CONTRACT_STATUS: Record<string, string> = {
  redaction_pending: '待确认脱敏', ready: '可审查',
  queued: '排队中', running: '审查中', completed: '审查完成', partial: '部分完成', failed: '已暂停', cancelled: '已停止',
};

/** Review-level status shown next to the open contract. */
export const REVIEW_STATUS: Record<string, string> = {
  queued: '排队中', running: '审查中', completed: '待复核', partial: '部分完成', failed: '已暂停', cancelled: '已停止',
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

export const OUTCOME_LABEL: Record<ReviewOutcome, string> = { failed_steps: '部分完成', evidence_gaps: '依据待核对', to_confirm: '待确认' };

export function reviewStatusLabel(r: Pick<Review, 'status' | 'batch_errors' | 'retrieval' | 'coverage' | 'review_tier' | 'profile'>): string {
  const outcome = reviewOutcome(r);
  if (!outcome && r.status === 'completed' && tierOf(r) === 'ultra_fast') return '未复核';
  return outcome ? OUTCOME_LABEL[outcome] : REVIEW_STATUS[r.status] || r.status;
}

/** Review tiers, fastest first, with what each one leaves out. */
export const TIERS: { value: ReviewTier; title: string; note: string }[] = [
  { value: 'ultra_fast', title: '极速', note: '一轮并行审查，直接给出意见和修改建议；不检索法规、不做独立复核，采用前请逐条确认。' },
  { value: 'fast', title: '快速', note: '分组审查后逐项独立复核；不检索法规，不做全文交叉核对。' },
  { value: 'standard', title: '标准', note: '分组审查与法规检索同时进行，逐项复核后核对各项修改能否同时采用。' },
  { value: 'deep', title: '深度', note: '法律、商业与公司规范分别审查，再经独立复核与全文协调；耗时最长。' },
];

/** Tiers the backend offers; a backend from before tiers only runs standard and deep reviews. */
export function availableTiers(caps: { review_tiers?: ReviewTier[] } | null) {
  const offered: ReviewTier[] = caps?.review_tiers?.length ? caps.review_tiers : ['standard', 'deep'];
  return TIERS.filter(t => offered.includes(t.value));
}

export const TIER_LABEL: Record<ReviewTier, string> = { ultra_fast: '极速审查', fast: '快速审查', standard: '标准审查', deep: '深度审查' };

/** The tier a review ran at; reviews from before tiers keep their original mode. */
export function tierOf(r?: { review_tier?: ReviewTier; profile?: Profile } | null): ReviewTier {
  return r?.review_tier || r?.profile?.review_tier || (r?.profile?.review_mode === 'multi_agent' ? 'deep' : 'standard');
}

/** Legal issues the research plan searched for without obtaining official text. */
export const researchGaps = (r: Pick<Review, 'retrieval'>) => (r.retrieval || []).filter(x => x.status !== 'retrieved').length;

export const KIND_LABEL: Record<string, string> = { legal: '法律风险', commercial: '商业利益', company_policy: '公司规范' };
export const KIND_FILTERS: [string, string][] = [['all', '全部'], ['legal', '法律风险'], ['commercial', '商业利益'], ['company_policy', '公司规范']];

export const AGENT_STATUS: Record<string, string> = {
  pending: '待开始', running: '进行中', completed: '已完成', partial: '部分完成', paused: '已暂停', not_applicable: '不适用',
};

export const COVERAGE_STATUS: Record<string, string> = {
  reviewed: '已审查', not_applicable: '不适用', needs_information: '待补充', not_reviewed: '未完成',
};

export const STEPS = ['脱敏确认', '审查设置', '审查意见', '核验导出'];

export type Tone = 'high' | 'mid' | 'low' | 'unconfirmed' | 'excluded';

/** One visual tone per finding: evidence state first, then severity. */
export function findingTone(f: Finding): Tone {
  const status = findingStatus(f);
  if (status === 'rejected') return 'excluded';
  if (status === 'unconfirmed') return 'unconfirmed';
  return f.severity === 'high' ? 'high' : f.severity === 'medium' ? 'mid' : 'low';
}

export const TONE_LABEL: Record<Tone, string> = {
  high: '高风险', mid: '中风险', low: '提示', unconfirmed: '待核实', excluded: '已排除',
};

const TONE_RANK: Record<Tone, number> = { high: 0, mid: 1, unconfirmed: 2, low: 3, excluded: 9 };

/** The most urgent tone among a paragraph's open findings. */
export function strongestTone(findings: Finding[]): Tone | null {
  return findings.map(findingTone).filter(t => t !== 'excluded').sort((a, b) => TONE_RANK[a] - TONE_RANK[b])[0] || null;
}

export function formatDate(value: unknown): string {
  const n = typeof value === 'number' ? (value < 1e12 ? value * 1000 : value) : typeof value === 'string' ? Date.parse(value) : NaN;
  if (!Number.isFinite(n)) return '';
  const date = new Date(n), now = new Date();
  if (date.toDateString() === now.toDateString()) return `今天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
  return date.getFullYear() === now.getFullYear()
    ? `${date.getMonth() + 1}月${date.getDate()}日`
    : `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

export const fileTitle = (name: string) => name.replace(/\.(docx|pdf|txt)$/i, '');
