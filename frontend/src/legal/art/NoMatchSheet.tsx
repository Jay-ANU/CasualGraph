import './art.css';

type Props = {
  className?: string;
  /** Rendered width in CSS px (height follows the 38 × 50 drawing). 38 renders 1:1. */
  size?: number;
};

/**
 * A sheet whose flagged-clause slot is empty (dashed): nothing matches the
 * current filter. Deliberately neutral so it never reads as "no risk".
 * Decorative only.
 */
export function NoMatchSheet({ className, size = 38 }: Props) {
  return <svg className={['lv-art', 'lv-art-nomatch', className].filter(Boolean).join(' ')} width={size} height={(size * 50) / 38}
    viewBox="13 3 38 50" aria-hidden="true" focusable="false">
    <rect className="lv-art-under" x="16.5" y="6.5" width="34" height="46" rx="1" />
    <rect className="lv-art-sheet" x="13.5" y="3.5" width="34" height="46" rx="1" />
    <path className="lv-art-head" d="M19.5 10.5h8" />
    <path className="lv-art-rule" d="M21.5 15.5h20M19.5 20.5h17M21.5 40.5h20M19.5 45.5h14" />
    <rect className="lv-art-slot" x="16.5" y="24.5" width="28" height="11" rx="1" />
  </svg>;
}
