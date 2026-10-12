import type { Review } from './types';
import { tierOf } from './labels';
import { currentLang, tr, type Lang } from '../i18n/core';

/**
 * Local preflight only. Parsing and permissions are still enforced by the API. The desk
 * keeps the Chinese message and translates it when shown (the English is in the dictionary).
 */
export function uploadIssue(file: Pick<File, 'name' | 'size'>, lang: Lang = currentLang()): string {
  if (!/\.(docx|pdf|txt)$/i.test(file.name)) return tr('仅支持 DOCX、PDF、TXT 格式，.doc 文件请另存为 .docx。', lang);
  if (file.size === 0) return tr('文件内容为空。', lang);
  if (file.size > 10 * 1024 * 1024) return tr('文件超过 10 MB 上限。', lang);
  return '';
}

export function pendingDecisions(review: Review): number {
  return new Set(review.findings.filter(f => !['accepted', 'rejected'].includes(review.decisions[f.id]?.decision)).map(f => f.id)).size;
}

/** Faster reviews deliver a readable draft as soon as the model finishes. */
export const draftFirst = (review: Review) => ['ultra_fast', 'fast'].includes(tierOf(review)) && ['completed', 'partial'].includes(review.status);
