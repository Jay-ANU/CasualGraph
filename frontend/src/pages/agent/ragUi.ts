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

export const formatSourceChipLabel = (source: RagSource): string => {
  const rawDoc = String(source.document_title || source.document_id || 'source');
  const shortDoc = rawDoc
    .replace(/\.[a-z0-9]+$/i, '')
    .split(/[\s_-]+/)
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
