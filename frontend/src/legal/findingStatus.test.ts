import { describe, expect, it } from 'vitest';
import { findingCounts, findingStatus, revisionState } from './findingStatus';
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
it('counts a supported legal risk while its basis label stays separate', () => {
  expect(findingStatus(finding({ kind: 'legal', evidence_status: 'source_matched', version_status: 'needs_verification' }))).toBe('supported');
  expect(findingStatus(finding({ kind: 'legal', evidence_status: 'model_cited' }))).toBe('supported');
  expect(findingStatus(finding({ kind: 'legal', evidence_status: 'unverified' }))).toBe('unconfirmed');
  expect(findingCounts([finding({ kind: 'legal', evidence_status: 'source_matched' })]).high).toBe(1);
});
describe('revision choices', () => {
  const base = { done: true, busy: false, original: '甲方应在验收后90日内付款。', legalBasis: false, manual: false };
  const suggestion = '甲方应在验收后60日内付款。';
  it('adopts a supported, unchanged suggestion in one click', () => {
    const state = revisionState(finding({ suggested_text: suggestion, revision_allowed: true }), { ...base, text: suggestion });
    expect(state).toMatchObject({ adoptable: true, decision: 'accepted', canSubmit: true });
  });
  it('turns an unconfirmed or edited suggestion into a confirmed human revision', () => {
    const unconfirmed = finding({ suggested_text: suggestion, revision_allowed: false, verification_status: 'uncertain' });
    expect(revisionState(unconfirmed, { ...base, text: suggestion })).toMatchObject({ decision: 'draft', canSubmit: false, issue: '请确认保存为人工修订。' });
    expect(revisionState(unconfirmed, { ...base, text: suggestion, manual: true })).toMatchObject({ decision: 'draft', canSubmit: true });
    const edited = finding({ suggested_text: suggestion, revision_allowed: true });
    expect(revisionState(edited, { ...base, text: '甲方应在验收后30日内付款。', manual: true }).decision).toBe('draft');
  });
  it('lets a reviewer write a revision where the model gave none', () => {
    const noSuggestion = finding({ suggested_text: '', revision_allowed: false });
    expect(revisionState(noSuggestion, { ...base, text: base.original, manual: true }).issue).toBe('修订内容与原文相同。');
    expect(revisionState(noSuggestion, { ...base, text: suggestion, manual: true }).canSubmit).toBe(true);
  });
  it('never revises from rejected findings or missing clauses, and legal edits need a confirmed basis', () => {
    expect(revisionState(finding({ verification_status: 'rejected' }), { ...base, text: suggestion, manual: true }).canSubmit).toBe(false);
    expect(revisionState(finding({ block_id: null }), { ...base, text: suggestion, manual: true }).canSubmit).toBe(false);
    const legal = finding({ kind: 'legal', suggested_text: suggestion, revision_allowed: true, evidence_status: 'model_cited' });
    expect(revisionState(legal, { ...base, text: suggestion }).issue).toBe('请先确认已核对法规版本及适用性。');
    expect(revisionState(legal, { ...base, text: suggestion, legalBasis: true }).decision).toBe('accepted');
  });
});
