import type { Contract, Review } from './types';

export type RevisionFormat = 'docx' | 'pdf' | 'txt';
export type ExportPrompt = { format: RevisionFormat; pendingCount: number; fingerprint: string };
export const defaultRevisionFormat = (contract: Pick<Contract, 'format'>): RevisionFormat => contract.format === 'docx' ? 'docx' : contract.format === 'pdf' ? 'pdf' : 'txt';

/** The count and fingerprint come from the same server snapshot. */
export function pendingExportPrompt(review: Review, format: RevisionFormat): ExportPrompt | null {
  const state = review.export_state;
  return state?.ready && state.pending_count > 0 && state.fingerprint
    ? { format, pendingCount: state.pending_count, fingerprint: state.fingerprint } : null;
}

export function exportQuery(format: RevisionFormat | 'md', fingerprint?: string | null, confirmed = false): string {
  const query = new URLSearchParams({ format: format === 'md' ? 'json' : format });
  if (format !== 'md') {
    if (fingerprint) query.set('fingerprint', fingerprint);
    if (confirmed) query.set('confirmed', 'true');
  }
  return query.toString();
}

type ExportConflict = { code: 'export_confirmation_required' | 'export_stale'; pendingCount: number; fingerprint: string };

/** Only the two structured export responses may open or invalidate a confirmation. */
export function exportConflict(payload: unknown): ExportConflict | null {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return null;
  const d = payload.detail;
  if (!d || typeof d !== 'object' || !('code' in d) || !('pending_count' in d) || !('fingerprint' in d)) return null;
  if ((d.code !== 'export_confirmation_required' && d.code !== 'export_stale') || typeof d.fingerprint !== 'string'
    || !d.fingerprint || typeof d.pending_count !== 'number' || !Number.isInteger(d.pending_count) || d.pending_count < 0) return null;
  return { code: d.code, pendingCount: d.pending_count, fingerprint: d.fingerprint };
}
