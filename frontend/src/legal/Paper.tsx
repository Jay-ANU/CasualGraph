import { Fragment, useMemo } from 'react';
import type { ReactNode } from 'react';
import { Columns, Download, FileText, Image as ImageIcon } from 'lucide-react';
import type { Block, Contract, Decision, DocumentNode, SourceLocation } from './types';
import type { PartyCandidate } from './text';
import { diffText } from './diff';
import { fileTitle, findingTone, toneLabel } from './labels';
import type { Numbered, Run, Stage } from './workspace';
import { headingEnd, isRevised, markerState, paragraphRuns } from './workspace';
import { documentPages, imageTextNodes } from './documentLayout';
import { OriginalImage, OriginalPdf } from './DocumentSource';
import { Marker } from './Marker';
import { Redline, RichText } from './ui';
import { ic } from './icon';
import { useI18n } from '../i18n/core';
import { serverText } from './i18n';

type Props = {
  contract: Contract; blocks: Block[]; stage: Stage; decisions: Record<string, Decision>;
  /** Findings drawn on the paper at this stage, already numbered. */
  items: Numbered[]; selected: string | null; located: { id: string; n: number } | null;
  originals: Block[] | null; busy: boolean;
  sourceLocation?: SourceLocation | null; onOriginalDownload?: () => void;
  mode: 'revised' | 'changes'; onMode: (mode: 'revised' | 'changes') => void; onExport?: () => void;
  candidates: PartyCandidate[]; party: { blockId: string; quote: string };
  detail?: string;
  onSelect: (id: string) => void; onParty: (blockId: string, quote: string) => void; onCompare: () => void;
};

const LEGEND = ['high', 'mid', 'low', 'unconfirmed'] as const;

/** Original values in place of the placeholders; shown only while comparing, never sent to a model. */
function Compare({ redacted, original }: { redacted: string; original: string }) {
  const head = redacted.slice(0, headingEnd(redacted));
  const keep = head && original.startsWith(head) ? head : '';
  return <>{keep && <strong className="lv-para-heading">{keep}</strong>}
    {diffText(redacted.slice(keep.length), original.slice(keep.length)).map((part, i) => part.kind === 'same' ? <RichText key={i} text={part.text} />
      : part.kind === 'ins' ? <span key={i} className="lv-original">{part.text}</span> : null)}</>;
}

function Runs({ runs, blockId, selected, running, party, onParty }: {
  runs: Run[]; blockId: string; selected: string | null; running: boolean;
  party: { blockId: string; quote: string }; onParty: (blockId: string, quote: string) => void;
}) {
  const { tx } = useI18n();
  return <>{runs.map((run, i) => {
    let node: ReactNode = <RichText text={run.text} />;
    if (run.heading) node = <strong className="lv-para-heading">{node}</strong>;
    if (run.finding) {
      node = <span className={`lv-mark tone-${findingTone(run.finding)}${run.finding.id === selected ? ' is-selected' : ''}${running ? ' is-prelim' : ''}`}>{node}</span>;
    } else if (run.party) {
      const quote = run.party, on = party.blockId === blockId && party.quote === quote;
      node = <button type="button" className={`lv-pick${on ? ' is-on' : ''}`} aria-pressed={on} aria-label={tx(`在正文中选择我方主体：${quote}`, `Pick our party in the text: ${quote}`)}
        onClick={event => { event.stopPropagation(); onParty(blockId, quote); }}>{node}{on && <span className="lv-pick-tag" aria-hidden="true">{tx('我方', 'Our party')}</span>}</button>;
    }
    return <Fragment key={i}>{node}</Fragment>;
  })}</>;
}

