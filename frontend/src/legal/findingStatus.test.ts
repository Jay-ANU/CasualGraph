import { describe, expect, it } from 'vitest';
import { findingCounts, findingStatus } from './findingStatus';
import type { Finding } from './types';
const finding = (overrides: Partial<Finding> = {}): Finding => ({
  id: 'f1', block_id: 'p1', original_quote: '合成原文', title: '合成风险', kind: 'commercial',
  severity: 'high', impact: '合成影响', reason: '合成理由', suggested_text: '', evidence_status: 'not_applicable',
  missing_facts: [], citations: [], policy_ids: [], verification_status: 'supported', ...overrides,
});
describe('audit risk summary', () => {
  it('never counts rejected or uncertain candidates as high risks', () => {
    expect(findingCounts([finding(), finding({ verification_status: 'rejected' }), finding({ verification_status: 'uncertain' }), finding({ evidence_status: 'unverified' })]))
      .toEqual({ high: 1, unconfirmed: 2, rejected: 1, actionable: 3 });
  });
  it('requires explicit support, evidence and no missing facts', () => {
    expect(findingStatus(finding({ verification_status: undefined }))).toBe('unconfirmed');
    expect(findingStatus(finding({ missing_facts: ['缺少附件'] }))).toBe('unconfirmed');
    expect(findingStatus(finding({ verification_status: 'rejected', missing_facts: ['未知'] }))).toBe('rejected');
  });
});
it('does not promote a legal citation to a verified law version', () => {
  expect(findingStatus(finding({ kind: 'legal', evidence_status: 'source_matched', version_status: 'needs_verification' }))).toBe('unconfirmed');
  expect(findingCounts([finding({ kind: 'legal', evidence_status: 'source_matched' })]).high).toBe(0);
});
