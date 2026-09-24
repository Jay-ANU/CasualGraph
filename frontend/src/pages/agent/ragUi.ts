import type { RagReasoningMode, RagSource, RagStreamEvent } from '../../types/api';

export const readSseEvents = async (
  response: Response,
  onEvent: (event: RagStreamEvent) => void,
): Promise<void> => {
  if (!response.body) {
    throw new Error('Streaming response body is empty');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';

    for (const frame of frames) {
      const trimmed = frame.trim();
      if (!trimmed || trimmed.startsWith(':')) {
        continue;
      }
      const dataLine = trimmed
        .split('\n')
        .find((line) => line.startsWith('data:'));
      if (!dataLine) {
        continue;
      }
      const payload = dataLine.slice(5).trim();
      if (!payload) {
        continue;
      }
      onEvent(JSON.parse(payload) as RagStreamEvent);
    }

    if (done) {
      break;
    }
  }
};

const LOW_VALUE_TITLE_TOKENS = new Set([
  'report',
  'reports',
  'sustainability',
  'esg',
  'environmental',
  'social',
  'governance',
  'annual',
  'update',
  'full',
  'pdf',
]);

export const cleanSourceName = (value?: string): string => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const fileName = raw.split(/[\\/]/).pop() || raw;
  return fileName
    .replace(/\.[a-z0-9]{1,8}$/i, '')
    .replace(/^[0-9a-f]{16,}[\s_-]+/i, '')
    .replace(/[\s_-]+/g, ' ')
    .trim();
};

const meaningfulTitleTokens = (value: string): Set<string> => (
  new Set(
    (value.match(/[a-z0-9]+/gi) || [])
      .map(token => token.toLowerCase())
      .filter(token => token.length > 1 && !/^\d+$/.test(token) && !LOW_VALUE_TITLE_TOKENS.has(token))
  )
);

export const formatSourceDocumentTitle = (source: RagSource): string => {
  const title = cleanSourceName(source.document_title);
  const sourceName = cleanSourceName(source.source);
  const documentId = cleanSourceName(source.document_id);

  if (sourceName) {
    const titleTokens = meaningfulTitleTokens(title);
    const sourceTokens = meaningfulTitleTokens(sourceName);
    const hasOverlap = Array.from(titleTokens).some(token => sourceTokens.has(token));
    if (!title || (sourceTokens.size > 0 && titleTokens.size > 0 && !hasOverlap)) {
      return sourceName;
    }
  }
  return title || sourceName || documentId || 'Report evidence';
};

export const formatSourceChipLabel = (source: RagSource): string => {
  const shortDoc = formatSourceDocumentTitle(source)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .join(' ')
    .toLowerCase();
  const chunk = String(source.chunk_id || '').trim();
  return chunk ? `${shortDoc} · ${chunk}` : shortDoc;
};

export const getLoadingSteps = (tier: RagReasoningMode) => {
  if (tier === 'deep') {
    return [
      'Reading the question…',
      'Breaking the question down…',
      'Searching current, historical and regulatory sources…',
      'Reading the most relevant passages…',
      'Checking the graph…',
      'Working through the evidence…',
      'Adding citations…',
      'Finishing the answer…',
    ];
  }
  return [
    'Reading the question…',
    'Searching the reports…',
    'Reading the most relevant passages…',
    'Writing the answer…',
  ];
};

export const normalizeMathForMarkdown = (value: string): string => {
  if (!value) return value;

  let normalized = value;
  normalized = normalized.replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (_match, expr: string) => {
    const cleanExpr = expr.replace(/\\text\{\$([^}]+)\}/g, '\\text{$1}');
    return `\n$$\n${cleanExpr}\n$$\n`;
  });
  normalized = normalized.replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (_match, expr: string) => {
    const cleanExpr = expr.replace(/\\text\{\$([^}]+)\}/g, '\\text{$1}');
    return `$${cleanExpr}$`;
  });
  return normalized;
};

export const normalizeStreamingMarkdown = (value: string): string => {
  const normalized = normalizeMathForMarkdown(value);
  const fenceMatches = normalized.match(/(^|\n)```/g) || [];
  if (fenceMatches.length % 2 === 1) {
    return `${normalized}\n\`\`\``;
  }
  return normalized;
};

const CITATION_PATTERN = /\[([^[\]\n]{1,200})\](?!\()/g;
const CITATION_SEPARATOR = /\s*[,;，；]\s*/;
const CODE_FENCE = /((?:```|~~~)[\s\S]*?(?:```|~~~|$))/g;
const INLINE_CODE = /(`[^`\n]*`)/g;

/**
 * Turn inline evidence markers such as `[chunk_3]` or `[chunk_3, chunk_7]`
 * into numbered markdown links (`[1](#cite-1)`) that the answer renderer
 * shows as citation buttons. Only markers whose ids all match exactly one
 * cited source are rewritten. Chunk ids are numbered per report, so an id
 * shared by passages from two reports is ambiguous and stays as written, as
 * do graph markers, prose in brackets, images, link definitions and code.
 */
export const linkCitations = (markdown: string, sources: RagSource[]): string => {
  if (!markdown || !sources.length) return markdown;
  const occurrences = new Map<string, number>();
  sources.forEach((source) => {
    const id = String(source.chunk_id || '').trim();
    if (id) occurrences.set(id, (occurrences.get(id) || 0) + 1);
  });
  const numberById = new Map<string, number>();
  sources.forEach((source, index) => {
    const id = String(source.chunk_id || '').trim();
    if (id && occurrences.get(id) === 1) numberById.set(id, index + 1);
  });
  if (numberById.size === 0) return markdown;

  const linkSegment = (segment: string) =>
    segment.replace(CITATION_PATTERN, (match: string, inner: string, offset: number, whole: string) => {
      if (offset > 0 && whole[offset - 1] === '!') return match;
      const atLineStart = offset === 0 || whole[offset - 1] === '\n';
      if (atLineStart && whole[offset + match.length] === ':') return match;
      const ids = inner.split(CITATION_SEPARATOR).map((id) => id.trim()).filter(Boolean);
      if (!ids.length || !ids.every((id) => numberById.has(id))) return match;
      return ids.map((id) => `[${numberById.get(id)}](#cite-${numberById.get(id)})`).join('');
    });

  // Leave fenced code blocks and inline code spans exactly as written.
  return markdown
    .split(CODE_FENCE)
    .map((block) => (
      block.startsWith('```') || block.startsWith('~~~')
        ? block
        : block
          .split(INLINE_CODE)
          .map((part) => (part.startsWith('`') ? part : linkSegment(part)))
          .join('')
    ))
    .join('');
};
