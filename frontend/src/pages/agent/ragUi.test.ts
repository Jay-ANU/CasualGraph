import { formatSourceChipLabel, formatSourceDocumentTitle } from './ragUi';

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
