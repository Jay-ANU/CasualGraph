import type { GraphData } from '../../types/graph';
import type { RagGraphSource, RagReasoningMode, RagSource, RagStreamEvent } from '../../types/api';

const QUERY_TOKEN_PATTERN = /[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}/g;
const QUERY_STOP_WORDS = new Set([
  'about', 'against', 'company', 'document', 'does', 'doing', 'esg', 'for', 'from', 'have',
]);

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

export const normalizeEvidenceText = (value?: string) =>
  String(value || '')
    .replace(/\s+/g, ' ')
    .replace(/\s*([,.;:!?])\s*/g, '$1 ')
    .replace(/\s+/g, ' ')
    .trim();

export const pickEvidenceSnippet = (text: string): string => {
  const cleaned = normalizeEvidenceText(text);
  if (!cleaned) return '';

  const chunks = cleaned
    .split(/(?<=[.!?])\s+/)
    .map(chunk => chunk.trim())
    .filter(Boolean);
  const bestChunk = chunks.find(chunk => chunk.length >= 70) || chunks[0] || cleaned;
  return bestChunk.length > 240 ? `${bestChunk.slice(0, 237)}...` : bestChunk;
};

export const getSourceRelevancePercent = (query: string, sourceText: string): number | null => {
  const queryTokens = extractQueryTokens(query)
    .map(token => token.trim().toLowerCase())
    .filter(token => token.length >= 3)
    .slice(0, 10);
  if (!queryTokens.length) return null;

  const haystack = sourceText.toLowerCase();
  const matched = queryTokens.filter(token => haystack.includes(token)).length;
  return Math.round((matched / queryTokens.length) * 100);
};

export const formatRelationLabel = (value?: string) =>
  String(value || 'related_to')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();

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

export const buildTracePreviewGraph = (graphSources?: RagGraphSource | null): GraphData | null => {
  if (!graphSources) return null;

  const edges = (graphSources.edges || [])
    .filter((edge) => edge?.source && edge?.target)
    .slice(0, 18)
    .map((edge) => ({
      source: String(edge.source),
      target: String(edge.target),
      relationship_type: String(edge.relationship_type || edge.relation_type || 'RELATED_TO'),
      confidence: typeof edge.confidence === 'number' ? edge.confidence : 0.65,
      evidence: String(edge.evidence || ''),
      domain: 'general',
    }));

  const nodeSet = new Set<string>();
  edges.forEach((edge) => {
    nodeSet.add(edge.source);
    nodeSet.add(edge.target);
  });

  (graphSources.matched_entities || []).forEach((entity) => {
    const label = String(entity?.label || entity?.name || entity?.id || '').trim();
    if (label) nodeSet.add(label);
  });

  const nodes = Array.from(nodeSet)
    .slice(0, 24)
    .map((id) => ({
      id,
      label: id,
      domain: 'general',
      type: /company/i.test(id) ? 'company' : 'entity',
      confidence: 0.75,
    }));

  if (!nodes.length || !edges.length) return null;

  return {
    nodes,
    edges: edges.filter((edge) => nodeSet.has(edge.source) && nodeSet.has(edge.target)),
    metadata: {
      node_count: nodes.length,
      edge_count: edges.length,
      is_directed: true,
      is_acyclic: false,
    },
  };
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

const extractQueryTokens = (value: string): string[] => {
  const matches = value.match(QUERY_TOKEN_PATTERN) || [];
  return matches
    .map((token) => token.trim().toLowerCase())
    .filter(token => token.length >= 2 && !QUERY_STOP_WORDS.has(token));
};
