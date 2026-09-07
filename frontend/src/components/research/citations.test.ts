import { remarkSourceLinks, sourceLocation } from './citations';
import type { RagSource } from '../../types/api';
const sources: RagSource[] = [{ chunk_id: 'report-1-p12', text: 'Source one' }, { chunk_id: 'chunk_2', text: 'Source two' }];
const text = (value: string) => ({ type: 'text', value });
function transform(value: string) {
  const tree = { type: 'root', children: [{ type: 'paragraph', children: [text(value)] }] };
  remarkSourceLinks({ sources })(tree);
  return JSON.parse(JSON.stringify(tree)).children[0].children;
}
describe('Known source citations', () => {
  it('links a known marker without changing the answer', () => {
    expect(transform('Evidence [report-1-p12].')).toEqual([text('Evidence '), { type: 'link', url: '#cg-source-0', children: [text('1')] }, text('.')]);
  });
  it('does not silently attribute duplicate IDs to one of several sources', () => {
    const tree = { type: 'root', children: [text('Evidence [chunk_2].')] };
    const before = JSON.stringify(tree);
    remarkSourceLinks({ sources: [sources[1], { ...sources[1], text: 'Another passage' }] })(tree);
    expect(JSON.stringify(tree)).toBe(before);
  });
  it('leaves unsupported markers visibly untouched', () => { expect(transform('Missing [chunk_99].')).toEqual([text('Missing [chunk_99].')]); });
  it('uses source order, not appearance order, for numbers', () => { expect(transform('[chunk_2] then [report-1-p12]')[0].url).toBe('#cg-source-1'); });
  it('handles adjacent and repeated citations', () => { expect(transform('[chunk_2][chunk_2]').filter((n: {type: string}) => n.type === 'link')).toHaveLength(2); });
  it('does not rewrite code, math or existing links', () => {
    const nodes = ['code', 'inlineCode', 'math', 'inlineMath', 'link'].map(type => ({ type, value: '[chunk_2]', children: [text('[chunk_2]')] }));
    const tree = { type: 'root', children: nodes };
    const before = JSON.stringify(tree);
    remarkSourceLinks({ sources })(tree);
    expect(JSON.stringify(tree)).toBe(before);
  });
  it('does not derive page numbers from identifiers', () => { expect(sourceLocation(sources[0])).toBe('Report passage'); });
  it('shows only explicit valid page metadata', () => { expect(sourceLocation({ ...sources[0], page: 12 } as RagSource)).toBe('Page 12'); });
  it('rejects invalid page metadata without guessing', () => { expect(sourceLocation({ ...sources[0], page: -1 } as RagSource)).toBe('Report passage'); });
});
