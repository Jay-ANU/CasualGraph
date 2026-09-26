import type { Finding } from './types';

/**
 * Rejected by the critic, still unconfirmed, supported, or quick (an ultra-fast finding that
 * was never sent to a critic: counted by severity, labelled unverified, adopted only as a
 * human revision). Legal findings keep a separate basis label (official text attached /
 * model-cited); the reviewer confirms the legal basis before adopting any legal edit.
 */
export function findingStatus(f: Finding): 'supported' | 'quick' | 'unconfirmed' | 'rejected' {
  if (f.verification_status === 'rejected') return 'rejected';
  if (f.verification_status === 'skipped' && f.evidence_status !== 'unverified' && f.missing_facts.length === 0) return 'quick';
  if (f.verification_status !== 'supported' || f.evidence_status === 'unverified' || f.missing_facts.length > 0) return 'unconfirmed';
  return 'supported';
}

export type RevisionInput = { done: boolean; busy: boolean; text: string; original: string; legalBasis: boolean; manual: boolean };

/**
 * What a reviewer may do with a finding. An unchanged suggestion the critic supported is
 * adopted in one click; anything else (edited text, an unconfirmed finding, or a paragraph
 * without a suggestion) is saved as a human revision, which the exact-combination check
 * verifies before export. Rejected findings and missing clauses cannot seed a revision.
 */
export function revisionState(f: Finding, s: RevisionInput) {
  const adoptable = s.text === f.suggested_text && !!f.suggested_text && f.revision_allowed === true;
  const issue = !s.done ? '审查完成后方可操作。'
    : findingStatus(f) === 'rejected' ? '该意见已被复核否定。'
    : !f.block_id ? '缺失条款需在原文中人工补充。'
    : !s.text.trim() ? '修订内容不能为空。'
    : s.text.trim() === s.original.trim() ? '修订内容与原文相同。'
    : f.kind === 'legal' && !s.legalBasis ? '请先确认已核对法规版本及适用性。'
    : !adoptable && !s.manual ? '请确认保存为人工修订。' : '';
  return { adoptable, decision: adoptable ? 'accepted' : 'draft', issue, canSubmit: !issue && !s.busy };
}

export function findingCounts(findings: Finding[]) {
  return {
    high: findings.filter(f => ['supported', 'quick'].includes(findingStatus(f)) && f.severity === 'high').length,
    unconfirmed: findings.filter(f => findingStatus(f) === 'unconfirmed').length,
    rejected: findings.filter(f => findingStatus(f) === 'rejected').length,
    actionable: findings.filter(f => findingStatus(f) !== 'rejected').length,
  };
}
