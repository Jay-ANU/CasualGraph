import { pick } from '../i18n/core';
import type { Block, Contract, DocumentNode, ImageNode, SourceLocation, TableCell, TableNode } from './types';
import { pagesOf } from './workspace';

export type DocumentPage = { page: number | null; nodes: DocumentNode[] };

/** Paragraph IDs remain the edit anchors; a table or image is only their structural container. */
export function referencedBlocks(nodes: DocumentNode[], result = new Set<string>()): Set<string> {
  for (const node of nodes) {
    if (node.type === 'paragraph') result.add(node.block_id);
    else if (node.type === 'image') node.block_ids?.forEach(id => result.add(id));
    else for (const row of node.rows) for (const cell of row.cells) referencedBlocks(cell.children, result);
  }
  return result;
}

/** OCR keeps text in blocks too. Reconstruct recognised cells without inventing a table around ordinary image text. */
export function imageTextNodes(contract: Contract, blocks: Block[]): Map<string, DocumentNode[]> {
  const images: ImageNode[] = [], sourceTables = new Set<string>();
  const walk = (nodes: DocumentNode[]) => {
    for (const node of nodes) {
      if (node.type === 'image') images.push(node);
      else if (node.type === 'table') {
        sourceTables.add(node.id);
        node.rows.forEach(row => row.cells.forEach(cell => walk(cell.children)));
      }
    }
  };
  walk(contract.document?.body || []);
  contract.document?.sections?.forEach(section => walk(section.body));
  const byId = new Map(blocks.map(block => [block.id, block]));
  return new Map(images.map(image => {
    const nodes: DocumentNode[] = [], tables = new Map<string, { node: TableNode; cells: Map<string, TableCell> }>();
    for (const id of image.block_ids || []) {
      const block = byId.get(id);
      if (!block) continue;
      const paragraph: DocumentNode = { type: 'paragraph', id: `image-text-${id}`, block_id: id };
      const meta = block.table;
      // An image placed inside a Word cell inherits its host table coordinates. It is not itself another table.
      if (!meta || sourceTables.has(meta.id) || ![meta.row, meta.col, meta.row_span, meta.col_span].every(Number.isInteger)
        || meta.row < 0 || meta.col < 0 || meta.row_span < 1 || meta.col_span < 1
        || meta.row + meta.row_span > 600 || meta.col + meta.col_span > 600) { nodes.push(paragraph); continue; }
      let table = tables.get(meta.id);
      if (!table) {
        table = { node: { type: 'table', id: `ocr-${image.id}-${meta.id}`, rows: [] }, cells: new Map() };
        tables.set(meta.id, table); nodes.push(table.node);
      }
      let cell = table.cells.get(meta.cell_id);
      if (!cell) {
        cell = { id: `${image.id}-${meta.cell_id}`, row: meta.row, col: meta.col, row_span: meta.row_span,
          col_span: meta.col_span, header: meta.header, children: [] };
        table.cells.set(meta.cell_id, cell);
      }
      cell.children.push(paragraph);
    }
    for (const { node, cells } of tables.values()) {
      const values = [...cells.values()], occupied = new Set<string>();
      const starts = new Map(values.map(cell => [`${cell.row}:${cell.col}`, cell]));
      const rows = Math.max(...values.map(cell => cell.row + cell.row_span));
      const cols = Math.max(...values.map(cell => cell.col + cell.col_span));
      for (const cell of values) for (let row = cell.row; row < cell.row + cell.row_span; row++)
        for (let col = cell.col; col < cell.col + cell.col_span; col++) occupied.add(`${row}:${col}`);
      // Empty OCR cells have no text block. Retain their space so later cells do not shift into the wrong column.
      for (let row = 0; row < rows; row++) {
        const rowCells: TableCell[] = [];
        for (let col = 0; col < cols;) {
          const cell = starts.get(`${row}:${col}`);
          if (cell) { rowCells.push(cell); col += cell.col_span; }
          else if (occupied.has(`${row}:${col}`)) col++;
          else {
            const start = col++;
            while (col < cols && !occupied.has(`${row}:${col}`)) col++;
            rowCells.push({ id: `${node.id}-empty-${row}-${start}`, row, col: start, row_span: 1, col_span: col - start, children: [] });
          }
        }
        node.rows.push({ id: `${node.id}-row-${row}`, cells: rowCells });
      }
    }
    return [image.id, nodes];
  }));
}

/** Old contracts retain their flat reading view. New ones use the source tree without duplicating OCR text. */
export function documentPages(contract: Contract, blocks: Block[]): DocumentPage[] {
  const doc = contract.document;
  if (doc?.version !== 1) return pagesOf(blocks).map(group => ({ page: group.page,
    nodes: group.blocks.map(block => ({ type: 'paragraph', id: `paragraph-${block.id}`, block_id: block.id })) }));
  const byId = new Map(blocks.map(block => [block.id, block]));
  const groups = new Map<number | null, DocumentNode[]>();
  if (doc.source === 'pdf') doc.pages.forEach(page => groups.set(page.number, []));
  const pageOf = (node: DocumentNode): number | null => {
    if (node.page != null) return node.page;
    if (node.type === 'paragraph') return byId.get(node.block_id)?.page ?? null;
    if (node.type === 'image') return node.block_ids?.map(id => byId.get(id)?.page).find(page => page != null) ?? null;
    return node.rows.flatMap(row => row.cells.flatMap(cell => cell.children)).map(pageOf).find(page => page != null) ?? null;
  };
  const add = (node: DocumentNode) => {
    const page = doc.source === 'pdf' ? pageOf(node) : null;
    if (!groups.has(page)) groups.set(page, []);
    groups.get(page)!.push(node);
  };
  doc.body.forEach(add);
  // Never hide text from an incomplete/older structure response. Section text stays in its own section.
  const placed = referencedBlocks(doc.body);
  doc.sections?.forEach(section => referencedBlocks(section.body, placed));
  blocks.filter(block => !placed.has(block.id)).forEach(block => add({ type: 'paragraph', id: `paragraph-${block.id}`, block_id: block.id }));
  return [...groups].map(([page, nodes]) => ({ page, nodes }));
}

export function sourceLabel(location: SourceLocation, block?: Block): string {
  const page = location.page ?? block?.page;
  const parts: string[] = [];
  if (page != null) parts.push(pick(`第 ${page} 页`, `Page ${page}`));
  if (block?.table) parts.push(pick(`表格第 ${block.table.row + 1} 行、第 ${block.table.col + 1} 列`, `Table row ${block.table.row + 1}, column ${block.table.col + 1}`));
  return parts.join(' · ') || pick('原件位置', 'Source location');
}

export function sourceElementIds(location: SourceLocation): string[] {
  return [location.block_id && `legal-block-${location.block_id}`, location.node_id && `legal-node-${location.node_id}`,
    location.asset_id && `legal-asset-${location.asset_id}`, location.page != null && `legal-page-${location.page}`].filter((id): id is string => Boolean(id));
}

export const contractHasText = (contract: Contract) => contract.reviewable !== false && contract.blocks.some(block => block.text.trim().length > 0);
