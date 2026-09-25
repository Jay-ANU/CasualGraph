import './art.css';

type Props = {
  className?: string;
  /** Rendered width in CSS px (height follows the 63 × 71 drawing). 63 renders 1:1. */
  size?: number;
  /** Write the first line once on mount (about 1.2 s). */
  intro?: boolean;
};

/**
 * A blank rule sheet with a fountain pen writing the first line: the empty
 * state for company policies. Decorative only.
 */
export function PolicySheet({ className, size = 63, intro = true }: Props) {
  const classes = ['lv-art', 'lv-art-policy', intro && 'lv-art-intro', className].filter(Boolean).join(' ');
  return <svg className={classes} width={size} height={(size * 71) / 63} viewBox="12 1 63 71" aria-hidden="true" focusable="false">
    <rect className="lv-art-under" x="15.5" y="11.5" width="46" height="60" rx="1" />
    <rect className="lv-art-sheet" x="12.5" y="8.5" width="46" height="60" rx="1" />
    <path className="lv-art-title" d="M27.5 18h16" />
    <path className="lv-art-head" d="M19.5 28.5h4M19.5 39.5h4M19.5 50.5h4M19.5 61.5h4" />
    <path className="lv-art-blank" d="M26.5 39.5h25M26.5 50.5h25M26.5 61.5h25" />
    <path className="lv-art-ink" pathLength={1} d="M26.5 28.9c1.6-2 3.1 1.3 4.9-.3s2.9-1.7 4.6.1 3.1.9 4.9-.9" />
    <g className="lv-art-pen-move">
      <g className="lv-art-pen" transform="translate(40.9 27.8) rotate(-36)">
        <path className="lv-art-pen-body" d="M0 0C2-.5 4.6-1.9 7-2.3h2.5v4.6H7C4.6 1.9 2 .5 0 0Zm9.5-2.3 5-.3v5.2l-5-.3M14.5-3H37a3 3 0 0 1 0 6H14.5Z" />
        <path d="M1.4 0h3.8M26.5-3v6M38.2-3v-1.3h-8.7" />
        <circle className="lv-art-pen-hole" cx="6" cy="0" r=".6" />
      </g>
    </g>
  </svg>;
}
