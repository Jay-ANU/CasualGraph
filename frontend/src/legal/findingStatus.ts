import type { Finding } from './types';
import { currentLang, pick, type Lang } from '../i18n/core';

/**
 * Rejected by the critic, still unconfirmed, supported, or quick (an ultra-fast finding that
 * was never sent to a critic: counted by severity and labelled unverified).
 * These labels describe evidence, not whether a person may use or export an edit.
 */
export function findingStatus(f: Finding): 'supported' | 'quick' | 'unconfirmed' | 'rejected' {
  if (f.verification_status === 'rejected') return 'rejected';
  if (f.verification_status === 'skipped' && f.evidence_status !== 'unverified' && f.missing_facts.length === 0) return 'quick';
  if (f.verification_status !== 'supported' || f.evidence_status === 'unverified' || f.missing_facts.length > 0) return 'unconfirmed';
  return 'supported';
}

export type RevisionInput = { done: boolean; busy: boolean; text: string; original: string; legalBasis?: boolean; manual?: boolean };

/**
 * An explicit accept/save action is the user's decision. Model disagreements and missing
 * legal evidence remain visible as notes; only unusable text or a missing target prevents
 * a paragraph edit. Automatically generated drafts are created separately by the backend.
 */
export function revisionState(f: Finding, s: RevisionInput, lang: Lang = currentLang()) {
  const adoptable = s.text === f.suggested_text && !!f.suggested_text;
  const say = (zh: string, en: string) => pick(zh, en, lang);
  const issue = !s.done ? say('审查完成后方可操作。', 'Available once the review has finished.')
    : !f.block_id ? say('缺失条款需在原文中人工补充。', 'Add a missing clause to the contract by hand.')
    : !s.text.trim() ? say('修订内容不能为空。', 'The revision cannot be empty.')
    : s.text.trim() === s.original.trim() ? say('修订内容与原文相同。', 'The revision is the same as the original.') : '';
  return { adoptable, decision: 'accepted', issue, canSubmit: !issue && !s.busy };
}

export function findingCounts(findings: Finding[]) {
  return {
    high: findings.filter(f => ['supported', 'quick'].includes(findingStatus(f)) && f.severity === 'high').length,
    unconfirmed: findings.filter(f => findingStatus(f) === 'unconfirmed').length,
    rejected: findings.filter(f => findingStatus(f) === 'rejected').length,
    actionable: findings.length,
  };
}
