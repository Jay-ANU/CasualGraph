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
      'Routing query...',
      'Decomposing question...',
      'Layered search across current / historical / regulatory...',
      'Reading top sources...',
      'Pulling graph context...',
      'Composing structured analysis...',
      'Citing evidence...',
      'Finalising answer...',
    ];
  }
  return [
    'Routing query...',
    'Searching reports...',
    'Reading top sources...',
    'Writing answer...',
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
