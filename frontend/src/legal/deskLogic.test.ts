import { describe, expect, it } from 'vitest';
import { uploadIssue, visibleFindings, pendingDecisions } from './deskLogic';
import type { Finding, Review } from './types';
const finding = (id: string, extra: Partial<Finding> = {}): Finding => ({ id, block_id: 'p1', original_quote: '合成原文', title: '付款保障', kind: 'commercial', severity: 'high', impact: '预付风险', reason: '交付时间未约定', suggested_text: '合成修改', evidence_status: 'not_applicable', missing_facts: [], citations: [], policy_ids: [], verification_status: 'supported', ...extra });
const review = (findings: Finding[]): Review => ({ id: 'r1', status: 'completed', stage: '', resumable: false, findings, coverage: [], sources: [], decisions: {}, policies: [], notice: '' });
describe('consumer contract desk preflight', () => {
  it.each(['DOCX', 'pdf', 'txt'])('accepts supported %s without submitting it', extension => {
    expect(uploadIssue({ name: `合同.${extension}`, size: 1024 })).toBe('');
  });
  it.each(['合同.doc', '合同.pdf.exe', '合同'])('rejects %s', name => {
    expect(uploadIssue({ name, size: 100 })).toContain('DOCX');
  });
  it('rejects empty and oversized files and permits exactly 10 MiB', () => {
    expect(uploadIssue({ name: '合同.txt', size: 0 })).toContain('空');
    expect(uploadIssue({ name: '合同.txt', size: 10 * 1024 * 1024 + 1 })).toContain('10 MB');
    expect(uploadIssue({ name: '合同.txt', size: 10 * 1024 * 1024 })).toBe('');
  });
});
describe('review prioritisation and honest counts', () => {
  it('prioritises unresolved supported high risks; preserves equal-priority order', () => {
    const r = review([finding('low', { severity: 'low' }), finding('decided'), finding('rejected', { verification_status: 'rejected' }), finding('unknown', { verification_status: 'uncertain' }), finding('high1'), finding('high2')]);
    r.decisions.decided = { decision: 'accepted', text: '', version: 1 };
    expect(visibleFindings(r, 'all', 'all', '').map(f => f.id)).toEqual(['high1', 'high2', 'unknown', 'low', 'decided', 'rejected']);
  });
  it('includes manual drafts in pending work but not rejected candidates or retained originals', () => {
    const r = review([finding('pending'), finding('draft'), finding('accepted'), finding('kept'), finding('rejected', { verification_status: 'rejected' })]);
    for (const [id, decision] of [['draft', 'draft'], ['accepted', 'accepted'], ['kept', 'rejected']]) r.decisions[id] = { decision, text: '', version: 1 };
    expect(pendingDecisions(r)).toBe(2);
    expect(visibleFindings(r, 'all', 'pending', '').map(f => f.id)).toEqual(['pending', 'draft']);
    expect(visibleFindings(r, 'all', 'rejected', '').map(f => f.id)).toEqual(['kept']);
  });
  it('combines text, category and verification filters without mutating a review', () => {
    const r = review([finding('x'), finding('y', { kind: 'legal', verification_status: 'uncertain', title: 'ABC 条款' })]);
    const before = JSON.stringify(r);
    expect(visibleFindings(r, 'legal', 'unconfirmed', ' abc ').map(f => f.id)).toEqual(['y']);
    expect(visibleFindings(r, 'all', 'all', '交付').length).toBe(2);
    expect(visibleFindings(r, 'commercial', 'unconfirmed', '')).toEqual([]);
    expect(JSON.stringify(r)).toBe(before);
  });
});
