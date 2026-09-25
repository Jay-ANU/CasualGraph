import { useMemo } from 'react';
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
  const manual = Boolean(blockId && quote && !candidates.some(c => c.blockId === blockId && c.quote === quote));
  return <fieldset className="lv-party" disabled={disabled}>
    <legend className="lv-sr">我方对应合同中的哪一个主体？</legend>
    {candidates.length > 0 ? <div className="lv-party-options" role="group" aria-label="从原文选择主体片段">
      {candidates.map(c => {
        const on = c.blockId === blockId && c.quote === quote;
        return <button type="button" key={`${c.blockId}:${c.quote}`} aria-label={c.quote} aria-pressed={on} className={on ? 'selected' : ''} onClick={() => onChange(c.blockId, c.quote)}>
          <span className="lv-party-radio" aria-hidden="true">{on && <Check {...ic} size={12} strokeWidth={2.5} />}</span>
          <span className="lv-party-quote"><RichText text={c.quote} /></span>
          {c.context && <span className="lv-party-context">出自：<RichText text={c.context} /></span>}
        </button>;
      })}
    </div> : <p className="lv-hint">没有在开头段落找到“甲方：……”这类主体信息，请在下方手动指定。</p>}

    {valid && <p className="lv-party-selected" role="status"><Check {...ic} size={14} />已选择：<RichText text={quote} /></p>}
    {quote && !valid && <p className="lv-note is-warn" role="alert">填写的内容与所选段落不一致。请逐字复制合同原文，不能使用猜测或其他版本的主体信息。</p>}

    <details className="lv-disclosure lv-party-manual" open={manual || (!candidates.length) || undefined}>
      <summary>找不到？手动指定</summary>
      <div className="lv-disclosure-body">
        <label className="lv-field"><span className="lv-field-label">主体所在段落</span>
          <select className="lv-select" aria-label="我方主体所在段落" value={blockId} onChange={e => onChange(e.target.value, '')}>
            <option value="">选择段落</option>
            {blocks.map(b => <option key={b.id} value={b.id}>{clauseLabel(b, 30)}</option>)}
          </select></label>
        {selected && <blockquote className="lv-quote-box"><RichText text={selected.text} /></blockquote>}
        {fragments.length > 0 && <div className="lv-chips" role="group" aria-label="所选段落中的片段">
          {fragments.map(text => <button type="button" key={text} aria-label={text} aria-pressed={quote === text} className={quote === text ? 'selected' : ''} onClick={() => onChange(blockId, text)}><RichText text={text} /></button>)}
        </div>}
        <label className="lv-field"><span className="lv-field-label">代表我方的原文</span>
          <input className="lv-input" aria-label="我方主体原文" maxLength={200} value={quote} onChange={e => onChange(blockId, e.target.value)} placeholder="从所选段落中逐字复制" /></label>
      </div>
    </details>
  </fieldset>;
}
