import { describe, expect, it } from 'vitest';
import { defaultRevisionFormat, exportConflict, exportQuery, pendingExportPrompt } from './exportFlow';
import type { Review } from './types';

const review = (pending: number): Review => ({ id: 'r1', status: 'completed', stage: '', resumable: false,
  findings: [], coverage: [], sources: [], decisions: {}, policies: [], notice: '',
  export_state: { ready: true, pending_count: pending, selected_count: 0, fingerprint: 'current-draft', confirmation_required: pending > 0 } });

describe('user-controlled export', () => {
  it('downloads without confirmation when there are no pending items, including no edits', () => {
    expect(pendingExportPrompt(review(0), 'docx')).toBeNull();
    expect(exportQuery('docx', 'current-draft')).toBe('format=docx&fingerprint=current-draft');
  });
  it('shows the server count and confirms only that same draft', () => {
    const r = review(7);
    r.draft_check = { id: 'c1', status: 'rejected', fingerprint: 'old-draft', final_hash: '', checks: [], whole_contract: { status: 'conflict', reason: 'Synthetic model disagreement' }, missing_facts: [] };
    const prompt = pendingExportPrompt(r, 'txt');
    expect(prompt).toEqual({ format: 'txt', pendingCount: 7, fingerprint: 'current-draft' });
    expect(exportQuery('txt', prompt!.fingerprint, true)).toBe('format=txt&fingerprint=current-draft&confirmed=true');
  });
  it('keeps report exports separate from revision confirmation', () => {
    expect(exportQuery('md', 'old-draft', true)).toBe('format=json');
  });
  it('exports annotated PDF with the same user confirmation and leaves parsing notes informational', () => {
    const r = review(0);
    r.export_state = { ...r.export_state!, appendix_count: 3, parsing_issue_count: 7 };
    expect(defaultRevisionFormat({ format: 'pdf' })).toBe('pdf');
    expect(defaultRevisionFormat({ format: 'docx' })).toBe('docx');
    expect(defaultRevisionFormat({ format: 'txt' })).toBe('txt');
    expect(pendingExportPrompt(r, 'pdf')).toBeNull();
    expect(exportQuery('pdf', 'current-draft')).toBe('format=pdf&fingerprint=current-draft');
    expect(pendingExportPrompt(review(2), 'pdf')).toEqual({ format: 'pdf', pendingCount: 2, fingerprint: 'current-draft' });
    expect(exportQuery('pdf', 'current-draft', true)).toBe('format=pdf&fingerprint=current-draft&confirmed=true');
  });
  it('recognises changed drafts and updated pending counts without interpreting other errors as consent', () => {
    expect(exportConflict({ detail: { code: 'export_stale', pending_count: 2, fingerprint: 'new-draft' } }))
      .toEqual({ code: 'export_stale', pendingCount: 2, fingerprint: 'new-draft' });
    expect(exportConflict({ detail: { code: 'export_confirmation_required', pending_count: 3, fingerprint: 'current' } }))
      .toEqual({ code: 'export_confirmation_required', pendingCount: 3, fingerprint: 'current' });
    for (const detail of [null, 'missing', { code: 'export_failed' }, { code: 'export_stale', pending_count: -1, fingerprint: 'x' }, { code: 'export_stale', pending_count: 1, fingerprint: null }]) {
      expect(exportConflict({ detail })).toBeNull();
    }
  });
});
