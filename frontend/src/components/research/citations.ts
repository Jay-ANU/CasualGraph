import type { RagSource } from '../../types/api';

type Node = { type: string; value?: string; url?: string; children?: Node[] };

/** Transform only known source markers in markdown text, never links/code/math. */
export function remarkSourceLinks({ sources }: { sources: RagSource[] }) {
  const numbers = new Map<string, number>();
  const ambiguous = new Set<string>();
  sources.forEach((source, index) => {
    if (!source.chunk_id) return;
    if (numbers.has(source.chunk_id)) ambiguous.add(source.chunk_id);
    else numbers.set(source.chunk_id, index);
  });
  // Duplicate IDs cannot identify one passage reliably. Preserve the marker.
  ambiguous.forEach(id => numbers.delete(id));
  return (tree: Node) => {
    const visit = (parent: Node) => {
      if (!parent.children || ['link', 'image', 'code', 'inlineCode', 'math', 'inlineMath', 'html'].includes(parent.type)) return;
      parent.children = parent.children.flatMap(node => {
        if (node.type !== 'text' || !node.value) { visit(node); return [node]; }
        const text = node.value;
        const parts: Node[] = [];
        let cursor = 0;
        const pattern = /\[([^\]\r\n]+)\]/g;
        let match: RegExpExecArray | null;
        while ((match = pattern.exec(text))) {
          const number = numbers.get(match[1]);
          if (number === undefined) continue;
          if (match.index > cursor) parts.push({ type: 'text', value: text.slice(cursor, match.index) });
          parts.push({ type: 'link', url: `#cg-source-${number}`, children: [{ type: 'text', value: String(number + 1) }] });
          cursor = match.index + match[0].length;
        }
        if (!parts.length) return [node];
        if (cursor < text.length) parts.push({ type: 'text', value: text.slice(cursor) });
        return parts;
      });
    };
    visit(tree);
  };
}

/** Use an explicit page only; a chunk ID is not a reliable page number. */
export function sourceLocation(source: RagSource): string {
  const page = (source as RagSource & { page?: unknown }).page;
  return typeof page === 'number' && Number.isInteger(page) && page > 0
    ? `Page ${page}` : 'Report passage';
}
