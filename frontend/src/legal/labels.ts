import type { Finding } from './types';
import { findingStatus } from './findingStatus';

/** Contract-level status shown in “我的合同”. */
export const CONTRACT_STATUS: Record<string, string> = {
  redaction_pending: '待确认脱敏', ready: '可审查',
  queued: '排队中', running: '审查中', completed: '审查完成', partial: '部分完成', failed: '已暂停', cancelled: '已停止',
};

/** Review-level status shown next to the open contract. */
export const REVIEW_STATUS: Record<string, string> = {
  queued: '排队中', running: '审查中', completed: '待你处理', partial: '部分完成', failed: '已暂停', cancelled: '已停止',
};

export const KIND_LABEL: Record<string, string> = { legal: '法律风险', commercial: '商业利益', company_policy: '公司规范' };
export const KIND_FILTERS: [string, string][] = [['all', '全部意见'], ['legal', '法律风险'], ['commercial', '商业利益'], ['company_policy', '公司规范']];

export const AGENT_STATUS: Record<string, string> = {
  pending: '等待开始', running: '进行中', completed: '已完成', partial: '部分完成', paused: '已暂停', not_applicable: '本轮不适用',
};

export const COVERAGE_STATUS: Record<string, string> = {
  reviewed: '已检查', not_applicable: '不适用', needs_information: '待确认', not_reviewed: '未完成',
};

export const STEPS = ['检查脱敏', '确认立场', '逐条处理', '核验导出'];

export type Tone = 'high' | 'mid' | 'low' | 'unconfirmed' | 'excluded';

/** One visual tone per finding: evidence state first, then severity. */
export function findingTone(f: Finding): Tone {
  const status = findingStatus(f);
  if (status === 'rejected') return 'excluded';
  if (status === 'unconfirmed') return 'unconfirmed';
  return f.severity === 'high' ? 'high' : f.severity === 'medium' ? 'mid' : 'low';
}

export const TONE_LABEL: Record<Tone, string> = {
  high: '高风险', mid: '中风险', low: '提示', unconfirmed: '待核实', excluded: '复核已排除',
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