/** Source containers preserve cells and images; their paragraph IDs remain the finding/edit anchors. */
export function Paper(p: Props) {
  const { tx } = useI18n();
  const pages = useMemo(() => documentPages(p.contract, p.blocks), [p.contract, p.blocks]);
  const imageTexts = useMemo(() => imageTextNodes(p.contract, p.blocks), [p.contract, p.blocks]);
  const blockMap = useMemo(() => new Map(p.blocks.map(block => [block.id, block])), [p.blocks]);
  const originalMap = useMemo(() => new Map(p.originals?.map(block => [block.id, block]) || []), [p.originals]);
  const itemMap = useMemo(() => {
    const result = new Map<string, Numbered[]>();
    for (const item of p.items) {
      const id = item.finding.block_id;
      if (id) result.set(id, [...(result.get(id) || []), item]);
    }
    return result;
  }, [p.items]);
  const originalView = p.originals !== null;
  const running = p.stage === 'running';
  const picking = p.stage === 'setup' && !originalView;
  const marking = (p.stage === 'results' && p.mode === 'changes') || running;
  const count = p.contract.replacement_count;
  const renderBlock = (blockId: string) => {
    const block = blockMap.get(blockId);
    if (!block) return null;
    const here = itemMap.get(block.id) || [];
    const revised = !originalView && (p.stage === 'results' || p.stage === 'export') ? here.find(x => isRevised(p.decisions[x.finding.id])) : undefined;
    const original = originalView ? originalMap.get(block.id) : undefined;
    const clickable = p.stage === 'results' && here.length > 0 && !originalView;
    const located = p.located?.id === block.id || p.sourceLocation?.block_id === block.id;
    const after = revised ? p.decisions[revised.finding.id].text : '';
    const head = block.text.slice(0, headingEnd(block.text));
    const afterHead = after.slice(0, headingEnd(after));
    const supplement = Boolean(revised && block.native_editable === false);
    const changes = head && after.startsWith(head)
      ? <><strong className="lv-para-heading"><RichText text={head} /></strong><Redline before={block.text.slice(head.length)} after={after.slice(head.length)} /></>
      : <Redline before={block.text} after={after} />;
    const draft = p.mode === 'revised'
      ? <>{afterHead && <strong className="lv-para-heading"><RichText text={afterHead} /></strong>}<RichText text={after.slice(afterHead.length)} /></> : changes;
    const body = original ? p.stage === 'redaction' ? <Compare redacted={block.text} original={original.text} /> : <RichText text={original.text} />
      : revised && !supplement ? draft
      : <Runs runs={paragraphRuns(block.text, picking ? p.candidates.filter(c => c.blockId === block.id).map(c => ({ quote: c.quote, party: c.quote }))
        : marking && !originalView ? here.map(x => ({ quote: x.finding.original_quote, finding: x.finding })) : [], headingEnd(block.text))}
        blockId={block.id} selected={p.selected} running={running} party={p.party} onParty={p.onParty} />;
    return <div key={`${block.id}-${located ? p.located?.n : 0}`} id={`legal-block-${block.id}`}
      className={`lv-block${here.some(x => x.finding.id === p.selected) ? ' is-selected' : ''}${clickable ? ' is-clickable' : ''}${located ? ' is-located' : ''}`}
      onClick={clickable ? () => p.onSelect(here[0].finding.id) : undefined}>
      {here.length > 0 && !picking && <span className="lv-margin">{here.map(x => {
        const marker = <Marker n={x.n} finding={x.finding} state={markerState(p.decisions[x.finding.id], running)} />;
        return p.stage === 'results' && !originalView
          ? <button key={x.finding.id} className="lv-margin-mark" aria-label={tx(`第 ${x.n} 条批注：${x.finding.title}`, `Note ${x.n}: ${x.finding.title}`)}
            onClick={event => { event.stopPropagation(); p.onSelect(x.finding.id); }}>{marker}</button>
          : <Fragment key={x.finding.id}>{marker}</Fragment>;
      })}</span>}
      <p className={`lv-para${block.heading_level ? ' is-heading' : ''}`}>
        {block.label && <span className="lv-paragraph-number">{block.label}{' '}</span>}{body}
      </p>
      {supplement && <div className="lv-source-supplement"><strong>{tx('补充修订 · 原件内容保留', 'Supplemental revision · Original content retained')}</strong><p className="lv-para">{draft}</p></div>}
    </div>;
  };
  const anchoredAssets = new Set<string>();
  const renderNode = (node: DocumentNode): ReactNode => {
    const located = p.sourceLocation?.node_id === node.id || (node.type === 'image' && p.sourceLocation?.asset_id === node.asset_id);
    if (node.type === 'paragraph') return <div key={node.id} id={`legal-node-${node.id}`}>{renderBlock(node.block_id)}</div>;
    if (node.type === 'image') {
      const assetAnchor = anchoredAssets.has(node.asset_id) ? undefined : `legal-asset-${node.asset_id}`;
      anchoredAssets.add(node.asset_id);
      return <figure key={node.id} id={`legal-node-${node.id}`} className={`lv-document-image${located ? ' is-located' : ''}`}>
      <div id={assetAnchor} className="lv-image-content">
        {originalView ? <OriginalImage contractId={p.contract.id} assetId={node.asset_id} width={node.width} height={node.height} />
          : <div className="lv-image-placeholder"><ImageIcon {...ic} size={24} aria-hidden="true" />
            <span>{tx('原件图片', 'Image in the original')}</span><p>{tx('图片可能含未脱敏信息，仅在“对照原件”中显示。', 'The image may contain unredacted information. It is shown only in the original view.')}</p></div>}
      </div>
      <figcaption>{node.block_ids?.length ? tx('图片文字（识别结果，请对照原件）', 'Recognised image text (check against the original)')
        : tx('图片内容未识别，未参与文字审查。', 'Image content has not been recognised and is not included in the text review.')}</figcaption>
      {imageTexts.get(node.id)?.map(renderNode)}
    </figure>;
    }
    const widths = node.column_widths;
    const total = widths?.reduce((sum, width) => sum + (Number.isFinite(width) && width > 0 ? width : 0), 0) || 0;
    return <div key={node.id} id={`legal-node-${node.id}`} className={`lv-contract-table-wrap${located ? ' is-located' : ''}`} tabIndex={0}
      role="region" aria-label={tx('合同表格，可横向滚动', 'Contract table, scroll horizontally')}>
      <table className="lv-contract-table" aria-label={tx('合同表格', 'Contract table')}>
        {widths && total > 0 && <colgroup>{widths.map((width, i) => <col key={i} style={width > 0 ? { width: `${width / total * 100}%` } : undefined} />)}</colgroup>}
        <tbody>{node.rows.map(row => <tr key={row.id}>{row.cells.map(cell => {
          const Cell = cell.header ? 'th' : 'td';
          return <Cell key={cell.id} data-cell-id={cell.id} rowSpan={Math.max(1, cell.row_span)} colSpan={Math.max(1, cell.col_span)}
            scope={cell.header ? 'col' : undefined}>
            {cell.children.map(renderNode)}
          </Cell>;
        })}</tr>)}</tbody>
      </table>
    </div>;
  };
  return <section className={`lv-paper-desk stage-${p.stage}`} aria-label={tx('合同正文', 'Contract text')}>
    <div className="lv-desk-bar">
      <span className="lv-desk-file"><FileText {...ic} size={14} /><span className="lv-desk-name">{p.contract.name}</span>
        <span aria-hidden="true">·</span><span>{p.stage === 'redaction' ? tx(`自动脱敏 ${count} 处`, `${count} auto-redacted`) : tx(`已脱敏 ${count} 处`, `${count} redacted`)}</span></span>
      {p.contract.original_available && <button className={`lv-toggle${originalView ? ' is-on' : ''}`} aria-pressed={originalView} disabled={p.busy} onClick={p.onCompare}>
        <Columns {...ic} size={14} />{tx('对照原件', 'Compare with original')}</button>}
      {p.stage === 'results' && !originalView && p.mode === 'changes' && p.items.length > 0 && <span className="lv-legend" aria-hidden="true">
        {LEGEND.map(t => <span key={t}><i className={`lv-legend-mark tone-${t}`} />{toneLabel(t)}</span>)}</span>}
      {p.stage === 'export' && !originalView && p.mode === 'changes' && <span className="lv-legend">{tx('修订预览', 'Revision preview')}<del>{tx('删除', 'Deleted')}</del><ins>{tx('新增', 'Inserted')}</ins></span>}
      {running && p.detail && <span className="lv-desk-detail">{serverText(p.detail)}</span>}
      {p.onExport && <div className="lv-draft-toolbar">
        <div role="group" aria-label={tx('修订稿显示方式', 'Draft display')}>
          <button className={`lv-toggle${!originalView && p.mode === 'revised' ? ' is-on' : ''}`} aria-pressed={!originalView && p.mode === 'revised'} onClick={() => p.onMode('revised')}>{tx('修订稿', 'Revised draft')}</button>
          <button className={`lv-toggle${!originalView && p.mode === 'changes' ? ' is-on' : ''}`} aria-pressed={!originalView && p.mode === 'changes'} onClick={() => p.onMode('changes')}>{tx('修订痕迹', 'Tracked changes')}</button>
        </div>
        <button className="lv-primary lv-btn-sm" disabled={p.busy} onClick={p.onExport}>{tx('导出修订稿', 'Export draft')}</button>
      </div>}
    </div>
    {!originalView && p.contract.format === 'pdf' && p.onExport && <p className="lv-source-notice">{tx('PDF 原页保留，修改将作为批注和附录导出；文字稿使用修改后的文字。',
      'PDF pages are retained; edits are exported as comments and an appendix. The text version uses the revised wording.')}</p>}
    {originalView && <div className="lv-source-notice">
      <p>{p.contract.format === 'docx' ? tx('原件结构预览（未脱敏）。表格、图片按来源位置显示；精确分页和浮动排版请以原 Word 为准。',
        'Original structure preview (unredacted). Tables and images follow source order; use the original Word file for exact pagination and floating layout.')
        : tx('正在本地查看未脱敏原件，不会因查看而发送给模型。', 'Viewing the unredacted original locally. Opening it does not send it to a model.')}</p>
      {p.onOriginalDownload && <button className="lv-text-button" disabled={p.busy} onClick={p.onOriginalDownload}><Download {...ic} size={14} />{tx('下载原文件', 'Download original')}</button>}
    </div>}
    {originalView && p.contract.format === 'pdf' ? <OriginalPdf contractId={p.contract.id} page={p.sourceLocation?.page} /> : <div className="lv-sheets">
      {pages.map((page, i) => <article className="lv-sheet" key={`${page.page}-${i}`}>
        <span id={page.page != null ? `legal-page-${page.page}` : undefined} />
        {i === 0 && <h1 className="lv-sheet-title">{fileTitle(p.contract.name)}</h1>}
        {page.nodes.map(renderNode)}
        {page.page != null && <footer className="lv-sheet-foot">{tx(`来源第 ${page.page} 页`, `Source page ${page.page}`)}</footer>}
      </article>)}
      {p.contract.document?.sections?.map(section => <article id={`legal-node-${section.id}`} className="lv-sheet lv-document-section" key={section.id}>
        <h2>{serverText(section.title)}</h2><p className="lv-source-status">{tx('原件附属内容；修改作为补充修订保留。', 'Additional source content; edits are retained as supplemental revisions.')}</p>
        {section.body.map(renderNode)}
      </article>)}
      {!pages.length && !p.contract.document?.sections?.length && <p className="lv-source-status">{tx('尚无可审查文字，请查看原件和解析提示。', 'No text is available for review. Open the original and check the parsing notes.')}</p>}
    </div>}
  </section>;
}
