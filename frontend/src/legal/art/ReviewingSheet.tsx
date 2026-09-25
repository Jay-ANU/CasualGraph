import './art.css';

type Props = {
  className?: string;
  /** Rendered width in CSS px (height follows the 30 × 41 drawing). 30 renders 1:1. */
  size?: number;
  /** Show a still sheet instead of the reading loop, e.g. while queued. */
  paused?: boolean;
};

// [y, x0, x1, heading]: two short clauses, read top to bottom.
const ROWS: [number, number, number, boolean][] = [
  [8.5, 8.5, 15.5, true], [12.5, 10.5, 24.5, false], [16.5, 8.5, 24.5, false], [20.5, 8.5, 19.5, false],
  [26.5, 8.5, 16.5, true], [30.5, 10.5, 24.5, false], [34.5, 8.5, 17.5, false],
];

/**
 * A sheet being read: its lines are inked one after another, then the page
 * settles and the pass repeats (3.6 s). Replaces the generic spinner while a
 * review runs. Decorative only; progress must still be announced in text.
 */
export function ReviewingSheet({ className, size = 30, paused = false }: Props) {
  const classes = ['lv-art', 'lv-art-review', paused && 'lv-art-paused', className].filter(Boolean).join(' ');
  return <svg className={classes} width={size} height={(size * 41) / 30} viewBox="3 2 30 41" aria-hidden="true" focusable="false">
    <rect className="lv-art-under" x="6.5" y="5.5" width="26" height="37" rx="1" />
    <rect className="lv-art-sheet" x="3.5" y="2.5" width="26" height="37" rx="1" />
    {ROWS.map(([y, x0, x1, head]) => <path key={y} className={head ? 'lv-art-base-head' : 'lv-art-rule'} d={`M${x0} ${y}H${x1}`} />)}
    <g className="lv-art-reading">
      {ROWS.map(([y, x0, x1, head], i) => <path key={y} className={`lv-art-read lv-art-r${i}${head ? ' lv-art-headline' : ''}`} d={`M${x0} ${y}H${x1}`} />)}
    </g>
  </svg>;
}
