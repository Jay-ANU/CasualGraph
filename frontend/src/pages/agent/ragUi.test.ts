import { formatSourceChipLabel, formatSourceDocumentTitle, linkCitations } from './ragUi';

describe('RAG evidence labels', () => {
  it('prefers the real source filename when stale chunk metadata points at another report', () => {
    const source = {
      chunk_id: 'chunk_0',
      text: 'Apple ESG content',
      document_id: 'aa_sustainability_report_2022_20260505062611',
      document_title: 'aa-sustainability-report-2022',
      source: '63ce4de69503662010f3a660_Apple_Pollution Emissions.pdf',
    };

    expect(formatSourceDocumentTitle(source)).toBe('Apple Pollution Emissions');
    expect(formatSourceChipLabel(source)).toBe('apple pollution · chunk_0');
  });

  it('keeps the document title when it agrees with the source filename', () => {
    const source = {
      chunk_id: 'chunk_0',
      text: 'American Airlines sustainability content',
      document_id: 'aa_sustainability_report_2022_20260501043104',
      document_title: 'aa-sustainability-report-2022',
      source: 'aa-sustainability-report-2022.pdf',
    };

    expect(formatSourceDocumentTitle(source)).toBe('aa sustainability report 2022');
    expect(formatSourceChipLabel(source)).toBe('aa sustainability · chunk_0');
  });
});

describe('linkCitations', () => {
  const sources = [
    { chunk_id: 'chunk_0', text: 'a' },
    { chunk_id: 'chunk_1', text: 'b' },
  ];

  it('numbers known evidence markers in source order', () => {
    expect(linkCitations('Scope 2 fell [chunk_1]. Targets [chunk_0, chunk_1].', sources)).toBe(
      'Scope 2 fell [2](#cite-2). Targets [1](#cite-1)[2](#cite-2).',
    );
  });

  it('leaves unknown markers, links and code untouched', () => {
    const text = 'Graph [G_1], missing [chunk_9], link [chunk_0](https://example.test)\n```\n[chunk_0]\n```';
    expect(linkCitations(text, sources)).toBe(text);
  });

  it('does not rewrite markers inside inline code', () => {
    expect(linkCitations('Use `[chunk_0]` as the marker, see [chunk_0].', sources)).toBe(
      'Use `[chunk_0]` as the marker, see [1](#cite-1).',
    );
  });

  it('returns the input when there are no sources', () => {
    expect(linkCitations('See [chunk_0].', [])).toBe('See [chunk_0].');
  });
});
