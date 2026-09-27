import type { Finding } from './types';
import { findingTone } from './labels';
import type { MarkerState } from './workspace';
import { DrawnCheck } from './ui';

/**
 * A finding's number as it appears in the margin, the outline and the rail:
 * filled in its risk colour, dashed while preliminary or unconfirmed, a green
 * check once its revision is adopted, grey when the original is kept.
 */
export function Marker({ n, finding, state, size = 'md', number = false }: {
  n: number; finding: Finding; state: MarkerState; size?: 'sm' | 'md';
  /** Keep the number on an adopted finding, where the list is about which ones were adopted. */
  number?: boolean;
}) {
  return <span className={`lv-marker lv-marker-${size} tone-${findingTone(finding)} is-${state}`} aria-hidden="true">
    {state === 'revised' && !number ? <DrawnCheck size={size === 'sm' ? 9 : 11} /> : n}
  </span>;
}
