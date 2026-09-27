import type { Decision } from './types';
import type { Numbered, OutlineEntry } from './workspace';
import { markerState } from './workspace';
import { Marker } from './Marker';
import { RichText } from './ui';

/** The contract's clauses with the numbers of the findings in each; the review's facts at the foot. */
export function Outline({ entries, items, decisions, running, activeBlock, blockCount, pageCount, meta, onEntry }: {
  entries: OutlineEntry[]; items: Numbered[]; decisions: Record<string, Decision>; running: boolean;
  activeBlock: string | null; blockCount: number; pageCount: number; meta: { k: string; v: string }[];
  onEntry: (entry: OutlineEntry, firstFinding?: string) => void;
}) {
  return <nav className="lv-outline" aria-label="条款目录">
    <div className="lv-outline-head"><span>条款</span><span className="lv-mono">{blockCount} 段{pageCount > 1 ? ` · ${pageCount} 页` : ''}</span></div>
    <ol className="lv-outline-list">
      {entries.map(entry => {
        const marks = items.filter(x => x.finding.block_id && entry.blockIds.includes(x.finding.block_id));
        const active = Boolean(activeBlock && entry.blockIds.includes(activeBlock));
        return <li key={entry.id}>
          <button className={active ? 'is-active' : ''} aria-current={active ? 'true' : undefined} onClick={() => onEntry(entry, marks[0]?.finding.id)}>
            <span className="lv-outline-no">{entry.no}</span>
            <span className="lv-outline-name"><RichText text={entry.name} /></span>
            {marks.length > 0 && <span className="lv-outline-marks">
              {marks.map(x => <Marker key={x.finding.id} n={x.n} finding={x.finding} state={markerState(decisions[x.finding.id], running)} size="sm" />)}
              <span className="lv-sr">，{marks.length} 条批注</span>
            </span>}
          </button>
        </li>;
      })}
    </ol>
    {meta.length > 0 && <dl className="lv-outline-meta">{meta.map(m => <div key={m.k}><dt>{m.k}</dt><dd title={m.v}>{m.v}</dd></div>)}</dl>}
  </nav>;
}
