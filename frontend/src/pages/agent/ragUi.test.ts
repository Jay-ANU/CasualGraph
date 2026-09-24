import { formatSourceChipLabel, formatSourceDocumentTitle, linkCitations } from './ragUi';

describe('RAG evidence labels', () => {
  it('prefers the real source filename when stale chunk metadata points at another document', () => {
    // "agreement" appears in both names but says nothing about which document this is.
    const source = {
      chunk_id: 'chunk_0',
      text: 'Lease terms',
      document_id: 'supply_agreement_2023_20260505062611',
      document_title: 'supply-agreement-2023',
      source: '63ce4de69503662010f3a660_Office Lease Agreement.pdf',
    };

    expect(formatSourceDocumentTitle(source)).toBe('Office Lease Agreement');
    expect(formatSourceChipLabel(source)).toBe('office lease · chunk_0');
  });

  it('keeps the document title when it agrees with the source filename', () => {
    const source = {
      chunk_id: 'chunk_0',
      text: 'Supply terms',
      document_id: 'supply_agreement_2023_20260501043104',
      document_title: 'supply-agreement-2023',
      source: 'supply-agreement-2023.pdf',
    };

    expect(formatSourceDocumentTitle(source)).toBe('supply agreement 2023');
    expect(formatSourceChipLabel(source)).toBe('supply agreement · chunk_0');
  });
});

describe('linkCitations', () => {
  const sources = [
    { chunk_id: 'chunk_0', text: 'a' },
    { chunk_id: 'chunk_1', text: 'b' },
  ];

  it('numbers known evidence markers in source order', () => {
    expect(linkCitations('Payment is due in 30 days [chunk_1]. Either party may terminate [chunk_0, chunk_1].', sources)).toBe(
      'Payment is due in 30 days [2](#cite-2). Either party may terminate [1](#cite-1)[2](#cite-2).',
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

  it('leaves ids that more than one document uses unlinked', () => {
    const shared = [
      { chunk_id: 'chunk_3', document_id: 'contract-a', text: 'a' },
      { chunk_id: 'chunk_3', document_id: 'contract-b', text: 'b' },
      { chunk_id: 'chunk_4', document_id: 'contract-b', text: 'c' },
    ];
    expect(linkCitations('Both [chunk_3], one [chunk_4].', shared)).toBe('Both [chunk_3], one [3](#cite-3).');
  });

  it('does not turn images, link definitions or tilde fences into citations', () => {
    const text = 'Chart ![chunk_0]\n[chunk_1]: https://example.test\n~~~\n[chunk_0]\n~~~';
    expect(linkCitations(text, sources)).toBe(text);
  });

  it('returns the input when there are no sources', () => {
    expect(linkCitations('See [chunk_0].', [])).toBe('See [chunk_0].');
  });
});
