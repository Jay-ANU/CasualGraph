import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { setCurrentLang } from '../i18n/core';
import { Paper } from './Paper';
import { ParsingIssues } from './ParsingIssues';
import { ReleasePanel } from './ReleasePanel';
import { contractHasText, documentPages, imageTextNodes, referencedBlocks, sourceElementIds, sourceLabel } from './documentLayout';
import { serverText } from './i18n';
import type { Block, Contract, Finding, Review } from './types';

const noop = () => undefined;
const b = (id: string, text: string, extra: Partial<Block> = {}): Block => ({ id, text, page: null, native_editable: true, ...extra });
const contract: Contract = { id: 'c1', name: 'Synthetic source.docx', status: 'ready', revision: 1, format: 'docx', org_id: 'o1', matter_id: 'm1',
  replacement_count: 1, warnings: [], reviews: [], original_available: true,
  blocks: [b('p1', '【脱敏1】交付清单', { label: '1.', heading_level: 1 }), b('p2', 'Project'), b('p3', '100'), b('p4', '200'),
    b('ocr1', 'Recognised seal text', { kind: 'ocr', native_editable: false }), b('header1', 'Source header', { native_editable: false })],
  assets: [{ id: 'a1', media_type: 'image/png' }],
  document: { version: 1, source: 'docx', pages: [], issues: [{ id: 'issue1', code: 'ocr_unavailable', message: 'Synthetic image needs checking', node_id: 'img1', asset_id: 'a1' }],
    body: [{ type: 'paragraph', id: 'n1', block_id: 'p1' }, { type: 'table', id: 't1', column_widths: [100, 150, 150], rows: [
      { id: 'r0', cells: [{ id: 'c0', row: 0, col: 0, row_span: 2, col_span: 1, header: true, children: [{ type: 'paragraph', id: 'n2', block_id: 'p2' }] },
        { id: 'c1', row: 0, col: 1, row_span: 1, col_span: 2, children: [{ type: 'paragraph', id: 'n3', block_id: 'p3' }] }] },
      { id: 'r1', cells: [{ id: 'c2', row: 1, col: 1, row_span: 1, col_span: 2, children: [{ type: 'paragraph', id: 'n4', block_id: 'p4' }] }] },
    ] }, { type: 'image', id: 'img1', asset_id: 'a1', block_ids: ['ocr1'] }],
    sections: [{ id: 'header', kind: 'header', title: 'Header', read_only: true, body: [{ type: 'paragraph', id: 'nh1', block_id: 'header1' }] }] } };
const finding: Finding = { id: 'f1', block_id: 'p3', original_quote: '100', title: 'Synthetic amount', kind: 'commercial', severity: 'medium',
  impact: '', reason: '', suggested_text: '150', evidence_status: 'not_applicable', missing_facts: [], citations: [], policy_ids: [] };
const review: Review = { id: 'r1', status: 'completed', stage: '', resumable: false, findings: [finding], coverage: [], sources: [], policies: [], notice: '',
  decisions: { f1: { decision: 'draft', text: '150', version: 1, source: 'model' } } };
const paper = (extra: Partial<Parameters<typeof Paper>[0]> = {}) => renderToStaticMarkup(<Paper contract={contract} blocks={contract.blocks} stage="results"
  decisions={review.decisions} items={[{ finding, n: 1 }]} selected="f1" located={null} originals={null} busy={false} mode="revised" onMode={noop}
  onExport={noop} candidates={[]} party={{ blockId: '', quote: '' }} onSelect={noop} onParty={noop} onCompare={noop} {...extra} />);
afterEach(() => { setCurrentLang('zh'); vi.unstubAllGlobals(); });

