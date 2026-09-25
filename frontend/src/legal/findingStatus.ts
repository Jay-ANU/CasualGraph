import type { Finding } from './types';

export function findingStatus(f: Finding): 'supported' | 'unconfirmed' | 'rejected' {
  if (f.verification_status === 'rejected') return 'rejected';
  if (f.verification_status !== 'supported' || f.evidence_status === 'unverified' || f.missing_facts.length > 0 || (f.kind === 'legal' && f.version_status !== 'verified')) return 'unconfirmed';
  return 'supported';
}

export function findingCounts(findings: Finding[]) {
  return {
    high: findings.filter(f => findingStatus(f) === 'supported' && f.severity === 'high').length,
    unconfirmed: findings.filter(f => findingStatus(f) === 'unconfirmed').length,
    rejected: findings.filter(f => findingStatus(f) === 'rejected').length,
    actionable: findings.filter(f => findingStatus(f) !== 'rejected').length,
  };
}
