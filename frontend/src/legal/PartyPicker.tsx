import { useMemo, useState } from 'react';
import { Check } from 'lucide-react';
import type { Block } from './types';
import { blockFragments, clauseLabel, partyCandidates } from './text';
import { RichText } from './ui';
import { ic } from './icon';

/**
 * The user binds “our party” to a verbatim quote. Suggestions only quote the
 * contract; nothing is pre-selected and the backend re-checks the quote.
 */
export function PartyPicker({ blocks, blockId, quote, disabled, onChange }: {
  blocks: Block[]; blockId: string; quote: string; disabled: boolean;
  onChange: (blockId: string, quote: string) => void;
}) {
  const candidates = useMemo(() => partyCandidates(blocks), [blocks]);
  const selected = blocks.find(b => b.id === blockId);
  const fragments = blockFragments(selected);
  const valid = quote.trim().length >= 2 && !!selected?.text.includes(quote);
  const custom = Boolean(blockId && quote && !candidates.some(c => c.blockId === blockId && c.quote === quote));
  const [manual, setManual] = useState(custom || !candidates.length);
  return <fieldset className="lv-party" disabled={disabled}>
    <legend className="lv-sr">我方主体</legend>
    {candidates.length > 0 && <div className="lv-party-options" role="group" aria-label="从原文选择主体片段">
      {candidates.map(c => {
        const on = c.blockId === blockId && c.quote === quote;
        return <button type="button" key={`${c.blockId}:${c.quote}`} aria-label={c.quote} aria-pressed={on} className={on ? 'selected' : ''} onClick={() => onChange(c.blockId, c.quote)}>
          <span className="lv-party-radio" aria-hidden="true">{on && <Check {...ic} size={11} strokeWidth={3} />}</span>
          <span className="lv-party-quote"><RichText text={c.quote} /></span>
          {c.context && <span className="lv-party-context"><RichText text={c.context} /></span>}
        </button>;
      })}
    </div>}
    {candidates.length > 0 && <button type="button" className="lv-text-button lv-party-toggle" aria-expanded={manual} onClick={() => setManual(!manual)}>手动指定</button>}
    {manual && <div className="lv-party-manual">
      <select className="lv-select" aria-label="我方主体所在段落" value={blockId} onChange={e => onChange(e.target.value, '')}>
        <option value="">选择主体所在段落</option>
        {blocks.map(b => <option key={b.id} value={b.id}>{clauseLabel(b, 30)}</option>)}
      </select>
      {fragments.length > 0 && <div className="lv-chips" role="group" aria-label="所选段落中的片段">
        {fragments.map(text => <button type="button" key={text} aria-label={text} aria-pressed={quote === text} className={quote === text ? 'selected' : ''} onClick={() => onChange(blockId, text)}><RichText text={text} /></button>)}
      </div>}
      <input className="lv-input" aria-label="我方主体原文" maxLength={200} value={quote} onChange={e => onChange(blockId, e.target.value)} placeholder="主体原文（须与段落内容一致）" />
    </div>}
    {quote && !valid && <p className="lv-note is-warn" role="alert">主体原文与所选段落不一致，请逐字填写。</p>}
  </fieldset>;
}
