import type { Decision } from './types';
import type { Numbered, OutlineEntry } from './workspace';
import { markerState } from './workspace';
import { Marker } from './Marker';
import { RichText } from './ui';
import { useI18n } from '../i18n/core';
import { plural } from './i18n';

/** The contract's clauses with the numbers of the findings in each; the review's facts at the foot. */
export function Outline({ entries, items, decisions, running, activeBlock, blockCount, pageCount, meta, onEntry }: {
  entries: OutlineEntry[]; items: Numbered[]; decisions: Record<string, Decision>; running: boolean;
  activeBlock: string | null; blockCount: number; pageCount: number; meta: { k: string; v: string }[];
  onEntry: (entry: OutlineEntry, firstFinding?: string) => void;
}) {
  const { tx } = useI18n();
  return <nav className="lv-outline" aria-label={tx('条款目录', 'Clause outline')}>
    <div className="lv-outline-head"><span>{tx('条款', 'Clauses')}</span><span className="lv-mono">
      {tx(`${blockCount} 段`, plural(blockCount, 'paragraph'))}{pageCount > 1 ? tx(` · ${pageCount} 页`, ` · ${plural(pageCount, 'page')}`) : ''}</span></div>
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
              <span className="lv-sr">{tx(`，${marks.length} 条批注`, `, ${plural(marks.length, 'note')}`)}</span>
            </span>}
          </button>
        </li>;
      })}
    </ol>
    {meta.length > 0 && <dl className="lv-outline-meta">{meta.map(m => <div key={m.k}><dt>{m.k}</dt><dd title={m.v}>{m.v}</dd></div>)}</dl>}
  </nav>;
}
