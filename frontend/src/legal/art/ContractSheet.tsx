import './art.css';

type Props = {
  className?: string;
  /** Rendered width in CSS px (height follows the 77 × 105 drawing). 77 renders 1:1. */
  size?: number;
  /** Lift the sheet, e.g. while a file is dragged over the upload panel. */
  active?: boolean;
  /** Draw the redaction and review marks in sequence once on mount (about 1.2 s). */
  intro?: boolean;
};

/**
 * A contract as the desk shows it: parties redacted with ink bars, one clause
 * flagged in the margin, signature lines still blank. Decorative only.
 */
export function ContractSheet({ className, size = 77, active = false, intro = true }: Props) {
  const classes = ['lv-art', 'lv-art-contract', active && 'lv-art-active', intro && 'lv-art-intro', className].filter(Boolean).join(' ');
  return <svg className={classes} width={size} height={(size * 105) / 77} viewBox="18 4 77 105" aria-hidden="true" focusable="false">
    <rect className="lv-art-under" x="22.5" y="8.5" width="72" height="100" rx="1" />
    <g className="lv-art-lift">
      <rect className="lv-art-sheet" x="18.5" y="4.5" width="72" height="100" rx="1" />
      <path className="lv-art-title" d="M43.5 16h22" />
      <path className="lv-art-label" d="M28.5 28.5h4" />
      <rect className="lv-art-redact" x="35" y="27" width="18" height="3" rx=".75" />
      <path className="lv-art-label" d="M28.5 34.5h4" />
      <rect className="lv-art-redact lv-art-later" x="35" y="33" width="13" height="3" rx=".75" />
      <path className="lv-art-head" d="M28.5 44.5h11" />
      <path className="lv-art-rule" d="M32.5 49.5h48M28.5 54.5h52M28.5 59.5h38" />
      <rect className="lv-art-flag" x="21" y="65" width="67" height="25" />
      <path className="lv-art-flag-rule" d="M22 65v25" />
      <path className="lv-art-head" d="M28.5 70.5h13" />
      <circle className="lv-art-flag-dot" cx="79.5" cy="70.5" r="1.75" />
      <path className="lv-art-rule" d="M32.5 75.5h48M28.5 80.5h52M28.5 85.5h43" />
      <path className="lv-art-sign" d="M28.5 94.5h20M60.5 94.5h20" />
    </g>
  </svg>;
}
