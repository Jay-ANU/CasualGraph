import type { Review } from './types';
import { findingStatus } from './findingStatus';

/** Local preflight only. Parsing and permissions are still enforced by the API. */
export function uploadIssue(file: Pick<File, 'name' | 'size'>): string {
  if (!/\.(docx|pdf|txt)$/i.test(file.name)) return '仅支持 DOCX、PDF（文本型）、TXT 格式，.doc 文件请另存为 .docx。';
  if (file.size === 0) return '文件内容为空。';
  if (file.size > 10 * 1024 * 1024) return '文件超过 10 MB 上限。';
  return '';
}

export function pendingDecisions(review: Review): number {
  return review.findings.filter(f => findingStatus(f) !== 'rejected'
    && (!review.decisions[f.id] || ['pending', 'draft'].includes(review.decisions[f.id].decision))).length;
}
