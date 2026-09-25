import type { Finding, Review } from './types';
import { findingStatus } from './findingStatus';

/** Local preflight only. Parsing and permissions are still enforced by the API. */
export function uploadIssue(file: Pick<File, 'name' | 'size'>): string {
  if (!/\.(docx|pdf|txt)$/i.test(file.name)) return '请选择 DOCX、文字型 PDF 或 TXT。旧版 .doc 请先另存为 .docx。';
  if (file.size === 0) return '这份文件是空的，请检查文件后重新选择。';
  if (file.size > 10 * 1024 * 1024) return '文件超过 10 MB，请拆分附件后上传。';
  return '';
}

export function visibleFindings(review: Review, kind: string, state: string, query: string): Finding[] {
  const text = query.trim().toLocaleLowerCase();
  const decision = (f: Finding) => review.decisions[f.id]?.decision || 'pending';
  const priority = (f: Finding) => (findingStatus(f) === 'rejected' ? 100 : 0)
    + (['accepted', 'rejected'].includes(decision(f)) ? 20 : 0)
    + ({ high: 0, medium: 4, low: 8 }[f.severity] ?? 8)
    + (findingStatus(f) === 'unconfirmed' ? 1 : 0);
  return review.findings.filter(f => (kind === 'all' || f.kind === kind)
    && (state === 'all' || (state === 'unconfirmed' ? findingStatus(f) === 'unconfirmed' : state === 'pending' ? findingStatus(f) !== 'rejected' && ['pending', 'draft'].includes(decision(f)) : decision(f) === state))
    && (!text || [f.title, f.impact, f.reason, f.original_quote].join(' ').toLocaleLowerCase().includes(text)))
    .map((finding, index) => ({ finding, index }))
    .sort((a, b) => priority(a.finding) - priority(b.finding) || a.index - b.index)
    .map(item => item.finding);
}

export function pendingDecisions(review: Review): number {
  return review.findings.filter(f => findingStatus(f) !== 'rejected'
    && (!review.decisions[f.id] || ['pending', 'draft'].includes(review.decisions[f.id].decision))).length;
}
