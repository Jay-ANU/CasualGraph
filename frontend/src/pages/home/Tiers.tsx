import { Check, Minus } from 'lucide-react';
import type { COPY } from './copy';

type Copy = (typeof COPY)['zh']['tiers'];

/** The four review depths, compared row by row. Scrolls sideways on narrow screens. */
export default function Tiers({ copy }: { copy: Copy }) {
  return (
    <div className="ap-tiers-scroll">
      <table className="ap-tiers">
        <thead>
          <tr>
            <th scope="col"><span className="sr-only">{copy.eyebrow}</span></th>
            {copy.columns.map((column, i) => (
              <th key={column.name} scope="col" className={i === 2 ? 'is-recommended' : ''}>
                <span className="ap-tier-tag">{column.tag}</span>
                <span className="ap-tier-name">{column.name}</span>
                <span className="ap-tier-note">{column.note}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {copy.rows.map(([label, cells]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              {cells.map((on, i) => (
                <td key={i} className={i === 2 ? 'is-recommended' : ''}>
                  {on ? <Check size={18} strokeWidth={2.4} aria-label="✓" /> : <Minus size={16} strokeWidth={2} aria-label="—" className="is-off" />}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ap-caption ap-tiers-foot">{copy.footnote}</p>
    </div>
  );
}