describe('structured contract reading and revision', () => {
  it('keeps horizontal and vertical merged cells and the finding’s exact paragraph anchor', () => {
    const html = paper();
    expect(html).toMatch(/rowspan="2" colspan="1"/i);
    expect(html).toMatch(/colspan="2"/i);
    expect(html).toContain('id="legal-block-p3"');
    expect(html).toContain('150');
    expect(html).not.toContain('>100<');
    expect(html).toContain('第 1 条批注：Synthetic amount');
    expect(html).toContain('lv-paragraph-number">1. ');
    expect(contract.blocks[0].text).toBe('【脱敏1】交付清单');
  });
  it('keeps images confidential until original view and renders each OCR/source paragraph once', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    const html = paper();
    expect(html).not.toContain('<img');
    expect(html).not.toContain('/assets/');
    expect(html).toContain('图片文字（识别结果，请对照原件）');
    expect(html.match(/id="legal-block-ocr1"/g)).toHaveLength(1);
    expect(html.match(/id="legal-block-header1"/g)).toHaveLength(1);
    expect(html).toContain('id="legal-node-header"');
    expect(fetch).not.toHaveBeenCalled();
    const originals = contract.blocks.map(block => ({ ...block, text: block.text.replace('【脱敏1】', 'Synthetic Original Name') }));
    const original = paper({ originals });
    expect(original).toContain('Synthetic Original Name');
    expect(original).toContain('原件结构预览');
    expect(original).toContain('正在读取原件图片');
    expect(original).toContain('>100<');
    expect(original).not.toContain('>150<');
    const repeated = structuredClone(contract);
    repeated.document!.body.push({ type: 'image', id: 'img2', asset_id: 'a1' });
    const copies = paper({ contract: repeated });
    expect(copies.match(/id="legal-asset-a1"/g)).toHaveLength(1);
    expect(copies).toContain('id="legal-node-img2"');
  });
  it('shows edits to non-native content as supplements while retaining the source wording', () => {
    const item = { ...finding, block_id: 'ocr1', suggested_text: 'Revised seal wording' };
    const html = paper({ items: [{ finding: item, n: 1 }], decisions: { f1: { decision: 'draft', text: item.suggested_text, version: 1 } } });
    expect(html).toContain('Recognised seal text');
    expect(html).toContain('Revised seal wording');
    expect(html).toContain('补充修订 · 原件内容保留');
  });
  it('retains OCR table cells, spans and empty positions without treating the image host cell as a nested table', () => {
    const source = structuredClone(contract);
    const image = source.document!.body.find(node => node.type === 'image')!;
    if (image.type !== 'image') throw new Error('Image fixture missing');
    const host = source.blocks.find(block => block.id === 'ocr1')!;
    host.table = { id: 't1', cell_id: 'c2', row: 1, col: 1, row_span: 1, col_span: 2 };
    const ocrCells = [
      b('ocr2', 'Recognised items', { table: { id: 'image-table', cell_id: 'ic1', row: 0, col: 0, row_span: 1, col_span: 2, header: true } }),
      b('ocr3', 'Recognised amount', { table: { id: 'image-table', cell_id: 'ic2', row: 1, col: 1, row_span: 1, col_span: 1 } }),
      b('ocr4', 'Shared label', { table: { id: 'image-table', cell_id: 'ic3', row: 2, col: 0, row_span: 2, col_span: 1 } }),
      b('ocr5', 'First value', { table: { id: 'image-table', cell_id: 'ic4', row: 2, col: 1, row_span: 1, col_span: 1 } }),
      b('ocr6', 'Second value', { table: { id: 'image-table', cell_id: 'ic5', row: 3, col: 1, row_span: 1, col_span: 1 } }),
    ].map(block => ({ ...block, kind: 'ocr', native_editable: false }));
    source.blocks.push(...ocrCells); image.block_ids!.push(...ocrCells.map(block => block.id));
    const nodes = imageTextNodes(source, source.blocks).get('img1')!;
    expect(nodes[0]).toMatchObject({ type: 'paragraph', block_id: 'ocr1' });
    expect(nodes).toHaveLength(2);
    const table = nodes[1]; if (table.type !== 'table') throw new Error('OCR table missing');
    expect(table.rows).toHaveLength(4);
    expect(table.rows[0].cells[0]).toMatchObject({ col_span: 2, header: true });
    expect(table.rows[1].cells[0]).toMatchObject({ col: 0, children: [] });
    expect(table.rows[1].cells[1].children[0]).toMatchObject({ block_id: 'ocr3' });
    expect(table.rows[2].cells[0].row_span).toBe(2);
    expect(table.rows[3].cells).toHaveLength(1);
    const html = paper({ contract: source, blocks: source.blocks });
    expect(html.match(/<table class="lv-contract-table"/g)).toHaveLength(2);
    expect(html.match(/id="legal-block-ocr3"/g)).toHaveLength(1);
    expect(html).not.toContain('<img');
  });
  it('keeps pages with only images visible and does not invent DOCX pagination', () => {
    expect(documentPages(contract, contract.blocks)).toHaveLength(1);
    const pdf: Contract = { ...contract, format: 'pdf', blocks: [], document: { version: 1, source: 'pdf', pages: [{ number: 2, width: 600, height: 800 }],
      body: [{ type: 'image', id: 'page2', asset_id: 'a1', page: 2 }], issues: [] } };
    expect(documentPages(pdf, pdf.blocks)).toEqual([{ page: 2, nodes: pdf.document!.body }]);
    expect(contractHasText(pdf)).toBe(false);
    expect(contractHasText({ ...contract, reviewable: false })).toBe(false);
    expect(paper({ contract: pdf, blocks: [] })).toContain('图片内容未识别');
  });
  it('falls back for old contracts and retains unplaced text without repeating section text', () => {
    const old = { ...contract, document: undefined };
    expect(documentPages(old, contract.blocks).flatMap(page => page.nodes)).toHaveLength(contract.blocks.length);
    const blocks = [...contract.blocks, b('unplaced', 'Additional extracted text')];
    const nodes = documentPages(contract, blocks).flatMap(page => page.nodes);
    expect(referencedBlocks(nodes).has('unplaced')).toBe(true);
    expect(referencedBlocks(nodes).has('header1')).toBe(false);
  });
  it('discloses source locations and offers annotated PDF alongside explicit plain text in English', () => {
    setCurrentLang('en');
    const block = b('p2', 'Synthetic', { page: 3, table: { id: 't1', cell_id: 'c0', row: 1, col: 2, row_span: 1, col_span: 1 } });
    expect(sourceLabel({}, block)).toBe('Page 3 · Table row 2, column 3');
    expect(sourceElementIds({ block_id: 'p2', node_id: 'n2', asset_id: 'a1', page: 3 })).toEqual(['legal-block-p2', 'legal-node-n2', 'legal-asset-a1', 'legal-page-3']);
    expect(renderToStaticMarkup(<ParsingIssues contract={contract} onLocate={noop} />)).toContain('Show location: ');
    expect(serverText('尚未配置私有 OCR 服务；原图已保留，图片文字等待识别。')).toContain('not configured');
    expect(serverText('第 2 页尚无可审查文字，已保留原页，等待 OCR 或人工核对。')).toContain('Page 2 has no reviewable text');
    const html = renderToStaticMarkup(<ReleasePanel review={review} contract={{ ...contract, format: 'pdf' }} open={[{ finding, n: 1 }]} busy={false}
      onCheck={noop} onReport={noop} onDraft={noop} onBack={noop} />);
    expect(html).toContain('Annotated original PDF');
    expect(html).toContain('Original pages retained; edits appear in comments and an appendix');
    expect(html).toContain('Export text');
    expect(html.match(/<button\b[^>]*>Export annotated PDF<\/button>/)?.[0]).not.toContain('disabled');
  });
});
