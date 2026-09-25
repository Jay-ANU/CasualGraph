import { Fragment } from 'react';
import { Lock, Search, X } from 'lucide-react';
import type { Block, Contract, Review } from './types';
import { findingStatus } from './findingStatus';
import { fileTitle, strongestTone } from './labels';
import { isClauseHeading } from './text';
import { RichText } from './ui';
import { ic } from './icon';

function Paragraph({ text }: { text: string }) {
  const [first, ...rest] = text.split('\n');
  if (!rest.length || !isClauseHeading(first)) return <span className="lv-para-text"><RichText text={text} /></span>;
  return <span className="lv-para-text"><strong className="lv-para-heading"><RichText text={first} /></strong>{'\n'}<RichText text={rest.join('\n')} /></span>;
}

export function DocumentPane({ contract, review, blocks, visibleBlocks, query, selectedBlock, originalBlocks, onQuery, onClose, onParagraph }: {
  contract: Contract; review: Review | null; blocks: Block[]; visibleBlocks: Block[]; query: string; selectedBlock: string | null;
  originalBlocks: Block[] | null; onQuery: (value: string) => void; onClose: () => void; onParagraph: (block: Block) => void;
}) {
  const pageBreaks = new Set<string>();
  visibleBlocks.reduce<number | null>((previous, b) => {
    if (b.page != null && previous != null && b.page !== previous) pageBreaks.add(b.id);
    return b.page ?? previous;
  }, null);
  return <section className="lv-document" aria-label="脱敏合同正文">
    <header>
      <div><strong>合同正文</strong><span className="lv-chip">脱敏版本</span></div>
      <button className="lv-icon" aria-label="关闭原文面板" onClick={onClose}><X {...ic} size={18} /></button>
    </header>
    <label className="lv-document-search"><Search {...ic} size={15} />
      <input aria-label="查找合同正文" placeholder="在正文中查找" value={query} onChange={e => onQuery(e.target.value)} />
      <span>{visibleBlocks.length} / {blocks.length} 段</span></label>
    <div className="lv-document-scroll">
      <article className="lv-paper">
        <h2>{fileTitle(contract.name)}</h2>
        {visibleBlocks.map(b => {
          const open = review?.findings.filter(f => f.block_id === b.id && findingStatus(f) !== 'rejected') || [];
          const settled = open.length > 0 && open.every(f => review?.decisions[f.id]?.decision === 'accepted');
          const tone = settled ? 'accepted' : strongestTone(open);
          return <Fragment key={b.id}>
            {pageBreaks.has(b.id) && <div className="lv-page-break" aria-hidden="true"><span>第 {b.page} 页</span></div>}
            <button id={`legal-block-${b.id}`} className={`lv-paragraph ${selectedBlock === b.id ? 'focused' : ''} ${tone ? `has-findings tone-${tone}` : ''}`} onClick={() => onParagraph(b)}>
              {open.length > 0 && <span className="lv-para-flag">{settled ? '已采纳修改' : `${open.length} 条意见`}</span>}
              <Paragraph text={b.text} />
              {originalBlocks && <span className="lv-original"><strong>原件（不会发送给 AI）</strong>{originalBlocks.find(o => o.id === b.id)?.text || '没有匹配到原件内容'}</span>}
            </button>
          </Fragment>;
        })}
        {!visibleBlocks.length && <p className="lv-empty-result">正文中没有找到“{query.trim()}”。</p>}
      </article>
    </div>
    <footer><Lock {...ic} size={13} />原件对照只在本页显示，不会发送给 AI 模型；导出的修订稿会恢复真实信息。</footer>
  </section>;
}
