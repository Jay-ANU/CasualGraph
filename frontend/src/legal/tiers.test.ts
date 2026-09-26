import { describe, expect, it } from 'vitest';
import { findingCounts, findingStatus, revisionState } from './findingStatus';
import { availableTiers, findingTone, reviewStatusLabel, tierOf } from './labels';
import { phaseSteps } from './reviewActivity';
import { ReviewReport } from './report';
import type { Finding, Review } from './types';

const finding = (overrides: Partial<Finding> = {}): Finding => ({
  id: 'f1', block_id: 'p1', original_quote: '合成原文', title: '合成风险', kind: 'commercial', severity: 'high', impact: '合成影响',
  reason: '合成理由', suggested_text: '合成修改', evidence_status: 'not_applicable', missing_facts: [], citations: [], policy_ids: [],
  verification_status: 'skipped', revision_allowed: false, ...overrides,
});
const review = (overrides: Partial<Review> = {}): Review => ({
  id: 'r1', status: 'completed', stage: '', resumable: false, findings: [finding()], coverage: [], sources: [], decisions: {}, policies: [],
  notice: '合成提示', review_tier: 'ultra_fast', ...overrides,
});

describe('review tiers', () => {
  it('offers only standard and deep when the backend predates tiers', () => {
    expect(availableTiers(null).map(t => t.value)).toEqual(['standard', 'deep']);
    expect(availableTiers({ review_tiers: ['ultra_fast', 'fast', 'standard', 'deep'] }).map(t => t.title)).toEqual(['极速', '快速', '标准', '深度']);
  });
  it('keeps the original mode of reviews created before tiers', () => {
    expect(tierOf({ profile: { review_mode: 'multi_agent' } })).toBe('deep');
    expect(tierOf({ profile: {} })).toBe('standard');
    expect(tierOf({ review_tier: 'fast', profile: { review_mode: 'multi_agent' } })).toBe('fast');
  });
  it('runs only the steps the tier has', () => {
    expect(phaseSteps(review()).map(s => s.label)).toEqual(['读取合同', '分项审查']);
    expect(phaseSteps(review({ review_tier: 'fast' })).map(s => s.label)).toEqual(['读取合同', '分项审查', '逐项复核']);
    expect(phaseSteps(review({ review_tier: 'deep' })).map(s => s.label)).toEqual(['读取合同', '检索法规', '分项审查', '汇总复核']);
  });
});

describe('ultra-fast findings', () => {
  it('count by severity, stay labelled unverified and are adopted only as human revisions', () => {
    const f = finding();
    expect(findingStatus(f)).toBe('quick');
    expect(findingTone(f)).toBe('high');
    expect(findingCounts([f]).high).toBe(1);
    const state = revisionState(f, { done: true, busy: false, text: f.suggested_text, original: '合成原文', legalBasis: false, manual: false });
    expect(state.adoptable).toBe(false);
    expect(state.decision).toBe('draft');
    expect(state.issue).toBe('请确认保存为人工修订。');
    expect(findingStatus(finding({ missing_facts: ['缺少附件'] }))).toBe('unconfirmed');
  });
  it('say so in the status label and the report', () => {
    expect(reviewStatusLabel(review())).toBe('未复核');
    const text = ReviewReport(review({ research: { status: 'skipped', issues: [] },
      skills: [{ id: 'review-method', name: '合同审查方法', version: '1.0.0', reason: '通用审查方法' }] }));
    expect(text).toContain('审查方式：极速审查');
    expect(text).toContain('风险等级：高风险（未经复核）');
    expect(text).toContain('合同审查方法（v1.0.0）：通用审查方法');
    expect(text).toContain('本档位不检索法规');
  });
});
