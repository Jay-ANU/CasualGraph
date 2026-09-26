import { describe, expect, it } from 'vitest';
import { researchGaps, reviewOutcome, reviewStatusLabel } from './labels';
import { ReviewReport } from './report';
import type { Review } from './types';

const review = (overrides: Partial<Review> = {}): Review => ({
  id: 'r1', status: 'partial', stage: '', resumable: false, findings: [], coverage: [], sources: [], decisions: {}, policies: [],
  notice: '合成提示', batch_errors: {}, retrieval: [{ rule_id: 'i1', status: 'retrieved', provider: 'bing_rss', warnings: [] }], ...overrides,
});

describe('review outcome', () => {
  it('calls a review partial only when a step did not run', () => {
    expect(reviewOutcome(review({ batch_errors: { '3': '模拟失败' } }))).toBe('failed_steps');
    expect(reviewOutcome(review({ coverage: [{ rule_id: 'x', title: '付款', status: 'not_reviewed', note: '' }] }))).toBe('failed_steps');
    expect(reviewStatusLabel(review({ batch_errors: { cross_check: '超时' } }))).toBe('部分完成');
  });
  it('treats missing official text as a basis to check, not a failed review', () => {
    const r = review({ retrieval: [{ rule_id: 'i1', status: 'no_verified_source', provider: 'bing_rss', warnings: [] },
                                   { rule_id: 'i2', status: 'retrieved', provider: 'bing_rss', warnings: [] }] });
    expect(reviewOutcome(r)).toBe('evidence_gaps');
    expect(researchGaps(r)).toBe(1);
    expect(reviewStatusLabel(r)).toBe('依据待核对');
    expect(ReviewReport(r)).toContain('审查状态：已完成（部分法律问题未取得官方原文）');
  });
  it('labels items to confirm without implying the review is unfinished', () => {
    expect(reviewOutcome(review())).toBe('to_confirm');
    expect(reviewStatusLabel(review())).toBe('待确认');
    expect(reviewOutcome(review({ status: 'completed' }))).toBeNull();
    expect(reviewStatusLabel(review({ status: 'completed' }))).toBe('待复核');
    expect(reviewStatusLabel(review({ status: 'failed' }))).toBe('已暂停');
  });
});
