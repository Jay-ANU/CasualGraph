import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { motion } from 'framer-motion';
import { Search, Download, Trash2, MessageSquare, Database, Loader2, Zap, BrainCircuit, Network, FolderOpen, FileUp, FileText, Plus, Paperclip, CheckCircle2, AlertCircle, Circle, ArrowUp, ChevronLeft, ChevronRight, ThumbsUp, ThumbsDown } from 'lucide-react';
import { GraphVisualizer } from '../components';
import { useAuth } from '../contexts/AuthContext';
import type { GraphData, GraphEdge, GraphHighlightPath, GraphNode } from '../types/graph';
import type { AgentTraceStep, FeedbackPayload, FeedbackRating, FeedbackReasonTag, RagReasoningMode, RagResponse } from '../types/api';
import EvidencePanel from './agent/EvidencePanel';
import {
  STORAGE_KEYS,
  buildChatMessage,
  deriveSessionTitle,
  formatRelativeTime,
  toSessionSummary,
  type ChatMessage,
  type ChatSession,
} from './agent/chatSession';
import {
  buildTracePreviewGraph,
  formatSourceChipLabel,
  getLoadingSteps,
  getSourceRelevancePercent,
  normalizeEvidenceText,
  normalizeMathForMarkdown,
  normalizeStreamingMarkdown,
  pickEvidenceSnippet,
  readSseEvents,
} from './agent/ragUi';

interface CausalRelationship {
  cause: string;
  effect: string;
  confidence: number;
  evidence: string;
  domain: string;
  relationship_type: string;
}
interface Document {
  id: string;
  title: string;
  domain: string;
  source: string;
  document_group?: string;
  source_type?: string;
  graph?: GraphData;
  relationships?: CausalRelationship[];
  relationship_count?: number;
  chunk_count?: number;
  ingested_at?: string;
  processed_text_path?: string;
  chunks_path?: string;
  extractions_path?: string;
  graph_path?: string;
  vector_store_path?: string;
  neo4j_sync?: {
    enabled?: boolean;
    synced?: boolean;
    database?: string;
    chunks_synced?: number;
    entities_synced?: number;
    relations_synced?: number;
    reason?: string;
  };
}
interface Neo4jStatus {
  enabled?: boolean;
  connected?: boolean;
  database?: string;
  auto_sync?: boolean;
  reason?: string;
  message?: string;
  stats?: {
    counts?: {
      document_count?: number;
      chunk_count?: number;
      entity_count?: number;
      relation_count?: number;
      mention_count?: number;
    };
  };
}

interface UploadSubmission {
  title: string;
  content?: string;
  file?: File | null;
  domain?: string;
  sourceType?: string;
  source?: string;
  openDocumentsOnComplete?: boolean;
}
const GRAPH_DOMAIN_LABELS: Record<string, string> = {
  environmental: 'Environmental',
  social: 'Social',
  governance: 'Governance',
  general: 'General',
  ai: 'AI',
};

const QUERY_TOKEN_PATTERN = /[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}/g;
const QUERY_STOP_WORDS = new Set([
  'about', 'against', 'company', 'document', 'does', 'doing', 'esg', 'for', 'from', 'have',
]);

const CONTEXTUAL_QUERY_PATTERN =
  /^(it|its|they|them|their|this|that|these|those|what about|how about|and|also|then|why|how|when|where)\b/i;

const REPORT_REFERENCE_PATTERN =
  /\b(this report|the report|this document|the document|this company|the company)\b|这份报告|这个报告|该报告|这个文件/iu;

const CHAT_AUTO_SCROLL_THRESHOLD_PX = 120;
const STREAM_RENDER_INTERVAL_MS = 80;
const MIN_EVIDENCE_RELEVANCE_PERCENT = 35;

const normalizeQueryToken = (value: string) => value.trim().toLowerCase();
const normalizeGraphDomain = (value?: string) => {
  const normalized = String(value || 'general').trim().toLowerCase();
  if (normalized.includes('environment')) return 'environmental';
  if (normalized.includes('social')) return 'social';
  if (normalized.includes('govern')) return 'governance';
  if (normalized === 'ai' || normalized.includes('artificial')) return 'ai';
  return 'general';
};

const humanizeGraphToken = (value?: string) =>
  String(value || '')
    .replace(/^[A-Z]+:/, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const isUsableGraphLabel = (value?: string) => {
  const trimmed = String(value || '').trim();
  if (!trimmed) return false;
  if (/^E\d+$/i.test(trimmed)) return false;
  if (/^[A-Z_]+:[a-z0-9_]+$/i.test(trimmed)) return false;
  return true;
};

const isAnonymousGraphToken = (value?: string) => {
  const trimmed = String(value || '').trim();
  if (!trimmed) return true;
  if (/^E\d+$/i.test(trimmed)) return true;
  if (/^Entity$/i.test(trimmed)) return true;
  return false;
};

const getGraphNodeLabel = (node: Record<string, any>) => {
  const metadata = node?.metadata && typeof node.metadata === 'object' ? node.metadata : {};
  const candidates = [
    node?.name,
    metadata?.display_name,
    metadata?.label,
    metadata?.name,
    humanizeGraphToken(node?.normalized_name),
    humanizeGraphToken(node?.id),
  ];
  const preferred = candidates.find(candidate => isUsableGraphLabel(candidate));
  return String(preferred || 'Entity');
};

const GRAPH_ENTITY_STOP_WORDS = new Set([
  'annual', 'corporate', 'esg', 'fiscal', 'report', 'responsibility', 'sustainability', 'year',
]);

const extractQueryTokens = (value: string): string[] => {
  const matches = value.match(QUERY_TOKEN_PATTERN) || [];
  return matches
    .map(normalizeQueryToken)
    .filter(token => token.length >= 2 && !QUERY_STOP_WORDS.has(token));
};

const getDocumentCompanyTerms = (doc: Document): Set<string> => {
  const terms = new Set<string>();

  const pushTerms = (value: string | undefined) => {
    extractQueryTokens(value || '').forEach(token => terms.add(token));
  };

  pushTerms(doc.title);
  doc.graph?.nodes.forEach((node: GraphNode) => {
    if (node.type.toLowerCase().includes('company')) {
      pushTerms(node.label);
    }
  });
  doc.relationships?.forEach(rel => {
    pushTerms(rel.cause);
    pushTerms(rel.effect);
  });
  return terms;
};

const shouldPreferSelectedDocument = (query: string, selectedDocument: Document | null, documents: Document[]) => {
  if (!selectedDocument) return false;

  const trimmed = query.trim();
  if (!trimmed) return false;
  if (CONTEXTUAL_QUERY_PATTERN.test(trimmed) || trimmed.endsWith('呢') || REPORT_REFERENCE_PATTERN.test(trimmed)) {
    return true;
  }

  const queryTerms = extractQueryTokens(trimmed);
  if (queryTerms.length === 0) {
    return true;
  }

  const selectedTerms = getDocumentCompanyTerms(selectedDocument);
  const otherTerms = new Set<string>();
  documents.forEach(doc => {
    if (doc.id === selectedDocument.id) return;
    getDocumentCompanyTerms(doc).forEach(term => otherTerms.add(term));
  });

  const mentionsOther = queryTerms.some(term => otherTerms.has(term) && !selectedTerms.has(term));

  if (mentionsOther) {
    return false;
  }
  return true;
};

const deriveNeo4jAnchorEntity = (document: Document | null): string | null => {
  if (!document) return null;

  const companyNodes = (document.graph?.nodes || [])
    .filter((node: GraphNode) => node.type.toLowerCase().includes('company') && isUsableGraphLabel(node.label))
    .sort((a: GraphNode, b: GraphNode) => b.confidence - a.confidence);
  if (companyNodes.length > 0) {
    return companyNodes[0].label;
  }

  const relationshipEntity = (document.relationships || []).find(
    rel => /^[A-Z][A-Za-z0-9& ._-]{1,}$/.test(rel.cause) && !isAnonymousGraphToken(rel.cause)
  );
  if (relationshipEntity) {
    return relationshipEntity.cause;
  }

  const titleTerms = extractQueryTokens(document.title).filter(term => !GRAPH_ENTITY_STOP_WORDS.has(term));
  return titleTerms[0] || null;
};

const mapNeo4jSubgraphToGraphData = (payload: any): GraphData | null => {
  const rawNodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const rawEdges = Array.isArray(payload?.edges) ? payload.edges : [];
  if (rawNodes.length === 0) return null;

  const nodes = rawNodes
    .map((node: any) => {
      const metadata = node?.metadata && typeof node.metadata === 'object' ? node.metadata : {};
      return {
        id: String(node.id || node.name || node.normalized_name || ''),
        label: getGraphNodeLabel(node),
        domain: normalizeGraphDomain(node.esg_domain || node.domain || metadata.esg_domain || metadata.domain),
        type: String(node.type || node.entity_type || metadata.raw_type || 'Entity'),
        confidence: Number(node.confidence || 0.85),
        description: String(node.description || metadata.description || ''),
        company: metadata.company ? String(metadata.company) : undefined,
        year: metadata.year ? String(metadata.year) : undefined,
        normalizedName: node.normalized_name ? String(node.normalized_name) : undefined,
        metadata,
      };
    })
    .filter((node: GraphData['nodes'][number]) => node.id);

  const nodeIds = new Set(nodes.map((node: GraphNode) => node.id));
  const nodeMap = new Map<string, GraphNode>(nodes.map((node: GraphNode) => [node.id, node]));
  const edges = rawEdges
    .map((edge: any) => {
      const source = String(edge.source || '');
      const target = String(edge.target || '');
      const sourceDomain = nodeMap.get(source)?.domain;
      const targetDomain = nodeMap.get(target)?.domain;
      return {
        source,
        target,
        relationship_type: String(edge.relation_type || edge.relationship_type || 'RELATED_TO'),
        confidence: Number(edge.confidence || 0.75),
        evidence: String(edge.evidence || ''),
        domain: sourceDomain === targetDomain ? sourceDomain || 'general' : 'general',
        documentId: edge.document_id ? String(edge.document_id) : undefined,
        chunkId: edge.chunk_id ? String(edge.chunk_id) : undefined,
      };
    })
    .filter((edge: GraphEdge) => edge.source && edge.target && nodeIds.has(edge.source) && nodeIds.has(edge.target));

  return {
    nodes,
    edges,
    metadata: {
      node_count: nodes.length,
      edge_count: edges.length,
      is_directed: true,
      is_acyclic: false,
    },
  };
};

const getGraphEdgeId = (edge: GraphData['edges'][number]) => `${edge.source}|${edge.relationship_type}|${edge.target}`;

const getGraphDegreeMap = (graph: GraphData) => {
  const degreeMap = new Map<string, number>();
  graph.nodes.forEach((node: GraphNode) => degreeMap.set(node.id, 0));
  graph.edges.forEach((edge: GraphEdge) => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
  });
  return degreeMap;
};

const getGraphFocusNodeId = (graph: GraphData | null) => {
  if (!graph || graph.nodes.length === 0) return null;
  const degreeMap = getGraphDegreeMap(graph);
  const companyNode = graph.nodes
    .filter((node: GraphNode) => node.type.toLowerCase().includes('company'))
    .sort((a: GraphNode, b: GraphNode) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0))[0];
  if (companyNode) return companyNode.id;

  return [...graph.nodes].sort((a: GraphNode, b: GraphNode) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0))[0]?.id || null;
};

const formatGraphLabel = (value: string) => value.replace(/_/g, ' ');

const getDomainBreakdown = (graph: GraphData | null) => {
  if (!graph) return [];
  const counts = new Map<string, number>();
  graph.nodes.forEach((node: GraphNode) => {
    const domain = normalizeGraphDomain(node.domain);
    counts.set(domain, (counts.get(domain) || 0) + 1);
  });
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
};

const getTopConnectedNodes = (graph: GraphData | null, limit = 5) => {
  if (!graph) return [];
  const degreeMap = getGraphDegreeMap(graph);
  return [...graph.nodes]
    .sort((a: GraphNode, b: GraphNode) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0))
    .slice(0, limit)
    .map((node: GraphNode) => ({ ...node, degree: degreeMap.get(node.id) || 0 }));
};

const sanitizeGraphData = (graph: GraphData | null): GraphData | null => {
  if (!graph) return null;

  const nodeMap = new Map<string, GraphNode>();
  graph.nodes.forEach((node: GraphNode) => {
    const existing = nodeMap.get(node.id);
    if (!existing) {
      nodeMap.set(node.id, node);
      return;
    }

    nodeMap.set(node.id, {
      ...existing,
      confidence: Math.max(existing.confidence, node.confidence),
      description: existing.description || node.description,
      company: existing.company || node.company,
      year: existing.year || node.year,
      metadata: { ...(node.metadata || {}), ...(existing.metadata || {}) },
    });
  });

  const nodes = Array.from(nodeMap.values());
  const validNodeIds = new Set(nodes.map((node: GraphNode) => node.id));
  const edgeMap = new Map<string, GraphEdge>();

  graph.edges.forEach((edge: GraphEdge) => {
    if (!validNodeIds.has(edge.source) || !validNodeIds.has(edge.target)) return;
    const edgeId = getGraphEdgeId(edge);
    const existing = edgeMap.get(edgeId);
    if (!existing) {
      edgeMap.set(edgeId, edge);
      return;
    }

    edgeMap.set(edgeId, {
      ...existing,
      confidence: Math.max(existing.confidence, edge.confidence),
      evidence: existing.evidence || edge.evidence,
      metadata: { ...(edge.metadata || {}), ...(existing.metadata || {}) },
    });
  });

  const edges = Array.from(edgeMap.values());
  return {
    nodes,
    edges,
    metadata: {
      node_count: nodes.length,
      edge_count: edges.length,
      is_directed: graph.metadata?.is_directed ?? true,
      is_acyclic: graph.metadata?.is_acyclic ?? false,
    },
  };
};

const documentNeedsGraphRepair = (document: Document | null) => {
  if (!document?.id || !document.graph) return false;

  const hasAnonymousNode = (document.graph.nodes || []).some(
    (node: GraphNode) => isAnonymousGraphToken(node.label) || isAnonymousGraphToken(node.id)
  );
  const hasAnonymousRelationship = (document.relationships || []).some(
    rel => isAnonymousGraphToken(rel.cause) || isAnonymousGraphToken(rel.effect)
  );
  return hasAnonymousNode || hasAnonymousRelationship;
};

const getSampleDocuments = (): Document[] => [
  {
    id: 'sample_esg_report',
    title: 'NVIDIA FY2025 Sustainability Report',
    domain: 'general',
    source: 'Sample ESG Index',
    graph: {
      nodes: [
        { id: 'nvidia', label: 'NVIDIA', domain: 'general', type: 'Company', confidence: 0.98 },
        { id: 'scope_2_market_based_emissions', label: 'scope 2 market-based emissions', domain: 'environmental', type: 'ESG Metric', confidence: 0.84 },
        { id: 'renewable_electricity', label: 'renewable electricity', domain: 'environmental', type: 'ESG Metric', confidence: 0.84 },
        { id: 'climate_risk_oversight', label: 'climate risk oversight', domain: 'governance', type: 'Policy', confidence: 0.8 }
      ],
      edges: [
        { source: 'nvidia', target: 'scope_2_market_based_emissions', relationship_type: 'HAS_METRIC', confidence: 0.82, evidence: 'NVIDIA reported a 14% reduction in scope 2 market-based emissions.', domain: 'environmental' },
        { source: 'nvidia', target: 'renewable_electricity', relationship_type: 'HAS_TARGET', confidence: 0.82, evidence: 'The company set a target to reach 100% renewable electricity for selected sites.', domain: 'environmental' },
        { source: 'climate_risk_oversight', target: 'nvidia', relationship_type: 'IMPACTS', confidence: 0.68, evidence: 'The board governance policy requires quarterly oversight of climate risk and AI safety topics.', domain: 'governance' }
      ],
      metadata: { node_count: 4, edge_count: 3, is_directed: true, is_acyclic: true }
    },
    relationships: [
      { cause: 'NVIDIA', effect: 'scope 2 market-based emissions', confidence: 0.82, evidence: 'NVIDIA reported a 14% reduction in scope 2 market-based emissions.', domain: 'general', relationship_type: 'HAS_METRIC' },
      { cause: 'NVIDIA', effect: 'renewable electricity', confidence: 0.82, evidence: 'The company set a target to reach 100% renewable electricity for selected sites.', domain: 'general', relationship_type: 'HAS_TARGET' },
      { cause: 'climate risk oversight', effect: 'NVIDIA', confidence: 0.68, evidence: 'The board governance policy requires quarterly oversight of climate risk and AI safety topics.', domain: 'general', relationship_type: 'IMPACTS' }
    ]
  }
];

const SAMPLE_DOCUMENTS = getSampleDocuments();

const readApiErrorMessage = async (response: Response): Promise<string> => {
  const fallback = `RAG service returned ${response.status}${response.statusText ? ` ${response.statusText}` : ''}.`;
  let raw = '';
  try {
    raw = await response.text();
  } catch {
    return fallback;
  }

  if (!raw.trim()) {
    return fallback;
  }

  try {
    const payload = JSON.parse(raw) as { message?: string; error?: string; detail?: string | { message?: string; error?: string } };
    if (payload?.error === 'no_accessible_documents') {
      return 'No searchable ESG documents are available for this account yet. Upload a report or try again after the global knowledge base is indexed.';
    }
    if (typeof payload?.detail === 'string') {
      return payload.detail;
    }
    if (payload?.detail && typeof payload.detail === 'object') {
      return payload.detail.message || payload.detail.error || fallback;
    }
    return payload?.message || payload?.error || fallback;
  } catch {
    if (raw.trim().startsWith('<!DOCTYPE') || raw.trim().startsWith('<html')) {
      return `${fallback} The response was HTML, so check that REACT_APP_ESG_API_BASE points to the backend API rather than the frontend route.`;
    }
    return raw.slice(0, 240);
  }
};

const isChatMemoryUnavailablePayload = (payload: any) => {
  const error = String(payload?.error || '').toLowerCase();
  const message = String(payload?.message || payload?.detail || payload?.warning || '').toLowerCase();
  return error === 'chat_memory_unavailable' || message.includes('chat memory is unavailable');
};

const isChatMemoryUnavailableError = (error: unknown) => {
  const message = error instanceof Error ? error.message : String(error || '');
  return message.toLowerCase().includes('chat_memory_unavailable') || message.toLowerCase().includes('chat memory is unavailable');
};

const FEEDBACK_REASON_OPTIONS: Array<{ tag: FeedbackReasonTag; label: string }> = [
  { tag: 'missing_evidence', label: 'Missing evidence' },
  { tag: 'wrong_citation', label: 'Wrong citation' },
  { tag: 'hallucination', label: 'Hallucination' },
  { tag: 'irrelevant', label: 'Irrelevant' },
  { tag: 'other', label: 'Other' },
];

interface FeedbackDraft {
  rating?: FeedbackRating;
  tags: FeedbackReasonTag[];
  reasonText: string;
  submitting?: boolean;
  error?: string;
}

const createMessageId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2)}`;
};

const findPreviousUserPrompt = (messages: ChatMessage[], index: number) => {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages[i]?.type === 'user' && messages[i].content.trim()) {
      return messages[i].content.trim();
    }
  }
  return '';
};

const formatAgentStage = (step: AgentTraceStep) => {
  if (step.tool === 'search_documents') return 'Searching reports';
  if (step.tool === 'get_graph_context') return 'Reading graph';
  if (step.tool === 'summarize_evidence') return 'Summarizing evidence';
  if (step.stage === 'completed') return 'Finalizing answer';
  if (step.stage === 'partial') return 'Partial answer';
  return step.stage
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
};

const normalizeAgentTraceSteps = (steps: unknown): AgentTraceStep[] => {
  if (!Array.isArray(steps)) return [];
  return steps
    .map((step, index) => {
      const raw = step && typeof step === 'object' ? step as Record<string, unknown> : {};
      const stepNumber = Number(raw.step || index + 1);
      return {
        step: Number.isFinite(stepNumber) ? stepNumber : index + 1,
        stage: String(raw.stage || 'agent'),
        tool: typeof raw.tool === 'string' ? raw.tool : null,
        status: String(raw.status || 'running'),
        summary: String(raw.summary || ''),
        elapsed_ms: typeof raw.elapsed_ms === 'number' ? raw.elapsed_ms : undefined,
        meta: raw.meta && typeof raw.meta === 'object' ? raw.meta as Record<string, unknown> : undefined,
      };
    });
};

const Agent: React.FC = () => {
  const { isAuthenticated, token, user } = useAuth();
  const isAdmin = (user?.role || '').toLowerCase() === 'admin';
  const apiHost = typeof window !== 'undefined' ? window.location.hostname || '127.0.0.1' : '127.0.0.1';
  const localApiHost = apiHost === 'localhost' || apiHost === '127.0.0.1';
  const esgApiBase = process.env.REACT_APP_ESG_API_BASE || (localApiHost ? `http://${apiHost}:8000` : '');
  const [conversation, setConversation] = useState<ChatMessage[]>([]);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [isChatSessionsLoading, setIsChatSessionsLoading] = useState(false);
  const [hasLoadedChatSessions, setHasLoadedChatSessions] = useState(false);
  const [chatSessionsError, setChatSessionsError] = useState('');
  const [pendingSessionDocumentId, setPendingSessionDocumentId] = useState<string>('');
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPipelineStatus, setShowPipelineStatus] = useState(false);
  const [loadingStepIndex, setLoadingStepIndex] = useState(0);
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const [activeAgentPath, setActiveAgentPath] = useState<'rag' | 'agent' | null>(null);
  const [agentTrace, setAgentTrace] = useState<AgentTraceStep[]>([]);
  // Tier selector: 'flash' (OpenAI gpt-5.4-mini, fast) vs 'deep' (Anthropic
  // Claude, layered retrieval + graph context). URL accepts ?tier=deep; legacy
  // ?mode=predict is honored as Deep so old bookmarks still work.
  const [tier, setTier] = useState<RagReasoningMode>(() => {
    if (typeof window === 'undefined') return 'flash';
    const params = new URLSearchParams(window.location.search);
    if (params.get('tier') === 'deep') return 'deep';
    if (params.get('mode') === 'predict') return 'deep';
    return 'flash';
  });
  const [feedbackDrafts, setFeedbackDrafts] = useState<Record<string, FeedbackDraft>>({});
  const [submittedFeedback, setSubmittedFeedback] = useState<Record<string, FeedbackRating>>({});
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [queryScopeMode, setQueryScopeMode] = useState<'selected' | 'all'>('all');
  const [queryDocumentIds, setQueryDocumentIds] = useState<string[]>([]);
  const [isDocumentsLoading, setIsDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState('');
  const [loadingDocumentId, setLoadingDocumentId] = useState<string | null>(null);
  const [uploadForm, setUploadForm] = useState({
    title: '',
    content: '',
    domain: 'general',
    source_type: '',
    source: ''
  });
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [isProcessingFile, setIsProcessingFile] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [uploadInputMode, setUploadInputMode] = useState<'file' | 'text'>('file');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState('');
  const [uploadMessage, setUploadMessage] = useState('');
  const [uploadStatusTitle, setUploadStatusTitle] = useState('');
  const quickUploadInputRef = useRef<HTMLInputElement>(null);
  // uploadStatusResult is no longer rendered (legacy 2xl right aside removed),
  // but the setter is still called by the upload flow for future use. Read access
  // intentionally absent until a new surface needs it.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [uploadStatusResult, setUploadStatusResult] = useState<'success' | 'duplicate' | 'error' | null>(null);
  const [activeTab, setActiveTab] = useState('chat');
  const [isEvidencePanelOpen, setIsEvidencePanelOpen] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.evidencePanelOpen);
      return saved === null ? false : saved === '1';
    } catch {
      return false;
    }
  });
  const [neo4jStatus, setNeo4jStatus] = useState<Neo4jStatus | null>(null);
  const [neo4jGraph, setNeo4jGraph] = useState<GraphData | null>(null);
  const [neo4jGraphState, setNeo4jGraphState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [selectedGraphEdgeId, setSelectedGraphEdgeId] = useState<string | null>(null);
  const [highlightPath, setHighlightPath] = useState<GraphHighlightPath | null>(null);
  const [isDocumentGraphOpen, setIsDocumentGraphOpen] = useState(false);
  const [repairingDocumentId, setRepairingDocumentId] = useState<string | null>(null);
  const attemptedGraphRepairRef = useRef<Set<string>>(new Set());
  const uploadStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conversationScrollRef = useRef<HTMLDivElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const shouldAutoFollowConversationRef = useRef(true);
  const updateAutoFollowConversation = useCallback(() => {
    const node = conversationScrollRef.current;
    if (!node) return;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    shouldAutoFollowConversationRef.current = distanceFromBottom <= CHAT_AUTO_SCROLL_THRESHOLD_PX;
  }, []);
  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    const node = conversationScrollRef.current;
    if (node) {
      node.scrollTo({ top: node.scrollHeight, behavior });
      shouldAutoFollowConversationRef.current = true;
      return;
    }
    conversationEndRef.current?.scrollIntoView({ behavior, block: 'end' });
  }, []);
  useEffect(() => {
    if (activeTab !== 'chat' || !shouldAutoFollowConversationRef.current) return;
    const frameId = window.requestAnimationFrame(() => scrollToBottom('auto'));
    return () => window.cancelAnimationFrame(frameId);
  }, [activeTab, conversation.length, scrollToBottom]);
  useEffect(() => {
    if (activeTab !== 'documents' || !isAdmin) return;
    const loadNeo4jStatus = async () => {
      try {
        const response = await fetch(`${esgApiBase}/graph/neo4j/status`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const payload = await response.json();
        setNeo4jStatus(payload);
      } catch (error) {
        setNeo4jStatus({
          enabled: true,
          connected: false,
          reason: 'request_failed',
          message: error instanceof Error ? error.message : 'Unable to load Neo4j status',
        });
      }
    };
    loadNeo4jStatus();
  }, [activeTab, esgApiBase, documents.length, isAdmin, token]);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('');
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'f') {
        e.preventDefault();
        if (searchInputRef.current && activeTab === 'documents') {
          searchInputRef.current.focus();
        }
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [activeTab]);

  const persistSelectedDocumentId = useCallback((documentId?: string) => {
    try {
      if (documentId) {
        localStorage.setItem(STORAGE_KEYS.selectedDocumentId, documentId);
      } else {
        localStorage.removeItem(STORAGE_KEYS.selectedDocumentId);
      }
    } catch (error) {
      console.error('Failed to persist selected document id:', error);
    }
  }, []);

  const persistCurrentSessionId = useCallback((sessionId?: string) => {
    try {
      if (sessionId) {
        localStorage.setItem(STORAGE_KEYS.currentSessionId, sessionId);
      } else {
        localStorage.removeItem(STORAGE_KEYS.currentSessionId);
      }
    } catch (error) {
      console.error('Failed to persist current session id:', error);
    }
  }, []);

  const clearCurrentChatSession = useCallback((sessionId?: string) => {
    if (sessionId) {
      setChatSessions(prev => prev.filter(session => session.id !== sessionId));
    }
    setCurrentSessionId('');
    persistCurrentSessionId('');
    setPendingSessionDocumentId('');
    setConversation([]);
  }, [persistCurrentSessionId]);

  const isMissingChatSessionError = useCallback((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error || '');
    return message.toLowerCase().includes('chat session not found');
  }, []);

  const upsertChatSession = useCallback((session: ChatSession) => {
    if (!session.id) return;
    setChatSessions(prev => {
      const next = prev.filter(item => item.id !== session.id);
      return [session, ...next];
    });
  }, []);

  const upsertDocument = useCallback((document: Document) => {
    setDocuments(prev => {
      const next = prev.filter(item => item.id !== document.id);
      return [document, ...next];
    });
  }, []);

  const fetchDocumentDetail = useCallback(async (documentId: string): Promise<Document> => {
    const response = await fetch(`${esgApiBase}/documents/${encodeURIComponent(documentId)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to load document detail');
    }
    return payload.document as Document;
  }, [esgApiBase, token]);

  const fetchChatSessions = useCallback(async () => {
    if (!isAuthenticated) {
      setChatSessions([]);
      setCurrentSessionId('');
      setConversation([]);
      setChatSessionsError('');
      setHasLoadedChatSessions(true);
      return;
    }

    setIsChatSessionsLoading(true);
    setChatSessionsError('');
    try {
      const response = await fetch(`${esgApiBase}/chat/sessions`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const payload = await response.json();
      if (!response.ok) {
        if (response.status === 503 && isChatMemoryUnavailablePayload(payload)) {
          setChatSessions([]);
          setCurrentSessionId('');
          persistCurrentSessionId('');
          setConversation([]);
          return;
        }
        throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to load chat sessions');
      }
      const sessions = Array.isArray(payload?.sessions) ? payload.sessions.map(toSessionSummary) : [];
      setChatSessions(sessions);
    } catch (error) {
      console.error('Failed to load chat sessions:', error);
      setChatSessionsError(error instanceof Error ? error.message : 'Unable to load chat sessions');
      setChatSessions([]);
    } finally {
      setIsChatSessionsLoading(false);
      setHasLoadedChatSessions(true);
    }
  }, [esgApiBase, isAuthenticated, persistCurrentSessionId, token]);

  const fetchSessionDetail = useCallback(async (sessionId: string) => {
    const response = await fetch(`${esgApiBase}/chat/sessions/${encodeURIComponent(sessionId)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to load chat session');
    }

    const session = toSessionSummary(payload?.session || {});
    const messages = Array.isArray(payload?.messages)
      ? payload.messages
          .map((message: any) =>
            buildChatMessage(
              String(message?.role || '').toLowerCase() === 'user' ? 'user' : 'agent',
              String(message?.content || ''),
              message?.data,
              message?.timestamp,
            )
          )
          .filter((message: ChatMessage) => message.content.trim())
      : [];

    return {
      session,
      messages,
    };
  }, [esgApiBase, token]);

  const createServerSession = useCallback(async (initial?: Partial<ChatSession>) => {
    const response = await fetch(`${esgApiBase}/chat/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        title: initial?.title || '',
        selected_document_id: initial?.selectedDocumentId || selectedDocument?.id || '',
        mode: initial?.mode || 'ask',
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to create chat session');
    }
    const session = toSessionSummary(payload?.session || {});
    upsertChatSession(session);
    return session;
  }, [esgApiBase, selectedDocument?.id, token, upsertChatSession]);

  const appendSessionMessage = useCallback(async (sessionId: string, message: ChatMessage) => {
    const response = await fetch(`${esgApiBase}/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        role: message.type === 'agent' ? 'assistant' : 'user',
        content: message.content,
        timestamp: message.timestamp.toISOString(),
        data: message.data || {},
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to persist chat message');
    }
    const session = toSessionSummary(payload?.session || {});
    upsertChatSession(session);
    return session;
  }, [esgApiBase, token, upsertChatSession]);

  const updateServerSession = useCallback(async (sessionId: string, update: { title?: string; selected_document_id?: string; mode?: string }) => {
    const response = await fetch(`${esgApiBase}/chat/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(update),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to update chat session');
    }
    const session = toSessionSummary(payload?.session || {});
    upsertChatSession(session);
    return session;
  }, [esgApiBase, token, upsertChatSession]);

  useEffect(() => {
    try {
      setCurrentSessionId(localStorage.getItem(STORAGE_KEYS.currentSessionId) || '');
    } catch (error) {
      console.error('Failed to restore current session id:', error);
      setCurrentSessionId('');
    }
    setConversation([]);
  }, []);

  useEffect(() => {
    void fetchChatSessions();
  }, [fetchChatSessions]);

  const selectDocument = useCallback(async (document: Document) => {
    setSelectedDocument(document);
    setQueryDocumentIds(prev => [document.id, ...prev.filter(id => id !== document.id)].slice(0, 3));
    setIsDocumentGraphOpen(false);
    persistSelectedDocumentId(document.id);

    if (currentSessionId) {
      try {
        await updateServerSession(currentSessionId, { selected_document_id: document.id });
      } catch (error) {
        if (isMissingChatSessionError(error)) {
          clearCurrentChatSession(currentSessionId);
          return;
        }
        console.error('Failed to sync selected document to chat session:', error);
      }
    }

    const alreadyDetailed = Boolean(document.relationships && document.graph && document.graph.nodes.length > 0);
    if (alreadyDetailed) {
      return;
    }

    setLoadingDocumentId(document.id);
    setDocumentsError('');
    try {
      const detailed = await fetchDocumentDetail(document.id);
      setDocuments(prev => prev.map(item => (item.id === detailed.id ? detailed : item)));
      setSelectedDocument(current => (current?.id === detailed.id ? detailed : current));
    } catch (error) {
      console.error('Failed to load document detail:', error);
      setDocumentsError(error instanceof Error ? error.message : 'Unable to load document detail');
    } finally {
      setLoadingDocumentId(current => (current === document.id ? null : current));
    }
  }, [clearCurrentChatSession, currentSessionId, fetchDocumentDetail, isMissingChatSessionError, persistSelectedDocumentId, updateServerSession]);

  useEffect(() => {
    const loadDocuments = async () => {
      if (!isAuthenticated) {
        setDocuments([]);
        setSelectedDocument(null);
        return;
      }

      setIsDocumentsLoading(true);
      setDocumentsError('');
      try {
        const response = await fetch(`${esgApiBase}/documents`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to load documents');
        }

        const remoteDocuments: Document[] = Array.isArray(payload?.documents) ? payload.documents : [];
        const nextDocuments = remoteDocuments.length > 0 ? remoteDocuments : SAMPLE_DOCUMENTS;
        setDocuments(nextDocuments);

        const savedSelectedDocumentId = localStorage.getItem(STORAGE_KEYS.selectedDocumentId) || '';
        const initialSelected =
          nextDocuments.find(doc => doc.id === savedSelectedDocumentId) ||
          nextDocuments[0] ||
          null;
        setSelectedDocument(initialSelected);

        if (initialSelected && remoteDocuments.some(doc => doc.id === initialSelected.id)) {
          if (currentSessionId || pendingSessionDocumentId) {
            void fetchDocumentDetail(initialSelected.id)
              .then((detailed) => {
                setDocuments(prev => prev.map(item => (item.id === detailed.id ? detailed : item)));
                setSelectedDocument(current => (current?.id === detailed.id ? detailed : current));
              })
              .catch((error) => {
                console.error('Failed to load initial document detail:', error);
              });
          } else {
            void selectDocument(initialSelected);
          }
        } else {
          persistSelectedDocumentId(initialSelected?.id);
        }
      } catch (error) {
        console.error('Failed to load documents from backend:', error);
        setDocumentsError(error instanceof Error ? error.message : 'Unable to load documents');
        setDocuments(SAMPLE_DOCUMENTS);
        setSelectedDocument(SAMPLE_DOCUMENTS[0] || null);
        persistSelectedDocumentId(SAMPLE_DOCUMENTS[0]?.id);
      } finally {
        setIsDocumentsLoading(false);
      }
    };

    void loadDocuments();
    // pendingSessionDocumentId is intentionally read inside but not in deps:
    // session-restore flow uses useEffect@918 to apply the pending id once
    // documents arrive, so document list reload should not be triggered by it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSessionId, esgApiBase, fetchDocumentDetail, isAuthenticated, persistSelectedDocumentId, selectDocument, token]);

  useEffect(() => {
    persistSelectedDocumentId(selectedDocument?.id);
  }, [persistSelectedDocumentId, selectedDocument]);

  useEffect(() => {
    if (!selectedDocument?.id) return;
    if (queryDocumentIds.length > 0) return;
    setQueryDocumentIds([selectedDocument.id]);
  }, [selectedDocument?.id, queryDocumentIds.length]);

  useEffect(() => {
    const validIds = new Set(documents.map(doc => doc.id));
    setQueryDocumentIds(prev => prev.filter(id => validIds.has(id)));
  }, [documents]);

  useEffect(() => {
    if (!isAuthenticated) {
      persistCurrentSessionId('');
      setPendingSessionDocumentId('');
      return;
    }
    persistCurrentSessionId(currentSessionId);
  }, [currentSessionId, isAuthenticated, persistCurrentSessionId]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.evidencePanelOpen, isEvidencePanelOpen ? '1' : '0');
    } catch (error) {
      console.error('Failed to persist evidence panel visibility:', error);
    }
  }, [isEvidencePanelOpen]);

  useEffect(() => {
    if (!isLoading) {
      setLoadingStepIndex(0);
      setLoadingElapsedMs(0);
    }
  }, [isLoading]);

  useEffect(() => {
    if (!isLoading) return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setLoadingElapsedMs(Date.now() - startedAt);
    }, 300);
    return () => window.clearInterval(timer);
  }, [isLoading]);

  useEffect(() => {
    if (!isAuthenticated || !currentSessionId) {
      if (!currentSessionId) {
        setConversation([]);
      }
      return;
    }

    let cancelled = false;
    const loadSession = async () => {
      setIsChatSessionsLoading(true);
      setChatSessionsError('');
      try {
        const payload = await fetchSessionDetail(currentSessionId);
        if (cancelled) return;
        upsertChatSession(payload.session);
        setConversation(payload.messages);
        setPendingSessionDocumentId(payload.session.selectedDocumentId || '');
        // Legacy sessions stored mode=predict; carry that forward as Deep tier.
        if (payload.session.mode === 'predict') setTier('deep');
      } catch (error) {
        if (cancelled) return;
        if (isChatMemoryUnavailableError(error)) {
          setCurrentSessionId('');
          persistCurrentSessionId('');
          setChatSessions([]);
          setChatSessionsError('');
          setConversation([]);
          return;
        }
        if (isMissingChatSessionError(error)) {
          clearCurrentChatSession(currentSessionId);
          return;
        }
        console.error('Failed to load current chat session:', error);
        setChatSessionsError(error instanceof Error ? error.message : 'Unable to load chat session');
        setConversation([]);
      } finally {
        if (!cancelled) {
          setIsChatSessionsLoading(false);
        }
      }
    };

    void loadSession();
    return () => {
      cancelled = true;
    };
  }, [clearCurrentChatSession, currentSessionId, fetchSessionDetail, isAuthenticated, isMissingChatSessionError, persistCurrentSessionId, upsertChatSession]);

  useEffect(() => {
    if (!hasLoadedChatSessions || !currentSessionId || isChatSessionsLoading) return;
    if (chatSessions.some(session => session.id === currentSessionId)) return;
    setCurrentSessionId('');
    persistCurrentSessionId('');
    setConversation([]);
  }, [chatSessions, currentSessionId, hasLoadedChatSessions, isChatSessionsLoading, persistCurrentSessionId]);

  // Tier (Flash/Deep) is a per-request choice; we no longer persist a session
  // 'mode' field that needed syncing to the backend on toggle.

  useEffect(() => {
    if (!pendingSessionDocumentId || documents.length === 0) return;
    const target = documents.find(doc => doc.id === pendingSessionDocumentId);
    if (!target) return;
    setPendingSessionDocumentId('');
    if (selectedDocument?.id !== target.id) {
      void selectDocument(target);
    }
  }, [documents, pendingSessionDocumentId, selectDocument, selectedDocument?.id]);
  useEffect(() => {
    if (activeTab !== 'documents' || !selectedDocument) {
      setNeo4jGraph(null);
      setNeo4jGraphState('idle');
      return;
    }

    const shouldLoadNeo4jGraph = Boolean(isAdmin && neo4jStatus?.connected && selectedDocument.neo4j_sync?.synced);
    const anchorEntity = deriveNeo4jAnchorEntity(selectedDocument);
    if (!shouldLoadNeo4jGraph || !anchorEntity) {
      setNeo4jGraph(null);
      setNeo4jGraphState('idle');
      return;
    }

    let cancelled = false;
    const loadNeo4jGraph = async () => {
      setNeo4jGraphState('loading');
      try {
        const response = await fetch(
          `${esgApiBase}/graph/neo4j/subgraph?entity=${encodeURIComponent(anchorEntity)}&hops=1&limit=36`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} }
        );
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload?.message || payload?.error || 'Neo4j subgraph request failed');
        }

        const graph = mapNeo4jSubgraphToGraphData(payload);
        if (cancelled) return;
        if (graph) {
          setNeo4jGraph(graph);
          setNeo4jGraphState('ready');
          return;
        }

        setNeo4jGraph(null);
        setNeo4jGraphState('error');
      } catch (error) {
        if (cancelled) return;
        console.error('Failed to load Neo4j graph:', error);
        setNeo4jGraph(null);
        setNeo4jGraphState('error');
      }
    };

    loadNeo4jGraph();
    return () => {
      cancelled = true;
    };
  }, [activeTab, esgApiBase, isAdmin, neo4jStatus?.connected, selectedDocument, token]);

  useEffect(() => {
    if (!isAdmin) return;
    if (activeTab !== 'documents' || !selectedDocument) return;
    if (!documentNeedsGraphRepair(selectedDocument)) return;
    if (repairingDocumentId === selectedDocument.id) return;
    if (attemptedGraphRepairRef.current.has(selectedDocument.id)) return;

    attemptedGraphRepairRef.current.add(selectedDocument.id);
    setRepairingDocumentId(selectedDocument.id);
    setNeo4jGraph(null);
    setNeo4jGraphState('idle');

    const repairGraph = async () => {
      try {
        const response = await fetch(`${esgApiBase}/documents/rebuild-graph`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(selectedDocument),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload?.message || payload?.error || 'Graph rebuild failed');
        }
        const repairedDocument = payload?.document as Document | undefined;
        if (!repairedDocument) {
          throw new Error('Graph rebuild returned no document payload');
        }

        setDocuments(prev => prev.map(doc => (doc.id === repairedDocument.id ? repairedDocument : doc)));
        setSelectedDocument(prev => (prev?.id === repairedDocument.id ? repairedDocument : prev));
      } catch (error) {
        console.error('Graph repair failed:', error);
      } finally {
        setRepairingDocumentId(current => (current === selectedDocument.id ? null : current));
      }
    };

    repairGraph();
  }, [activeTab, esgApiBase, isAdmin, repairingDocumentId, selectedDocument, token]);
  useEffect(() => {
    const activeGraph = neo4jGraph || selectedDocument?.graph || null;
    const focusNodeId = getGraphFocusNodeId(activeGraph);
    setSelectedGraphNodeId(focusNodeId);
    setSelectedGraphEdgeId(null);
    setHighlightPath(null);
  }, [neo4jGraph, selectedDocument]);

  useEffect(() => {
    return () => {
      if (uploadStatusTimerRef.current) {
        clearTimeout(uploadStatusTimerRef.current);
      }
    };
  }, []);

  const clearUploadStatusTimer = () => {
    if (uploadStatusTimerRef.current) {
      clearTimeout(uploadStatusTimerRef.current);
      uploadStatusTimerRef.current = null;
    }
  };

  const dismissUploadStatus = () => {
    clearUploadStatusTimer();
    setUploadStatusResult(null);
    setUploadStatusTitle('');
    setUploadProgress(0);
    setUploadStage('');
    setUploadMessage('');
  };

  const scheduleUploadStatusDismiss = () => {
    clearUploadStatusTimer();
    uploadStatusTimerRef.current = setTimeout(() => {
      dismissUploadStatus();
    }, 4000);
  };

  const handleUpload = async (submission?: UploadSubmission) => {
    const fileToUpload = submission?.file ?? uploadedFile;
    const contentToUpload = submission?.content ?? (fileContent || uploadForm.content);
    const titleToUpload = (submission?.title ?? uploadForm.title).trim();
    const domainToUpload = submission?.domain ?? uploadForm.domain;
    const sourceTypeToUpload = submission?.sourceType ?? uploadForm.source_type;
    const sourceToUpload = submission?.source ?? uploadForm.source;
    const openDocumentsOnComplete = submission?.openDocumentsOnComplete ?? true;

    if (!titleToUpload || (!contentToUpload && !fileToUpload)) {
      addAgentMessage("Please provide a document title and either uploaded file content or manual text.", "error");
      return;
    }
    if (!isAuthenticated) {
      addAgentMessage("Please log in to upload documents.", "error");
      return;
    }
    setIsUploading(true);
    clearUploadStatusTimer();
    setUploadStatusTitle(fileToUpload?.name || titleToUpload || 'Uploaded document');
    setUploadStatusResult(null);
    setUploadProgress(1);
    setUploadStage('queued');
    setUploadMessage('Queued for processing');
    addAgentMessage(`Analyzing document: "${titleToUpload}" and rebuilding the active RAG index...`, "processing");
    try {
      const formData = new FormData();
      formData.append('title', titleToUpload);
      formData.append('domain', domainToUpload);
      formData.append('source_type', sourceTypeToUpload);
      formData.append('source', sourceToUpload);
      if (fileToUpload) {
        formData.append('file', fileToUpload);
      } else {
        formData.append('content', contentToUpload);
      }

      const response = await fetch(`${esgApiBase}/documents/upload-async`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.message || payload?.detail || payload?.error || 'Upload failed');
      }
      const jobId = payload?.job_id;
      if (!jobId) {
        throw new Error('Upload job was created without a job id.');
      }

      let uploadedDocument: Document | null = null;
      let finalStats: any = null;
      let isDuplicate = false;
      let duplicateMatchedBy = '';
      let lastMessage = 'Queued for processing';

      while (!uploadedDocument) {
        await new Promise(resolve => setTimeout(resolve, 1200));
        const jobResponse = await fetch(`${esgApiBase}/documents/jobs/${jobId}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const jobPayload = await jobResponse.json();
        if (!jobResponse.ok) {
          throw new Error(jobPayload?.message || jobPayload?.detail || jobPayload?.error || 'Unable to fetch upload progress');
        }

        const progress = Number(jobPayload?.progress || 0);
        const stage = String(jobPayload?.stage || 'processing');
        const message = String(jobPayload?.message || 'Processing document');
        lastMessage = message;
        setUploadProgress(progress);
        setUploadStage(stage);
        setUploadMessage(message);

        if (jobPayload?.status === 'failed') {
          throw new Error(jobPayload?.error || message || 'Document processing failed');
        }

        if (jobPayload?.status === 'rejected') {
          throw new Error(jobPayload?.error || message || 'Upload request was rejected.');
        }

        if (jobPayload?.status === 'completed') {
          uploadedDocument = jobPayload?.result?.document || null;
          finalStats = jobPayload?.result?.stats || null;
          isDuplicate = Boolean(jobPayload?.result?.duplicate);
          duplicateMatchedBy = String(jobPayload?.result?.matched_by || '');
        }
      }

      if (!uploadedDocument) {
        throw new Error(lastMessage || 'Document processing did not return a result');
      }

      const completedDocument = uploadedDocument;
      upsertDocument(completedDocument);
      setUploadForm({ title: '', content: '', domain: 'general', source_type: '', source: '' });
      setFileContent('');
      setUploadedFile(null);
      setUploadProgress(100);
      setUploadStage('completed');
      setUploadMessage(isDuplicate ? 'Duplicate detected; reusing existing document' : 'Document processing complete');
      setUploadStatusResult(isDuplicate ? 'duplicate' : 'success');
      scheduleUploadStatusDismiss();
      const successMessage = isDuplicate
        ? `This document is already in your library — opened existing entry "${completedDocument.title}" (matched by ${duplicateMatchedBy || 'content hash'}).`
        : `Document "${completedDocument.title}" was processed successfully and added to the ESG knowledge corpus.`;
      addAgentMessage(successMessage, "success");
      const summaryHeader = isDuplicate ? 'Existing document reused:' : 'Key findings from the latest ingestion:';
      const summaryMessage = `${summaryHeader}
• Chunks: ${finalStats?.chunk_count || 0}
• Graph nodes: ${completedDocument.graph?.metadata?.node_count || 0}
• Relationships: ${completedDocument.relationships?.length || 0}
${isDuplicate
  ? 'No re-processing was needed — chat retrieval already covers this content.'
  : `Corpus update:
• This document is now searchable alongside the existing ESG/library documents
• Extraction results were saved for later graph exploration
• Chat retrieval now draws from the broader corpus unless a future filter is applied`}`;
      addAgentMessage(summaryMessage, "success");
      if (openDocumentsOnComplete) {
        setActiveTab('documents');
      }
      setSelectedDocument(completedDocument);
      persistSelectedDocumentId(completedDocument.id);
    } catch (error) {
        console.error('Upload error:', error);
        const message = error instanceof Error ? error.message : 'Unknown error';
        const rejected = /rejected/i.test(message);
        clearUploadStatusTimer();
        setUploadStatusResult('error');
        setUploadStage('failed');
        setUploadMessage(message);
        setUploadProgress(current => Math.max(current, 100));
        addAgentMessage(
          rejected
            ? `Upload request was rejected: ${message}`
            : `Document upload failed: ${message}. Please try again.`,
          "error"
        );
      } finally {
        setIsUploading(false);
      }
  };
  const pushConversationMessage = useCallback((message: ChatMessage) => {
    setConversation(prev => [...prev, message]);
  }, []);

  const addAgentMessage = useCallback((
    content: string,
    type: 'success' | 'error' | 'processing' | 'info' = 'info',
    data?: ChatMessage['data']
  ) => {
    void type;
    const message = buildChatMessage('agent', content, data);
    pushConversationMessage(message);
    return message;
  }, [pushConversationMessage]);

  const handleOpenFullGraph = useCallback(async () => {
    const params = new URLSearchParams();
    params.set('scope', selectedDocument?.id ? 'document' : 'all');
    if (selectedDocument?.id) {
      params.set('document_id', selectedDocument.id);
    }
    const graphWindow = window.open('about:blank', '_blank');
    if (!graphWindow) {
      addAgentMessage('The graph window was blocked by the browser. Please allow pop-ups and try again.', 'error');
      return;
    }
    graphWindow.opener = null;

    if (isAuthenticated && token) {
      try {
        const response = await fetch(`${esgApiBase}/kg-view/ticket`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ document_id: selectedDocument?.id || '' }),
        });
        const payload = await response.json().catch(() => ({} as { ticket?: string; detail?: string; message?: string }));
        if (!response.ok || !payload.ticket) {
          throw new Error(payload.detail || payload.message || 'Could not create graph access ticket');
        }
        params.set('ticket', payload.ticket);
      } catch (error) {
        console.error('Failed to create graph access ticket:', error);
        graphWindow.close();
        addAgentMessage('Could not open the authenticated graph view. Please refresh and try again.', 'error');
        return;
      }
    }

    graphWindow.location.href = `${esgApiBase}/kg-view?${params.toString()}`;
  }, [addAgentMessage, esgApiBase, isAuthenticated, selectedDocument?.id, token]);

  const addAgentMessageToSession = useCallback(async (
    sessionId: string,
    content: string,
    type: 'success' | 'error' | 'processing' | 'info' = 'info',
    data?: ChatMessage['data']
  ) => {
    const message = addAgentMessage(content, type, data);
    try {
      await appendSessionMessage(sessionId, message);
    } catch (error) {
      console.error('Failed to persist assistant message:', error);
    }
    return message;
  }, [addAgentMessage, appendSessionMessage]);
  const processUserQuery = async (
    query: string,
    historyMessages: ChatMessage[] = [],
    sessionId?: string,
    onStepChange?: (stepIndex: number) => void,
    onAnswerStart?: () => void,
  ) => {
    // User text is always sent to RAG. Navigation should only happen through
    // explicit UI controls, not keyword hijacks like "upload" or "graph".
    // Removed: a frontend "relationship-template" hijack that intercepted any query whose
    // lowercase form contained any rel.cause or rel.effect substring. With graph extractor
    // artifacts like "n" or "i", this matched almost every question and prevented /rag/ask
    // from ever being called. All causal-relationship explanation should come from the LLM
    // via the backend, not from a hardcoded frontend template.
    try {
      const documentIdsForQuery = queryScopeMode === 'all' ? [] : effectiveQueryDocumentIds;
      const preferredDocumentId = queryScopeMode === 'all'
        ? undefined
        : shouldPreferSelectedDocument(query, selectedDocument, documents)
          ? (documentIdsForQuery.length > 0
              ? (documentIdsForQuery.includes(selectedDocument?.id || '') ? selectedDocument?.id : documentIdsForQuery[0])
              : selectedDocument?.id)
          : undefined;
      onStepChange?.(0);
      const requestBody = {
        question: query,
        top_k: 3,
        session_id: sessionId,
        reasoning_mode: tier,
        document_ids: documentIdsForQuery,
        preferred_document_id: preferredDocumentId,
        history: historyMessages
          .filter(message => message.type === 'user' || message.type === 'agent')
          .slice(-6)
          .map(message => ({
            role: message.type === 'agent' ? 'assistant' : 'user',
            content: message.content
          }))
      };

      const response = await fetch(`${esgApiBase}/rag/ask/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response));
      }

      const placeholderTimestamp = new Date();
      const placeholderMessage = buildChatMessage('agent', '', {
        mode: 'ask',
        backend: 'streaming',
        sources: [],
        messageId: createMessageId(),
      }, placeholderTimestamp);
      pushConversationMessage(placeholderMessage);

      let latestMessageData: ChatMessage['data'] = placeholderMessage.data;
      let pendingStreamingContent = '';
      let streamingRenderTimer: number | null = null;
      let lastStreamingRenderAt = 0;
      const applyStreamingUpdate = () => {
        streamingRenderTimer = null;
        lastStreamingRenderAt = window.performance.now();
        const content = pendingStreamingContent;
        setConversation(prev => prev.map((message) => {
          if (
            message.type === 'agent' &&
            message.timestamp.getTime() === placeholderTimestamp.getTime()
          ) {
            return {
              ...message,
              content,
              data: latestMessageData,
            };
          }
          return message;
        }));
      };
      const flushStreamingUpdate = () => {
        if (streamingRenderTimer !== null) {
          window.clearTimeout(streamingRenderTimer);
          streamingRenderTimer = null;
        }
        applyStreamingUpdate();
      };
      const updateStreamingMessage = (
        content: string,
        nextData?: Partial<NonNullable<ChatMessage['data']>>,
        immediate = false,
      ) => {
        latestMessageData = {
          ...(latestMessageData || {}),
          ...(nextData || {}),
        };
        pendingStreamingContent = content;
        if (immediate) {
          flushStreamingUpdate();
          return;
        }
        if (streamingRenderTimer === null) {
          const elapsedMs = window.performance.now() - lastStreamingRenderAt;
          const delayMs = Math.max(0, STREAM_RENDER_INTERVAL_MS - elapsedMs);
          streamingRenderTimer = window.setTimeout(applyStreamingUpdate, delayMs);
        }
      };

      let streamedAnswer = '';
      let finalPayload: RagResponse | null = null;
      let sawFirstToken = false;
      try {
        await readSseEvents(response, (event) => {
          if (event.type === 'meta') {
            if (event.payload.stream_stage === 'routing') {
              onStepChange?.(0);
            } else if (event.payload.stream_stage === 'context_ready') {
              onStepChange?.(tier === 'deep' ? 5 : 3);
            } else if (event.payload.stream_stage === 'planning') {
              onStepChange?.(tier === 'deep' ? 2 : 1);
            } else if (event.payload.stream_stage === 'agent_trace') {
              onStepChange?.(tier === 'deep' ? 4 : 2);
            }
            const traceSteps = normalizeAgentTraceSteps(event.payload.agent_trace);
            if (event.payload.agent_path) {
              setActiveAgentPath(event.payload.agent_path);
            }
            if (traceSteps.length > 0) {
              setAgentTrace(prev => [...prev, ...traceSteps]);
            }
            const nextData: Partial<NonNullable<ChatMessage['data']>> = {
              mode: event.payload.mode || latestMessageData?.mode || 'ask',
            };
            if (event.payload.agent_path) {
              nextData.agentPath = event.payload.agent_path;
            }
            if (traceSteps.length > 0) {
              nextData.agentTrace = [...(latestMessageData?.agentTrace || []), ...traceSteps];
            }
            if (Array.isArray(event.payload.sources)) {
              nextData.sources = event.payload.sources;
            }
            if (event.payload.graph_sources) {
              nextData.graphSources = event.payload.graph_sources;
            }
            updateStreamingMessage(streamedAnswer, nextData, event.payload.stream_stage === 'routing');
            return;
          }
          if (event.type === 'token') {
            if (!sawFirstToken) {
              sawFirstToken = true;
              onAnswerStart?.();
            }
            streamedAnswer += event.text;
            updateStreamingMessage(streamedAnswer);
            return;
          }
          if (event.type === 'done') {
            onStepChange?.(tier === 'deep' ? 7 : 3);
            finalPayload = event.payload;
            const finalTrace = normalizeAgentTraceSteps(event.payload.agent_trace);
            const finalAgentPath = event.payload.agent_path || event.payload.path;
            if (finalAgentPath) {
              setActiveAgentPath(finalAgentPath);
            }
            if (finalTrace.length > 0) {
              setAgentTrace(finalTrace);
            }
            const finalAnswer = typeof event.payload.answer === 'string' && event.payload.answer.trim()
              ? event.payload.answer
              : streamedAnswer || 'The system could not find enough grounded information to answer that question.';
            updateStreamingMessage(finalAnswer, {
              mode: event.payload.mode || 'ask',
              backend: event.payload.backend,
              agentPath: finalAgentPath,
              agentTrace: finalTrace.length > 0 ? finalTrace : latestMessageData?.agentTrace,
              partial: Boolean(event.payload.partial),
              partialReason: event.payload.partial_reason || null,
              sources: Array.isArray(event.payload.sources) ? event.payload.sources : [],
              graphSources: event.payload.graph_sources,
              timingsMs: event.payload.timings_ms,
            }, true);
            streamedAnswer = finalAnswer;
            return;
          }
          if (event.type === 'error') {
            throw new Error(event.message || 'RAG stream failed');
          }
        });
      } finally {
        if (streamingRenderTimer !== null) {
          window.clearTimeout(streamingRenderTimer);
          streamingRenderTimer = null;
        }
      }

      if (!finalPayload) {
        throw new Error('RAG stream ended before completion');
      }

      if (sessionId) {
        try {
          await appendSessionMessage(sessionId, buildChatMessage('agent', streamedAnswer, latestMessageData, placeholderTimestamp));
        } catch (error) {
          console.error('Failed to persist streamed assistant message:', error);
        }
      }
      return;
    } catch (error) {
      console.error('RAG query error:', error);
      const content = error instanceof Error
        ? `RAG request failed: ${error.message}`
        : `I couldn't reach the RAG service at ${esgApiBase}. Make sure the ESG API is running on port 8000.`;
      if (sessionId) {
        await addAgentMessageToSession(sessionId, content, 'error');
      } else {
        addAgentMessage(content, 'error');
      }
      return;
    }
  };
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isLoading) return;
    const userMessage = buildChatMessage('user', inputText);
    const nextHistory = [...conversation, userMessage];
    pushConversationMessage(userMessage);
    const query = inputText;
    setInputText('');
    setIsLoading(true);
    setShowPipelineStatus(true);
    setLoadingStepIndex(0);
    setActiveAgentPath(null);
    setAgentTrace([]);
    try {
      let sessionId = currentSessionId;
      let sessionIdToActivateAfterFirstTurn = '';
      if (isAuthenticated && !sessionId) {
        setLoadingStepIndex(1);
        try {
          const session = await createServerSession({
            title: deriveSessionTitle([userMessage]),
            selectedDocumentId: selectedDocument?.id || '',
            mode: 'ask',
          });
          sessionId = session.id;
          sessionIdToActivateAfterFirstTurn = sessionId;
        } catch (error) {
          if (isChatMemoryUnavailableError(error)) {
            console.info('Chat memory is unavailable; continuing without persisted chat history.');
            sessionId = '';
            sessionIdToActivateAfterFirstTurn = '';
            setCurrentSessionId('');
            persistCurrentSessionId('');
            setChatSessionsError('');
          } else {
            throw error;
          }
        }
      }

      if (isAuthenticated && sessionId) {
        try {
          setLoadingStepIndex(1);
          await appendSessionMessage(sessionId, userMessage);
        } catch (error) {
          if (isChatMemoryUnavailableError(error)) {
            console.info('Chat memory is unavailable; continuing without persisted chat history.');
            sessionId = '';
            sessionIdToActivateAfterFirstTurn = '';
            setCurrentSessionId('');
            persistCurrentSessionId('');
            setChatSessionsError('');
          } else if (isMissingChatSessionError(error)) {
            clearCurrentChatSession(sessionId);
            const session = await createServerSession({
              title: deriveSessionTitle([userMessage]),
              selectedDocumentId: selectedDocument?.id || '',
              mode: 'ask',
            });
            sessionId = session.id;
            sessionIdToActivateAfterFirstTurn = sessionId;
            await appendSessionMessage(sessionId, userMessage);
          } else {
            console.error('Failed to persist user message:', error);
          }
        }
      }

      await processUserQuery(
        query,
        nextHistory,
        sessionId,
        (step) => setLoadingStepIndex(step),
        () => setShowPipelineStatus(false),
      );
      if (sessionIdToActivateAfterFirstTurn && sessionId === sessionIdToActivateAfterFirstTurn) {
        setCurrentSessionId(sessionIdToActivateAfterFirstTurn);
        persistCurrentSessionId(sessionIdToActivateAfterFirstTurn);
      }
    } finally {
      setIsLoading(false);
      setShowPipelineStatus(false);
    }
  };
  const handleNewSession = () => {
    setCurrentSessionId('');
    persistCurrentSessionId('');
    setConversation([]);
    setActiveAgentPath(null);
    setAgentTrace([]);
    setActiveTab('chat');
  };
  const handleSelectSession = (id: string) => {
    setCurrentSessionId(id);
    setActiveAgentPath(null);
    setAgentTrace([]);
    setActiveTab('chat');
  };
  const handleDeleteSession = async (id: string) => {
    try {
      const response = await fetch(`${esgApiBase}/chat/sessions/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to delete chat session');
      }
      setChatSessions(prev => prev.filter(session => session.id !== id));
      if (id === currentSessionId) {
        setCurrentSessionId('');
        persistCurrentSessionId('');
        setConversation([]);
      }
    } catch (error) {
      console.error('Delete chat session failed:', error);
      addAgentMessage(
        error instanceof Error ? `Chat delete failed: ${error.message}` : 'Chat delete failed.',
        'error'
      );
    }
  };
  const deleteDocument = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this document?')) {
      return;
    }

    const target = documents.find(doc => doc.id === id);
    if (target?.id === 'sample_esg_report') {
      setDocuments(documents.filter(doc => doc.id !== id));
      setQueryDocumentIds(prev => prev.filter(docId => docId !== id));
      if (selectedDocument?.id === id) {
        setSelectedDocument(null);
        persistSelectedDocumentId('');
      }
      addAgentMessage("Document deleted successfully. You can upload a new one anytime!");
      return;
    }

    try {
      const response = await fetch(`${esgApiBase}/documents/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.message || payload?.detail || payload?.error || 'Unable to delete document');
      }
      const remaining = documents.filter(doc => doc.id !== id);
      setDocuments(remaining);
      setQueryDocumentIds(prev => prev.filter(docId => docId !== id));
      if (selectedDocument?.id === id) {
        const nextSelected = remaining[0] || null;
        setSelectedDocument(nextSelected);
        persistSelectedDocumentId(nextSelected?.id);
        if (nextSelected && nextSelected.id !== 'sample_esg_report') {
          void selectDocument(nextSelected);
        }
      }
      addAgentMessage("Document deleted successfully. You can upload a new one anytime!");
    } catch (error) {
      console.error('Delete document failed:', error);
      addAgentMessage(
        error instanceof Error ? `Document delete failed: ${error.message}` : 'Document delete failed.',
        "error"
      );
    }
  };
  const exportGraph = (document: Document, format: string) => {
    const dataStr = JSON.stringify(document.graph, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = window.document.createElement('a');
    link.href = url;
    link.download = `${document.title}_graph.${format}`;
    link.click();
    URL.revokeObjectURL(url);
    addAgentMessage(`Graph exported successfully as ${format.toUpperCase()}!`);
  };
  const getFilteredRelationships = (relationships: CausalRelationship[]) => {
    return relationships.filter(rel => {
      const matchesSearch = searchTerm === '' || 
        rel.cause.toLowerCase().includes(searchTerm.toLowerCase()) ||
        rel.effect.toLowerCase().includes(searchTerm.toLowerCase()) ||
        rel.evidence.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesType = filterType === '' || 
        rel.relationship_type.toLowerCase().includes(filterType.toLowerCase());
      return matchesSearch && matchesType;
    });
  };
  const handleFileUpload = async (file: File, options: { autoUpload?: boolean } = {}) => {
    console.log('File upload triggered:', file.name, file.type, file.size);
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      addAgentMessage(`[ERROR] File too large: ${(file.size / 1024 / 1024).toFixed(1)}MB. Maximum size is 50MB.`, "error");
      return;
    }

    setUploadedFile(file);
    setIsProcessingFile(true);
    try {
      const lowerName = file.name.toLowerCase();
      const supported =
        lowerName.endsWith('.pdf') ||
        lowerName.endsWith('.doc') ||
        lowerName.endsWith('.docx') ||
        lowerName.endsWith('.txt') ||
        lowerName.endsWith('.rtf') ||
        file.type === 'application/pdf' ||
        file.type === 'text/plain' ||
        file.type.includes('word') ||
        file.type.includes('rtf');

      if (!supported) {
        console.log('Unsupported file type:', file.type);
        throw new Error(`Unsupported file type: ${file.type}. Supported formats: PDF, Word (.doc/.docx), Text (.txt), RTF (.rtf)`);
      }

      const preview = lowerName.endsWith('.txt') || file.type === 'text/plain'
        ? await file.text()
        : '';
      const inferredTitle = options.autoUpload
        ? file.name.replace(/\.[^/.]+$/, '')
        : uploadForm.title || file.name.replace(/\.[^/.]+$/, '');
      setFileContent(preview);
      if (!uploadForm.title) {
        setUploadForm(prev => ({
          ...prev,
          title: inferredTitle
        }));
      }
      if (options.autoUpload) {
        setIsProcessingFile(false);
        await handleUpload({
          title: inferredTitle,
          file,
          content: preview,
          domain: 'general',
          sourceType: '',
          source: '',
          openDocumentsOnComplete: false,
        });
      } else {
        addAgentMessage(`[SUCCESS] File "${file.name}" is ready. Click "Index this report" to upload and process it.`, "success");
      }
    } catch (error) {
      console.error('File processing error:', error);
      addAgentMessage(`[ERROR] Error processing file: ${error instanceof Error ? error.message : 'Unknown error'}. Please try a different file.`, "error");
      setUploadedFile(null);
    } finally {
      setIsProcessingFile(false);
    }
  };

  const handleUploadEntry = () => {
    if (!isAuthenticated) {
      addAgentMessage("Please log in to upload documents.", "error");
      return;
    }
    setActiveTab('upload');
  };

  const totalDocuments = documents.length;
  const agentStarterCards: Array<{ title: string; prompt: string; tier: RagReasoningMode }> = [
    {
      title: 'Summarise',
      prompt: 'Summarise the ESG strategy, targets, risks, and evidence from the most relevant reports.',
      tier: 'flash',
    },
    {
      title: 'Compare',
      prompt: 'Compare the ESG strategy and climate targets across the uploaded reports.',
      tier: 'flash',
    },
    {
      title: 'Assess risk',
      prompt: 'Predict how ESG strategy could affect business risk and share-price narrative using report evidence and graph context.',
      tier: 'deep',
    },
  ];
  const selectedQueryDocuments = queryDocumentIds
    .map((id) => documents.find((doc) => doc.id === id))
    .filter((doc): doc is Document => Boolean(doc))
    .slice(0, 3);
  const effectiveQueryDocumentIds =
    queryScopeMode === 'all'
      ? []
      : (selectedQueryDocuments.length > 0
          ? selectedQueryDocuments.map((doc) => doc.id)
          : (selectedDocument?.id ? [selectedDocument.id] : []));
  const scopedDocumentCount = effectiveQueryDocumentIds.length;
  const queryScopeLabel =
    queryScopeMode === 'all'
      ? 'All reports'
      : scopedDocumentCount > 0
        ? `${scopedDocumentCount} selected`
        : 'Current report';
  const queryScopeDetail =
    queryScopeMode === 'all'
      ? `${totalDocuments} reports available`
      : selectedQueryDocuments.length > 0
        ? selectedQueryDocuments.map((doc) => doc.title).join(', ')
        : selectedDocument?.title || 'No report selected';
  const loadingSteps = getLoadingSteps(tier);
  const currentLoadingStep = loadingSteps[Math.min(loadingStepIndex, loadingSteps.length - 1)];
  const showLongWaitHint = isLoading && loadingElapsedMs >= 8000;
  const visibleAgentTrace = agentTrace.slice(-5);
  const loadingHintText =
    loadingElapsedMs >= 15000
      ? 'Still processing — larger corpora can take longer. The request is active.'
      : 'Still working… retrieval and grounding can take a few more seconds.';
  const filteredSelectedRelationships = getFilteredRelationships(selectedDocument?.relationships || []);
  const navItems = [
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'upload', label: 'Upload', icon: FileUp },
    { id: 'documents', label: 'Library', icon: FolderOpen },
  ];
  // MiniMax-style pill tabs for the mobile section switcher.
  const mobileTabButtonClass = (tab: string) =>
    `inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition ${
      activeTab === tab
        ? 'border-ink bg-ink text-white'
        : 'border-hairline bg-canvas text-ink-steel hover:border-ink hover:text-ink'
    }`;
  const uploadDisabled = isUploading || isProcessingFile || !uploadForm.title || (!uploadedFile && !fileContent && !uploadForm.content);
  const displayedConversation = conversation.filter(
    (message, index) => !(index === 0 && message.type === 'agent' && message.content.includes('CausalGraph'))
  );
  const getFeedbackMessageId = (message: ChatMessage, index: number) => {
    const existing = String(message.data?.messageId || '').trim();
    if (existing) return existing;
    return `${currentSessionId || 'local'}:${message.timestamp.toISOString()}:${index}`;
  };
  const toggleFeedbackTag = (messageId: string, tag: FeedbackReasonTag) => {
    setFeedbackDrafts(prev => {
      const draft = prev[messageId] || { rating: 'down' as FeedbackRating, tags: [], reasonText: '' };
      const nextTags = draft.tags.includes(tag)
        ? draft.tags.filter(item => item !== tag)
        : [...draft.tags, tag];
      return {
        ...prev,
        [messageId]: { ...draft, tags: nextTags, error: '' },
      };
    });
  };
  const setFeedbackReasonText = (messageId: string, reasonText: string) => {
    setFeedbackDrafts(prev => ({
      ...prev,
      [messageId]: {
        ...(prev[messageId] || { rating: 'down' as FeedbackRating, tags: [], reasonText: '' }),
        reasonText,
        error: '',
      },
    }));
  };
  const openDownvoteFeedback = (message: ChatMessage, index: number) => {
    const messageId = getFeedbackMessageId(message, index);
    if (submittedFeedback[messageId] || message.data?.feedback?.rating) return;
    setFeedbackDrafts(prev => {
      if (prev[messageId]) {
        const next = { ...prev };
        delete next[messageId];
        return next;
      }
      return { ...prev, [messageId]: { rating: 'down', tags: [], reasonText: '' } };
    });
  };
  const markFeedbackSubmitted = (message: ChatMessage, messageId: string, rating: FeedbackRating) => {
    setSubmittedFeedback(prev => ({ ...prev, [messageId]: rating }));
    setConversation(prev => prev.map(item => {
      const sameMessage =
        item.data?.messageId === messageId ||
        item.timestamp.getTime() === message.timestamp.getTime();
      if (!sameMessage) return item;
      return {
        ...item,
        data: {
          ...(item.data || {}),
          messageId,
          feedback: {
            rating,
            submittedAt: new Date().toISOString(),
          },
        },
      };
    }));
    setFeedbackDrafts(prev => {
      const next = { ...prev };
      delete next[messageId];
      return next;
    });
  };
  const submitFeedback = async (message: ChatMessage, index: number, rating: FeedbackRating) => {
    const messageId = getFeedbackMessageId(message, index);
    if (submittedFeedback[messageId] || message.data?.feedback?.rating) return;

    const draft = feedbackDrafts[messageId] || { rating, tags: [], reasonText: '' };
    const reasonText = draft.reasonText.trim();
    const reasonTags = rating === 'down' ? draft.tags : [];
    if (rating === 'down' && reasonTags.length === 0 && !reasonText) {
      setFeedbackDrafts(prev => ({
        ...prev,
        [messageId]: { ...draft, rating, error: 'Choose a reason or add a note.' },
      }));
      return;
    }
    if (!token) {
      setFeedbackDrafts(prev => ({
        ...prev,
        [messageId]: { ...draft, rating, error: 'Sign in to send feedback.' },
      }));
      return;
    }

    setFeedbackDrafts(prev => ({
      ...prev,
      [messageId]: { ...draft, rating, submitting: true, error: '' },
    }));

    const payload: FeedbackPayload = {
      session_id: currentSessionId || 'local',
      message_id: messageId,
      query: findPreviousUserPrompt(displayedConversation, index),
      answer: message.content,
      rating,
      reason_tags: reasonTags,
      reason_text: rating === 'down' ? reasonText : '',
      sources: message.data?.sources || [],
      timings_ms: message.data?.timingsMs,
    };

    try {
      const response = await fetch(`${esgApiBase}/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (response.status === 409) {
        markFeedbackSubmitted(message, messageId, rating);
        return;
      }
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response));
      }
      markFeedbackSubmitted(message, messageId, rating);
    } catch (error) {
      setFeedbackDrafts(prev => ({
        ...prev,
        [messageId]: {
          ...draft,
          rating,
          submitting: false,
          error: error instanceof Error ? error.message : 'Unable to send feedback.',
        },
      }));
    }
  };
  const latestSources = [...conversation]
    .reverse()
    .find(message => message.type === 'agent' && message.data?.sources && message.data.sources.length > 0)
    ?.data?.sources || [];
  const latestUserPrompt = [...conversation]
    .reverse()
    .find(message => message.type === 'user' && message.content?.trim())
    ?.content || '';
  const evidenceCards = latestSources.map((src, idx) => {
    const cleanedText = normalizeEvidenceText(src.text);
    const backendRelevance =
      typeof src.relevance_score === 'number'
        ? Math.round(Math.max(0, Math.min(1, src.relevance_score)) * 100)
        : null;
    const relevance = backendRelevance ?? getSourceRelevancePercent(latestUserPrompt, cleanedText);
    return {
      rank: idx + 1,
      documentTitle: src.document_title || src.document_id || 'Untitled source',
      chunkLabel: src.chunk_id || '',
      sourceType: src.source_type || '',
      domain: src.domain || '',
      snippet: pickEvidenceSnippet(cleanedText),
      relevance,
    };
  })
    .filter(card => card.relevance === null || card.relevance >= MIN_EVIDENCE_RELEVANCE_PERCENT)
    .slice(0, 6)
    .map((card, idx) => ({ ...card, rank: idx + 1 }));
  const latestGraphSources = [...conversation]
    .reverse()
    .find(
      message =>
        message.type === 'agent' &&
        message.data?.graphSources &&
        ((message.data.graphSources.matched_entities?.length || 0) > 0 ||
          (message.data.graphSources.edges?.length || 0) > 0),
    )
    ?.data?.graphSources;
  const tracePreviewGraph = buildTracePreviewGraph(latestGraphSources);
  const graphEdges = (latestGraphSources?.edges || [])
    .filter((edge) => edge?.source && edge?.target)
    .slice(0, 6);
  const uploadDisplayTitle = uploadStatusTitle || uploadedFile?.name || uploadForm.title || 'Uploaded document';
  const neo4jCounts = neo4jStatus?.stats?.counts || {};
  const selectedNeo4jSync = selectedDocument?.neo4j_sync;
  const neo4jConnected = Boolean(neo4jStatus?.connected);
  const baseGraph = neo4jGraph || selectedDocument?.graph || null;
  const displayedGraph = sanitizeGraphData(baseGraph);
  const graphFocusNodeId = getGraphFocusNodeId(displayedGraph);
  const graphDegreeMap = displayedGraph ? getGraphDegreeMap(displayedGraph) : new Map<string, number>();
  const graphDomainBreakdown = getDomainBreakdown(displayedGraph);
  const graphTopNodes = getTopConnectedNodes(displayedGraph);
  const selectedGraphNode = displayedGraph?.nodes.find((node: GraphNode) => node.id === selectedGraphNodeId) || null;
  const selectedGraphEdge = displayedGraph?.edges.find((edge: GraphEdge) => getGraphEdgeId(edge) === selectedGraphEdgeId) || null;
  const graphViewTitle = selectedDocument?.title || 'Focused report graph';
  return (
    <div className="cg-workspace h-[calc(100vh-72px)] overflow-hidden text-ink">
      <input
        ref={quickUploadInputRef}
        type="file"
        accept=".pdf,.doc,.docx,.txt,.rtf"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) {
            void handleFileUpload(file, { autoUpload: true });
          }
        }}
      />
      <div className="flex h-full w-full overflow-hidden border-t border-hairline bg-transparent">
        <aside className="cg-sidebar hidden h-full w-60 shrink-0 border-r lg:flex lg:flex-col xl:w-64">
          <div className="border-b border-hairline bg-surface-soft px-3 py-3">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-steel">Agent</div>
                <div className="mt-1 font-display text-[16px] font-semibold tracking-normal text-ink">Research Desk</div>
              </div>
              <span className="rounded-full bg-success-bg px-2 py-0.5 text-[10px] font-semibold text-success">
                Live
              </span>
            </div>
            <button
              onClick={handleNewSession}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-ink px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-ink-charcoal whitespace-nowrap"
            >
              <Plus className="h-4 w-4" />
              New chat
            </button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col bg-surface-soft">
            <div className="flex items-center justify-between px-3 pb-1.5 pt-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Chats</div>
              <div className="text-xs text-ink-stone">{chatSessions.length}</div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-3">
              {isChatSessionsLoading && chatSessions.length === 0 && (
                <div className="px-3 py-4 text-xs text-ink-stone">
                  Loading conversations…
                </div>
              )}
              {chatSessionsError && (
                <div className="px-3 py-2 text-xs text-red-500">
                  {chatSessionsError}
                </div>
              )}
              {chatSessions.length === 0 ? (
                <div className="px-3 py-6 text-center text-xs text-ink-stone">
                  No conversations yet
                </div>
              ) : (
                [...chatSessions]
                  .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))
                  .map((session) => {
                    const isActive = session.id === currentSessionId;
                    return (
                      <div
                        key={session.id}
                        className={`group/session relative mb-1 px-0 ${
                          isActive
                            ? 'cg-list-row cg-list-row-active'
                            : 'rounded-md border border-transparent hover:border-hairline hover:bg-white'
                        }`}
                      >
                        <button
                          onClick={() => handleSelectSession(session.id)}
                          className="block w-full px-2.5 py-2.5 pr-8 text-left"
                        >
                          <div className={`line-clamp-1 text-[13px] font-semibold leading-[1.35] ${isActive ? 'text-ink' : 'text-ink-charcoal'}`}>
                            {session.title || 'New chat'}
                          </div>
                          <div className="mt-1 text-[12px] text-ink-stone">
                            {formatRelativeTime(session.updatedAt)}
                          </div>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm('Delete this conversation?')) {
                              handleDeleteSession(session.id);
                            }
                          }}
                          className={`absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-ink-stone transition hover:bg-hairline hover:text-red-600 ${
                            isActive ? 'opacity-100' : 'opacity-0 group-hover/session:opacity-100'
                          }`}
                          title="Delete chat"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    );
                  })
              )}
            </div>
          </div>

          <div className="border-t border-hairline bg-surface-soft p-2">
            <button
              onClick={handleUploadEntry}
              className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] transition ${
                activeTab === 'upload' ? 'bg-white font-medium text-ink shadow-sm' : 'text-ink-charcoal hover:bg-white'
              }`}
            >
              <FileUp className="h-4 w-4" />
              Upload
              {isUploading && <span className="ml-auto h-2 w-2 rounded-full bg-ink" />}
            </button>
            <button
              onClick={() => setActiveTab('documents')}
              className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] transition ${
                activeTab === 'documents' ? 'bg-white font-medium text-ink shadow-sm' : 'text-ink-charcoal hover:bg-white'
              }`}
            >
              <FolderOpen className="h-4 w-4" />
              Library
              <span className="ml-auto text-[11px] text-ink-stone">{totalDocuments}</span>
            </button>
          </div>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex gap-2 overflow-x-auto border-b border-hairline bg-surface-soft px-3 py-3 lg:hidden">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`${mobileTabButtonClass(item.id)} relative`}
                >
                  {item.id === 'upload' && isUploading && (
                    <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-ink ring-2 ring-white" />
                  )}
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
          </div>

          {isUploading && (
            <div className="flex items-center gap-2 border-b border-hairline bg-white px-4 py-2 text-xs text-ink-charcoal shadow-sm">
              <Loader2 className="h-3 w-3 animate-spin text-ink-charcoal" />
              <span className="truncate">
                {uploadDisplayTitle} · {uploadStage || 'processing'} · {uploadProgress}%
              </span>
            </div>
          )}

          <div className={activeTab === 'chat' ? 'flex min-h-0 flex-1 flex-col overflow-hidden' : 'min-h-0 flex-1 overflow-y-auto p-4 sm:p-5 lg:p-6'}>

        {activeTab === 'chat' && (
          <div className="flex min-h-0 flex-1 overflow-hidden">
          <section className="flex min-h-0 flex-1 flex-col">
            <header className="border-b border-hairline bg-white/95 px-4 py-3 sm:px-6">
              {(() => {
                const currentSession = chatSessions.find(s => s.id === currentSessionId);
                const sessionTitle = currentSession?.title?.trim() || deriveSessionTitle(conversation) || 'New conversation';
                return (
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h1 className="truncate font-display text-[18px] font-semibold leading-[1.35] tracking-normal text-ink">
                        {sessionTitle}
                      </h1>
                      <p className="mt-0.5 truncate text-[12px] text-ink-steel" title={queryScopeDetail}>
                        Scope: {queryScopeLabel}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {latestSources.length > 0 && (
                        <button
                          onClick={() => setIsEvidencePanelOpen(prev => !prev)}
                          className="hidden h-8 items-center gap-1.5 rounded-full border border-hairline bg-canvas px-3 text-[12px] font-semibold text-ink-charcoal transition hover:border-ink xl:inline-flex"
                          title={isEvidencePanelOpen ? 'Hide evidence panel' : 'Show evidence panel'}
                        >
                          {isEvidencePanelOpen ? (
                            <ChevronRight className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronLeft className="h-3.5 w-3.5" />
                          )}
                          <span>Evidence</span>
                        </button>
                      )}
                      <button
                        onClick={handleUploadEntry}
                        className="inline-flex h-8 items-center gap-1.5 rounded-full border border-hairline bg-canvas px-3 text-[12px] font-semibold text-ink-charcoal transition hover:border-ink"
                        title="Upload report"
                      >
                        <FileUp className="h-3.5 w-3.5" />
                        <span className="hidden sm:inline">Upload</span>
                      </button>
                    </div>
                  </div>
                );
              })()}
            </header>

            <div
              ref={conversationScrollRef}
              onScroll={updateAutoFollowConversation}
              className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-white px-4 py-5 sm:px-6"
            >
              <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col">
                {displayedConversation.length === 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.45 }}
                    className="flex flex-1 items-center justify-center"
                  >
                    <div className="w-full max-w-3xl px-4 py-10 text-center sm:px-8">
                      <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-hairline bg-white text-ink shadow-sm">
                        <MessageSquare className="h-5 w-5" />
                      </div>
                      <h1 className="font-display text-[30px] font-semibold leading-[1.16] tracking-normal text-ink sm:text-[38px]">
                        Ask across your reports
                      </h1>
                      <p className="mx-auto mt-3 max-w-xl text-[14px] leading-6 text-ink-steel sm:text-[15px]">
                        Start with a question, upload a report, or choose a smaller document scope.
                      </p>
                      <div className="mt-6 flex flex-wrap justify-center gap-2">
                        <button
                          type="button"
                          onClick={handleUploadEntry}
                          className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-ink-charcoal"
                        >
                          <FileUp className="h-4 w-4" />
                          Upload report
                        </button>
                        <button
                          type="button"
                          onClick={() => setActiveTab('documents')}
                          className="inline-flex items-center gap-2 rounded-full border border-hairline bg-white px-4 py-2 text-[13px] font-semibold text-ink-charcoal shadow-sm transition hover:border-ink hover:text-ink"
                        >
                          <FolderOpen className="h-4 w-4" />
                          Choose reports
                        </button>
                      </div>
                      <div className="mt-5 flex flex-wrap justify-center gap-2">
                        {agentStarterCards.map((card) => (
                          <button
                            key={card.title}
                            type="button"
                            onClick={() => {
                              setTier(card.tier);
                              setInputText(card.prompt);
                            }}
                            className="rounded-full border border-hairline bg-white px-4 py-2 text-[13px] font-semibold text-ink-charcoal shadow-sm transition hover:border-ink hover:bg-surface-soft hover:text-ink"
                          >
                            {card.title}
                          </button>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                )}

                <div className="space-y-6">
                  {displayedConversation.map((message, index) => {
                    const isUser = message.type === 'user';

                    if (isUser) {
                      return (
                        <motion.div
                          key={index}
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.35 }}
                          className="group flex flex-col items-end"
                        >
                          <div className="cg-message-user max-w-[80%] px-5 py-3 text-[14px] leading-[1.55] shadow-sm">
                            <div className="prose prose-sm prose-invert max-w-none leading-[1.55] [&>p]:mb-1 [&>p:last-child]:mb-0 [&>ul]:pl-4 [&>ol]:pl-4">
                              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: 'ignore' }]]}>
                                {normalizeMathForMarkdown(message.content)}
                              </ReactMarkdown>
                            </div>
                          </div>
                          <div className="mt-1.5 text-[11px] tracking-normal text-ink-stone opacity-0 transition-opacity group-hover:opacity-100">
                            {message.timestamp.toLocaleTimeString()}
                          </div>
                        </motion.div>
                      );
                    }

                    const feedbackMessageId = getFeedbackMessageId(message, index);
                    const feedbackRating = submittedFeedback[feedbackMessageId] || message.data?.feedback?.rating;
                    const feedbackDraft = feedbackDrafts[feedbackMessageId];
                    const canSubmitFeedback = Boolean(message.content.trim() && message.data?.backend);
                    const messageAgentTrace = message.data?.agentTrace || [];
                    const isAgentAnswer = message.data?.agentPath === 'agent' || messageAgentTrace.length > 0;

                    return (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.35 }}
                        className="group"
                      >
                        <div className="flex gap-3">
                          <div className="cg-icon-well mt-0.5 h-8 w-8 shrink-0 bg-ink text-white">
                            <Network className="h-4 w-4" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="cg-message-assistant prose prose-sm max-w-none text-[14px] leading-[1.7] text-ink-charcoal [&>p]:mb-2.5 [&>ul]:pl-4 [&>ol]:pl-4 [&>ul>li]:mb-1.5 [&>ol>li]:mb-1.5 [&>h1]:font-display [&>h2]:font-display [&>h3]:font-display [&>h4]:font-display [&>code]:font-mono [&>pre]:font-mono">
                              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: 'ignore' }]]}>
                                {normalizeStreamingMarkdown(message.content)}
                              </ReactMarkdown>
                            </div>

                            {isAgentAnswer && (
                              <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-ink-steel">
                                <span className="inline-flex items-center gap-1 rounded-md border border-hairline bg-white px-2 py-0.5">
                                  <BrainCircuit className="h-3 w-3 text-ink-charcoal" />
                                  Evidence agent
                                </span>
                                {messageAgentTrace.length > 0 && (
                                  <span className="inline-flex items-center rounded-md border border-hairline bg-white px-2 py-0.5">
                                    {messageAgentTrace.length} steps
                                  </span>
                                )}
                                {message.data?.partial && (
                                  <span className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-800">
                                    <AlertCircle className="h-3 w-3" />
                                    Partial
                                  </span>
                                )}
                              </div>
                            )}

                            {message.data?.sources && message.data.sources.length > 0 && (
                              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                                <span className="cg-eyebrow text-ink-steel">Cites</span>
                                {message.data.sources.slice(0, 4).map((source, sourceIdx) => (
                                  <span
                                    key={`${source.chunk_id || source.document_id || sourceIdx}-${sourceIdx}`}
                                    className="inline-flex items-center gap-1 rounded-md border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-ink-charcoal"
                                  >
                                    <FileText className="h-3 w-3 text-ink-stone" />
                                    {formatSourceChipLabel(source)}
                                  </span>
                                ))}
                              </div>
                            )}

                            {canSubmitFeedback && (
                              <div className="mt-3">
                                <div className="flex items-center gap-1.5">
                                  <button
                                    type="button"
                                    onClick={() => void submitFeedback(message, index, 'up')}
                                    disabled={Boolean(feedbackRating || feedbackDraft?.submitting)}
                                    aria-pressed={feedbackRating === 'up'}
                                    aria-label="Mark answer helpful"
                                    title="Helpful"
                                    className={`cg-btn-icon !h-7 !w-7 disabled:cursor-not-allowed ${
                                      feedbackRating === 'up'
                                        ? '!border-ink !bg-ink !text-white'
                                        : '!text-ink-steel hover:!text-ink'
                                    } ${feedbackRating && feedbackRating !== 'up' ? 'opacity-45' : ''}`}
                                  >
                                    <ThumbsUp className="h-3.5 w-3.5" />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => openDownvoteFeedback(message, index)}
                                    disabled={Boolean(feedbackRating || feedbackDraft?.submitting)}
                                    aria-pressed={feedbackRating === 'down'}
                                    aria-label="Mark answer unhelpful"
                                    title="Unhelpful"
                                    className={`cg-btn-icon !h-7 !w-7 disabled:cursor-not-allowed ${
                                      feedbackRating === 'down'
                                        ? '!border-ink !bg-ink !text-white'
                                        : '!text-ink-steel hover:!text-ink'
                                    } ${feedbackRating && feedbackRating !== 'down' ? 'opacity-45' : ''}`}
                                  >
                                    <ThumbsDown className="h-3.5 w-3.5" />
                                  </button>
                                  {feedbackRating && (
                                    <span className="ml-1 inline-flex items-center gap-1 text-[11px] font-medium text-ink-steel">
                                      <CheckCircle2 className="h-3 w-3" />
                                      Feedback sent
                                    </span>
                                  )}
                                  {feedbackDraft?.error && feedbackDraft.rating !== 'down' && (
                                    <span className="ml-1 inline-flex items-center gap-1 text-[11px] font-medium text-red-600">
                                      <AlertCircle className="h-3 w-3" />
                                      {feedbackDraft.error}
                                    </span>
                                  )}
                                </div>

                                {feedbackDraft && feedbackDraft.rating === 'down' && !feedbackRating && (
                                  <div className="mt-2 max-w-xl rounded-lg border border-hairline bg-white p-3 shadow-sm">
                                    <div className="flex flex-wrap gap-1.5">
                                      {FEEDBACK_REASON_OPTIONS.map(option => {
                                        const selected = feedbackDraft.tags.includes(option.tag);
                                        return (
                                          <label
                                            key={option.tag}
                                            className={`inline-flex cursor-pointer items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold transition ${
                                              selected
                                                ? 'border-ink bg-ink text-white'
                                                : 'border-hairline bg-canvas text-ink-steel hover:border-ink hover:text-ink'
                                            }`}
                                          >
                                            <input
                                              type="checkbox"
                                              checked={selected}
                                              onChange={() => toggleFeedbackTag(feedbackMessageId, option.tag)}
                                              className="sr-only"
                                            />
                                            {option.label}
                                          </label>
                                        );
                                      })}
                                    </div>
                                    {feedbackDraft.tags.includes('other') && (
                                      <textarea
                                        value={feedbackDraft.reasonText}
                                        onChange={(event) => setFeedbackReasonText(feedbackMessageId, event.target.value)}
                                        rows={2}
                                        placeholder="Add a note"
                                        className="mt-2 block w-full resize-none rounded-lg border border-hairline bg-canvas px-3 py-2 text-[12px] leading-5 text-ink outline-none placeholder:text-ink-stone focus:border-ink"
                                      />
                                    )}
                                    {feedbackDraft.error && (
                                      <div className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-red-600">
                                        <AlertCircle className="h-3 w-3" />
                                        <span>{feedbackDraft.error}</span>
                                      </div>
                                    )}
                                    <div className="mt-2 flex justify-end gap-1.5">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setFeedbackDrafts(prev => {
                                            const next = { ...prev };
                                            delete next[feedbackMessageId];
                                            return next;
                                          });
                                        }}
                                        className="rounded-full border border-hairline px-3 py-1 text-[11px] font-semibold text-ink-steel transition hover:border-ink hover:text-ink"
                                      >
                                        Cancel
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => void submitFeedback(message, index, 'down')}
                                        disabled={feedbackDraft.submitting}
                                        className="rounded-full border border-ink bg-ink px-3 py-1 text-[11px] font-semibold text-white transition hover:bg-ink-charcoal disabled:cursor-not-allowed disabled:opacity-60"
                                      >
                                        {feedbackDraft.submitting ? 'Sending...' : 'Submit'}
                                      </button>
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}

                            <div className="mt-1.5 text-[11px] text-ink-stone opacity-0 transition-opacity group-hover:opacity-100">
                              {message.timestamp.toLocaleTimeString()}
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}

                  {showPipelineStatus && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-5">
                      <div className="cg-eyebrow mb-3 text-ink-charcoal">Assistant</div>
                      <div className="flex items-center gap-2 text-[15px] text-ink-steel">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>{currentLoadingStep}</span>
                      </div>
                      <div className="mt-1.5 text-[11px] text-ink-stone">
                        Step {Math.min(loadingStepIndex + 1, loadingSteps.length)}/{loadingSteps.length}
                      </div>
                      {activeAgentPath === 'agent' && visibleAgentTrace.length > 0 && (
                        <div className="mt-3 max-w-xl rounded-lg border border-hairline bg-white px-3 py-2 shadow-sm">
                          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-ink-charcoal">
                            <BrainCircuit className="h-3.5 w-3.5" />
                            Evidence agent
                          </div>
                          <div className="space-y-1">
                            {visibleAgentTrace.map((step, traceIndex) => {
                              const status = String(step.status || '').toLowerCase();
                              const TraceIcon = status === 'running'
                                ? Loader2
                                : status === 'completed'
                                  ? CheckCircle2
                                  : status === 'failed'
                                    ? AlertCircle
                                    : Circle;
                              return (
                                <div
                                  key={`${step.step}-${step.tool || step.stage}-${traceIndex}`}
                                  className="flex min-w-0 items-start gap-2 text-[12px] leading-5 text-ink-steel"
                                >
                                  <TraceIcon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                                    status === 'running'
                                      ? 'animate-spin text-ink-charcoal'
                                      : status === 'completed'
                                        ? 'text-emerald-700'
                                        : status === 'failed'
                                          ? 'text-red-600'
                                          : 'text-ink-stone'
                                  }`} />
                                  <span className="min-w-0 flex-1 truncate">
                                    <span className="font-medium text-ink-charcoal">{formatAgentStage(step)}</span>
                                    {step.summary ? <span className="text-ink-stone"> · {step.summary}</span> : null}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      {showLongWaitHint && (
                        <p className="mt-2 text-[12px] text-ink-steel">
                          {loadingHintText}
                        </p>
                      )}
                    </motion.div>
                  )}
                  {showPipelineStatus && <div aria-hidden="true" className="h-[34vh] min-h-40 max-h-80 shrink-0" />}
                  <div ref={conversationEndRef} />
                </div>
              </div>
            </div>

            <div className="border-t border-hairline bg-surface-soft px-4 py-3 sm:px-6">
              <div className="mx-auto w-full max-w-5xl">
                <form
                  onSubmit={handleSubmit}
                  className="cg-agent-composer px-3 py-2 transition"
                >
                  <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setQueryScopeMode(queryScopeMode === 'all' ? 'selected' : 'all')}
                      className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-canvas px-2.5 py-1 text-[11px] font-semibold text-ink-charcoal transition hover:border-ink hover:text-ink"
                      title="Toggle document scope"
                    >
                      <FolderOpen className="h-3 w-3" />
                      <span>Scope: {queryScopeLabel}</span>
                    </button>
                    {queryScopeMode !== 'all' && effectiveQueryDocumentIds.slice(0, 2).map((docId) => {
                      const doc = documents.find(item => item.id === docId);
                      if (!doc) return null;
                      const removable = queryDocumentIds.includes(docId);
                      return (
                        <span key={docId} className="inline-flex min-w-0 items-center gap-1 rounded-full border border-hairline bg-surface px-2 py-0.5 text-[11px] font-medium text-ink-charcoal">
                          <span className="truncate max-w-[160px]">{doc.title}</span>
                          {removable && (
                            <button
                              type="button"
                              onClick={() => setQueryDocumentIds((prev) => prev.filter((id) => id !== docId))}
                              className="text-ink-faint transition hover:text-ink-charcoal"
                              title="Remove from query scope"
                            >
                              ×
                            </button>
                          )}
                        </span>
                      );
                    })}
                    {queryScopeMode !== 'all' && (
                      <button
                        type="button"
                        onClick={() => setActiveTab('documents')}
                        className="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold text-ink-steel transition hover:bg-surface-soft hover:text-ink"
                        title="Pick query documents"
                      >
                        Change
                      </button>
                    )}
                  </div>
                  <textarea
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={(e) => {
                      // Skip Enter-to-send while an IME composition session is
                      // active — Chinese/Japanese/Korean users press Enter to
                      // confirm candidates or commit Pinyin, not to submit.
                      // `nativeEvent.isComposing` and the legacy keyCode 229
                      // both flag this state.
                      if (
                        e.key === 'Enter' &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing &&
                        e.keyCode !== 229
                      ) {
                        e.preventDefault();
                        handleSubmit(e as unknown as React.FormEvent);
                      }
                    }}
                    placeholder={
                      tier === 'deep'
                        ? 'Ask a deep analytical question: causal reasoning, scenarios, comparisons…'
                        : 'Query emissions, targets, risks, governance, or supply-chain signals…'
                    }
                    rows={1}
                    className="block max-h-28 min-h-[30px] w-full resize-none border-0 bg-transparent px-1 py-1 text-[14px] leading-[1.5] text-ink outline-none placeholder:text-ink-stone"
                    disabled={isLoading}
                  />
                  <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <button
                        type="button"
                        onClick={handleUploadEntry}
                        disabled={isUploading || isProcessingFile}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-hairline bg-white text-ink-charcoal shadow-sm transition hover:border-ink hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                        title="Upload report"
                        aria-label="Upload report"
                      >
                        <Paperclip className="h-4 w-4" />
                      </button>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div
                        className="inline-flex items-center rounded-full border border-hairline bg-white p-0.5"
                        role="group"
                        aria-label="Reasoning tier"
                      >
                        <button
                          type="button"
                          onClick={() => setTier('flash')}
                          aria-pressed={tier === 'flash'}
                          className={`inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[12px] font-semibold transition ${
                            tier === 'flash'
                              ? 'bg-ink text-white shadow-sm'
                              : 'text-ink-steel hover:bg-surface-soft hover:text-ink'
                          }`}
                          title="Fast grounded answers"
                        >
                          <Zap className="h-3.5 w-3.5" />
                          <span>Fast</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setTier('deep')}
                          aria-pressed={tier === 'deep'}
                          className={`inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[12px] font-semibold transition ${
                            tier === 'deep'
                              ? 'bg-ink text-white shadow-sm'
                              : 'text-ink-steel hover:bg-surface-soft hover:text-ink'
                          }`}
                          title="Deeper analysis and graph reasoning"
                        >
                          <BrainCircuit className="h-3.5 w-3.5" />
                          <span>Deep</span>
                        </button>
                      </div>
                      <button
                        type="submit"
                        disabled={!inputText.trim() || isLoading}
                        className="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-full bg-ink text-white shadow-sm transition hover:bg-ink-charcoal active:translate-y-[0.5px] disabled:cursor-not-allowed disabled:bg-surface-soft disabled:text-ink-stone disabled:shadow-none"
                        title="Send (Enter)"
                        aria-label="Send"
                      >
                        <ArrowUp className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </form>
                <div className="mt-1 px-1 text-right">
                  <span className="cg-eyebrow text-ink-stone">
                    Enter to send
                  </span>
                </div>
              </div>
            </div>
          </section>

          {isEvidencePanelOpen && (
            <EvidencePanel
              evidenceCards={evidenceCards}
              latestGraphSources={latestGraphSources}
              tracePreviewGraph={tracePreviewGraph}
              graphEdges={graphEdges}
              neo4jConnected={neo4jConnected}
            />
          )}
          </div>
        )}

          {activeTab === 'upload' && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mx-auto w-full max-w-[1320px] space-y-5"
            >
              <header className="cg-tool-panel px-6 py-5 sm:px-7">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <h2 className="font-display text-[28px] font-semibold leading-[1.16] tracking-normal text-ink">
                      Upload a report
                    </h2>
                    <p className="mt-2 max-w-xl text-sm leading-6 text-ink-steel">
                      Add a file or paste text, then index it for search.
                    </p>
                  </div>
                  <span className="rounded-full border border-hairline bg-surface-soft px-3 py-1.5 text-xs font-semibold text-ink-charcoal">
                    PDF, Word, Text, RTF
                  </span>
                </div>
              </header>

              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr),420px]">
                <section className="cg-tool-panel p-5 sm:p-6">
                  <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h3 className="text-base font-semibold text-ink">Source</h3>
                      <p className="mt-1 text-sm text-ink-steel">Choose one input method.</p>
                    </div>
                    <div className="inline-flex rounded-lg border border-hairline bg-surface-soft p-0.5">
                      {([
                        { id: 'file', label: 'Upload file' },
                        { id: 'text', label: 'Paste text' },
                      ] as const).map((option) => (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => {
                            setUploadInputMode(option.id);
                            if (option.id === 'file') {
                              setUploadForm((prev) => ({ ...prev, content: '' }));
                            } else {
                              setUploadedFile(null);
                              setFileContent('');
                            }
                          }}
                          className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                            uploadInputMode === option.id
                              ? 'bg-ink text-white shadow-sm'
                              : 'text-ink-steel hover:bg-white hover:text-ink'
                          }`}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {uploadInputMode === 'file' ? (
                    <>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.doc,.docx,.txt,.rtf"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            handleFileUpload(file);
                          }
                        }}
                        className="hidden"
                        id="file-upload"
                      />
                      {!uploadedFile ? (
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => fileInputRef.current?.click()}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              fileInputRef.current?.click();
                            }
                          }}
                          onDragOver={(e) => {
                            e.preventDefault();
                            setIsDraggingFile(true);
                          }}
                          onDragLeave={() => setIsDraggingFile(false)}
                          onDrop={(e) => {
                            e.preventDefault();
                            setIsDraggingFile(false);
                            const file = e.dataTransfer.files?.[0];
                            if (file) handleFileUpload(file);
                          }}
                          className={`flex min-h-[260px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
                            isDraggingFile
                              ? 'border-ink bg-white shadow-sm'
                              : 'border-hairline bg-surface-soft hover:border-ink-stone hover:bg-white'
                          }`}
                        >
                          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-hairline bg-white">
                            <FileUp className={`h-5 w-5 ${isDraggingFile ? 'text-ink' : 'text-ink-stone'}`} />
                          </div>
                          <p className="mt-4 text-[16px] font-semibold text-ink">
                            {isDraggingFile ? 'Release to upload' : 'Drop file or browse'}
                          </p>
                          <p className="mt-2 max-w-md text-sm leading-6 text-ink-steel">
                            Files up to 50MB. Text files show a quick preview.
                          </p>
                          {isProcessingFile && (
                            <div className="mt-4 flex items-center gap-2 text-xs text-ink-steel">
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              <span>Processing file…</span>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="rounded-2xl border border-hairline bg-surface-soft p-4">
                          <div className="flex items-start gap-3">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-ink-charcoal">
                              <FileUp className="h-4 w-4" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium text-ink">{uploadedFile.name}</p>
                              <p className="text-xs text-ink-steel">{(uploadedFile.size / 1024).toFixed(1)} KB</p>
                            </div>
                            <button
                              onClick={() => {
                                setUploadedFile(null);
                                setFileContent('');
                              }}
                              className="text-xs font-medium text-ink-steel transition hover:text-red-600"
                            >
                              Remove
                            </button>
                          </div>
                          {fileContent && (
                            <details className="group/preview mt-3">
                              <summary className="flex cursor-pointer items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-steel hover:text-ink-charcoal">
                                <span className="text-ink-stone transition-transform group-open/preview:rotate-90">›</span>
                                Preview first 200 characters
                              </summary>
                              <div className="mt-2 max-h-24 overflow-y-auto rounded-md border border-hairline bg-white p-3 text-xs leading-5 text-ink-charcoal">
                                {fileContent.substring(0, 200)}
                                {fileContent.length > 200 && <span className="text-ink-stone">…</span>}
                              </div>
                            </details>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div>
                      <textarea
                        value={uploadForm.content}
                        onChange={(e) => setUploadForm({ ...uploadForm, content: e.target.value })}
                        rows={15}
                        className="w-full min-h-[320px] resize-none rounded-2xl border border-hairline bg-surface-soft px-4 py-3 text-sm leading-6 text-ink outline-none transition focus:border-ink-steel focus:ring-1 focus:ring-ink/10"
                        placeholder="Paste the report text here. You can add a full section, a short excerpt, or the complete report if needed."
                      />
                    </div>
                  )}
                </section>

                <aside className="cg-tool-panel p-5 sm:p-6">
                  <div className="mb-5">
                    <h3 className="text-base font-semibold text-ink">Report details</h3>
                    <p className="mt-1 text-sm leading-6 text-ink-steel">
                      {isAdmin
                        ? 'Labels are optional for managed uploads.'
                        : 'Give the report a clear name.'}
                    </p>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-ink-steel">
                        Report title <span className="text-ink-stone">*</span>
                      </label>
                      <input
                        type="text"
                        value={uploadForm.title}
                        onChange={(e) => setUploadForm({ ...uploadForm, title: e.target.value })}
                        className="w-full rounded-lg border border-hairline px-3 py-2 text-sm text-ink outline-none transition focus:border-ink-steel focus:ring-1 focus:ring-ink/10"
                        placeholder={uploadedFile?.name || 'Enter document title'}
                      />
                    </div>

                    {isAdmin && (
                      <>
                        <div>
                          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-ink-steel">
                            Category
                          </label>
                          <select
                            value={uploadForm.domain}
                            onChange={(e) => setUploadForm({ ...uploadForm, domain: e.target.value })}
                            className="w-full rounded-lg border border-hairline px-3 py-2 text-sm text-ink outline-none transition focus:border-ink-steel focus:ring-1 focus:ring-ink/10"
                          >
                            <option value="general">General</option>
                            <option value="esg_report">ESG report</option>
                            <option value="academic">Academic prior</option>
                            <option value="regulatory">Regulatory context</option>
                            <option value="news">News</option>
                            <option value="environmental">Environmental</option>
                            <option value="social">Social</option>
                            <option value="governance">Governance</option>
                          </select>
                        </div>

                        <div>
                          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-ink-steel">
                            Source type
                          </label>
                          <select
                            value={uploadForm.source_type}
                            onChange={(e) => setUploadForm({ ...uploadForm, source_type: e.target.value })}
                            className="w-full rounded-lg border border-hairline px-3 py-2 text-sm text-ink outline-none transition focus:border-ink-steel focus:ring-1 focus:ring-ink/10"
                          >
                            <option value="">Auto-detect</option>
                            <option value="corporate_disclosure">Corporate disclosure</option>
                            <option value="peer_reviewed">Peer reviewed</option>
                            <option value="regulatory_doc">Regulatory document</option>
                            <option value="analyst_report">Analyst report</option>
                            <option value="news_article">News article</option>
                          </select>
                        </div>
                      </>
                    )}
                  </div>

                  <button
                    onClick={() => handleUpload()}
                    disabled={uploadDisabled}
                    className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink-charcoal active:translate-y-[0.5px] disabled:cursor-not-allowed disabled:bg-hairline disabled:text-ink-muted"
                  >
                    {isUploading ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>{uploadStage ? `${uploadStage}…` : 'Processing…'}</span>
                      </>
                    ) : (
                      <>
                        <Database className="h-4 w-4" />
                        <span>Index this report</span>
                      </>
                    )}
                  </button>

                  {isUploading && (
                    <div className="mt-4 space-y-2">
                      <div className="flex items-center justify-between text-xs text-ink-steel">
                        <span className="truncate">{uploadMessage || uploadStage || 'Processing'}</span>
                        <span className="ml-2 shrink-0 font-mono text-[12px] font-semibold text-ink-charcoal">
                          {uploadProgress}%
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-surface-soft">
                        <div
                          className="h-full bg-ink transition-all duration-500"
                          style={{ width: `${Math.max(4, uploadProgress)}%` }}
                        />
                      </div>
                    </div>
                  )}
                </aside>
              </div>
            </motion.div>
          )}

	          {activeTab === 'documents' && (
	            <motion.div
	              initial={{ opacity: 0, y: 20 }}
	              animate={{ opacity: 1, y: 0 }}
	              className="grid min-w-0 gap-4 2xl:grid-cols-[minmax(280px,360px),minmax(0,1fr)]"
	            >
	              <div className="cg-tool-panel min-w-0 p-4 sm:p-5">
	                <div className="mb-5 flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-display text-[22px] font-semibold leading-[1.25] tracking-normal text-ink">
                      Library
                    </h2>
                    <p className="mt-1 text-sm text-ink-steel">Pick reports for focused questions.</p>
                  </div>
                  <span className="cg-chip font-mono text-[11px] text-ink-charcoal">
                    {documents.length} items
                  </span>
                </div>
                {documentsError && (
                  <div
                    className="mb-4 rounded-md border px-3 py-2 text-sm"
                    style={{
                      borderColor: 'var(--cg-warn-border)',
                      background: 'var(--cg-warn-bg)',
                      color: 'var(--cg-warn)',
                    }}
                  >
                    {documentsError}
                  </div>
                )}
                {isDocumentsLoading && (
                  <div className="mb-4 flex items-center gap-2 text-sm text-ink-steel">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Loading documents from backend…</span>
                  </div>
                )}
                <div className="space-y-3">
                  {documents.map((doc) => {
                    const inQueryScope = queryDocumentIds.includes(doc.id);
                    const canAddToScope = inQueryScope || queryDocumentIds.length < 3;
                    return (
                    <div
                      key={doc.id}
                      className={`group min-w-0 cursor-pointer p-4 ${
                        selectedDocument?.id === doc.id
	                          ? 'cg-list-row cg-list-row-active'
                          : 'cg-list-row'
                      }`}
                      onClick={() => {
                        void selectDocument(doc);
                      }}
                    >
	                      <div className="flex min-w-0 items-start justify-between gap-3">
	                        <div className="min-w-0 flex-1">
	                          <h3 className="mb-2 line-clamp-2 break-words font-display text-[15px] font-semibold leading-[1.4] tracking-normal text-ink">
	                            {doc.title}
	                          </h3>
	                          <p className="text-sm text-ink-steel">
                              {doc.graph?.metadata?.node_count || 0} concepts · {doc.relationship_count ?? (doc.relationships?.length || 0)} relationships
                            </p>
	                          {doc.source && (
	                            <p className="mt-1 line-clamp-1 break-words text-xs text-ink-stone">{doc.source}</p>
	                          )}
	                        </div>
                        <div className="flex items-start gap-1">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setQueryScopeMode('selected');
                              setQueryDocumentIds((prev) => {
                                if (prev.includes(doc.id)) {
                                  return prev.filter((id) => id !== doc.id);
                                }
                                if (prev.length >= 3) return prev;
                                return [...prev, doc.id];
                              });
                            }}
                            disabled={!canAddToScope}
                            className={`inline-flex h-6 items-center rounded-md border px-2 text-[10px] font-semibold uppercase tracking-[0.08em] transition ${
                              inQueryScope
                                ? 'border-ink bg-ink text-white'
                                : canAddToScope
                                  ? 'border-hairline bg-white text-ink-charcoal hover:border-hairline hover:text-ink'
                                  : 'cursor-not-allowed border-hairline bg-surface-soft text-ink-stone'
                            }`}
                            title={inQueryScope ? 'Remove from query scope' : canAddToScope ? 'Add to query scope' : 'You can select up to 3 documents'}
                          >
                            {inQueryScope ? 'Selected' : canAddToScope ? 'Use' : 'Max 3'}
                          </button>
                          {isAdmin && (() => {
                            const isLoading = loadingDocumentId === doc.id;
                            const synced = Boolean(doc.neo4j_sync?.synced);
                            const syncEnabled = doc.neo4j_sync?.enabled !== false;
                            const failed = syncEnabled && !synced && !isLoading && Boolean(doc.neo4j_sync?.reason);
                            if (isLoading) {
                              return (
                                <span className="mt-1 inline-flex h-5 w-5 items-center justify-center" title="Loading detail">
                                  <Loader2 className="h-3.5 w-3.5 animate-spin text-ink-steel" />
                                </span>
                              );
                            }
                            if (synced) {
                              return (
                                <span
                                  className="mt-1 inline-flex h-5 w-5 items-center justify-center"
                                  title="Synced to Neo4j"
                                >
                                  <CheckCircle2 className="h-3.5 w-3.5" style={{ color: 'var(--cg-success)' }} />
                                </span>
                              );
                            }
                            if (failed) {
                              return (
                                <span
                                  className="mt-1 inline-flex h-5 w-5 items-center justify-center"
                                  title={doc.neo4j_sync?.reason || 'Sync failed'}
                                >
                                  <AlertCircle className="h-3.5 w-3.5" style={{ color: 'var(--cg-warn)' }} />
                                </span>
                              );
                            }
                            return (
                              <span className="mt-1 inline-flex h-5 w-5 items-center justify-center" title="Not synced">
                                <Circle className="h-3 w-3 text-ink-faint" />
                              </span>
                            );
                          })()}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              exportGraph(doc, 'json');
                            }}
                            className="rounded-md p-1.5 text-ink-steel opacity-100 transition hover:bg-surface-soft hover:text-ink sm:opacity-0 sm:group-hover:opacity-100"
                            title="Export graph"
                          >
                            <Download className="h-4 w-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteDocument(doc.id);
                            }}
                            className="rounded-md p-1.5 text-ink-steel opacity-100 transition hover:bg-red-50 hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100"
                            title="Delete report"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                  )})}
                </div>
	              </div>
	              {selectedDocument && (
	                <div className="cg-tool-panel min-w-0 p-4 sm:p-5 lg:p-6">
	                  <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
	                    <div className="min-w-0">
	                      <h3 className="break-words text-2xl font-semibold leading-tight text-ink">{selectedDocument.title}</h3>
	                      <p className="mt-1 text-sm text-ink-steel">Overview of what was extracted from this report.</p>
                        {loadingDocumentId === selectedDocument.id && (
                          <p className="mt-2 text-sm text-ink-steel">Loading document detail...</p>
                        )}
	                    </div>
                    <button
                      onClick={() => setActiveTab('chat')}
                      className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink-charcoal"
                    >
                      Query corpus
                    </button>
                  </div>
                  <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <div className="cg-tool-panel-soft p-4">
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-steel">Concepts</div>
                      <div className="mt-2 text-3xl font-semibold text-ink">{selectedDocument.graph?.metadata?.node_count || 0}</div>
                    </div>
                    <div className="cg-tool-panel-soft p-4">
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-steel">Connections</div>
                      <div className="mt-2 text-3xl font-semibold text-ink">{selectedDocument.graph?.metadata?.edge_count || 0}</div>
                    </div>
                    <div className="cg-tool-panel-soft p-4">
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-steel">Structure</div>
                      <div className="mt-2 text-2xl font-semibold text-ink">
                        {selectedDocument.graph?.metadata?.is_acyclic ? 'Acyclic' : 'Cyclic'}
                      </div>
                    </div>
                  </div>

                  {isAdmin && (
                    <div className="cg-tool-panel-soft mb-6 p-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-hairline bg-white text-ink-charcoal">
                          <Database className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h4 className="text-sm font-semibold text-ink">Neo4j persistence</h4>
                            <span
                              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                                neo4jConnected
                                  ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                                  : 'bg-amber-50 text-amber-700 ring-1 ring-amber-200'
                              }`}
                            >
                              {neo4jConnected ? 'Connected' : 'Unavailable'}
                            </span>
                          </div>
                          <p className="mt-1 break-words text-sm text-ink-steel">
                            {neo4jStatus
                              ? neo4jConnected
                                ? 'Graph persistence is online.'
                                : neo4jStatus.message || neo4jStatus.reason || 'Neo4j status check failed.'
                              : 'Checking Neo4j status...'}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handleOpenFullGraph}
                          className="inline-flex items-center justify-center rounded-lg border border-hairline bg-white px-3 py-2 text-sm font-medium text-ink-charcoal transition hover:bg-surface-soft"
                        >
                          <Network className="mr-2 h-4 w-4" />
                          Open full graph
                        </button>
                        <button
                          onClick={() => setActiveTab('upload')}
                          className="inline-flex items-center justify-center rounded-lg border border-hairline bg-white px-3 py-2 text-sm font-medium text-ink-charcoal transition hover:bg-surface-soft"
                        >
                          Add report
                        </button>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                      {[
                        ['Documents', neo4jCounts.document_count],
                        ['Chunks', neo4jCounts.chunk_count],
                        ['Entities', neo4jCounts.entity_count],
                        ['Relations', neo4jCounts.relation_count],
                        ['Mentions', neo4jCounts.mention_count],
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-lg border border-hairline bg-white p-3">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">{label}</div>
                          <div className="mt-1 text-xl font-semibold text-ink">{typeof value === 'number' ? value : '-'}</div>
                        </div>
                      ))}
                    </div>

                    {selectedNeo4jSync && (
                      <div className="mt-3 rounded-lg border border-hairline bg-white px-3 py-2 text-sm text-ink-charcoal">
                        Current report sync: {selectedNeo4jSync.synced ? 'synced' : selectedNeo4jSync.reason || 'not synced'}
                        {selectedNeo4jSync.synced && (
                          <>
                            {' '}· {selectedNeo4jSync.chunks_synced || 0} chunks
                            {' '}· {selectedNeo4jSync.entities_synced || 0} entities
                            {' '}· {selectedNeo4jSync.relations_synced || 0} relations
                          </>
                        )}
                      </div>
                    )}
                    </div>
                  )}

                  <div className="mb-6">
                    <div className="flex flex-col gap-3 border-b border-hairline pb-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <h4 className="text-base font-semibold text-ink">Graph explorer</h4>
                        <p className="mt-1 text-sm text-ink-steel">
                          Open this only when you need node-level evidence.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setIsDocumentGraphOpen(prev => !prev)}
                        className="inline-flex items-center justify-center rounded-full border border-hairline bg-white px-4 py-2 text-sm font-semibold text-ink-charcoal transition hover:border-ink hover:text-ink"
                      >
                        {isDocumentGraphOpen ? 'Hide graph' : 'Show graph'}
                      </button>
                    </div>
                    {isDocumentGraphOpen && (
                      <div className="mt-4 space-y-4">
                        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr),360px]">
                          <div className="min-w-0 space-y-4">
                            <div className="grid gap-3 lg:grid-cols-3">
                              <div className="cg-tool-panel-soft p-4">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Focused graph</div>
                                <div className="mt-2 text-base font-semibold text-ink">{graphViewTitle}</div>
                                <p className="mt-1 text-sm text-ink-steel">
                                  {neo4jGraphState === 'ready'
                                    ? 'Rendered from the Neo4j subgraph for the current report.'
                                    : 'Rendered from the local extracted graph for this report.'}
                                </p>
                              </div>
                              <div className="cg-tool-panel-soft p-4">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Domain mix</div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {graphDomainBreakdown.length > 0 ? graphDomainBreakdown.map(([domain, count]) => (
                                    <span key={domain} className="rounded-full border border-hairline bg-white px-3 py-1 text-sm text-ink-charcoal">
                                      {GRAPH_DOMAIN_LABELS[domain] || domain}: {count}
                                    </span>
                                  )) : (
                                    <span className="text-sm text-ink-steel">No domain metadata available.</span>
                                  )}
                                </div>
                              </div>
                              <div className="cg-tool-panel-soft p-4">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Top connected</div>
                                <div className="mt-3 space-y-2">
                                  {graphTopNodes.slice(0, 3).map(node => (
                                    <button
                                      key={node.id}
                                      onClick={() => {
                                        setSelectedGraphNodeId(node.id);
                                        setSelectedGraphEdgeId(null);
                                      }}
                                      className="flex w-full items-center justify-between rounded-lg border border-hairline bg-white px-3 py-2 text-left text-sm text-ink-charcoal transition hover:border-hairline hover:bg-surface"
                                    >
                                      <span className="truncate pr-3">{node.label}</span>
                                      <span className="shrink-0 text-xs text-ink-stone">{node.degree} links</span>
                                    </button>
                                  ))}
                                </div>
                              </div>
                            </div>

                            <div className="cg-tool-panel p-4">
                              <div className="mb-3 flex items-center justify-between">
                                <div>
                                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Detail graph</div>
                                  <div className="mt-1 text-base font-semibold text-ink">{graphViewTitle}</div>
                                </div>
                                <div className="text-right">
                                  <div className="text-xs font-medium uppercase tracking-[0.14em] text-ink-stone">
                                    {neo4jGraphState === 'ready' ? 'Neo4j' : 'Local'}
                                  </div>
                                  <div className="mt-1 text-sm text-ink-steel">
                                    {neo4jGraphState === 'ready'
                                      ? 'Focused subgraph from the current report'
                                      : neo4jGraphState === 'loading'
                                        ? 'Loading Neo4j subgraph...'
                                        : 'Local graph fallback'}
                                  </div>
                                </div>
                              </div>

                              {neo4jGraphState === 'loading' ? (
                                <div className="flex h-[420px] items-center justify-center rounded-xl border border-hairline bg-surface-soft text-ink-steel">
                                  <Loader2 className="mr-3 h-5 w-5 animate-spin" />
                                  Loading focused graph view...
                                </div>
                              ) : displayedGraph ? (
                                displayedGraph.nodes.length > 0 ? (
		                              <GraphVisualizer
                                  graph={displayedGraph}
                                  height={520}
                                  focusNodeId={selectedGraphNodeId || graphFocusNodeId}
                                  selectedNodeId={selectedGraphNodeId}
                                  selectedEdgeId={selectedGraphEdgeId}
                                  highlightPath={highlightPath}
                                  onNodeSelect={(node: GraphNode) => {
                                    setSelectedGraphNodeId(node.id);
                                    setSelectedGraphEdgeId(null);
                                    setHighlightPath(null);
                                  }}
                                  onEdgeSelect={(edge: GraphEdge) => {
                                    setSelectedGraphEdgeId(getGraphEdgeId(edge));
                                    setSelectedGraphNodeId(null);
                                    setHighlightPath(null);
                                  }}
                                />
                                ) : (
                                  <div className="cg-empty-state py-12 text-center text-ink-steel">
                                    <Database className="mx-auto mb-3 h-12 w-12 text-ink-faint" />
                                    <p className="text-lg font-medium">No graph data available</p>
                                    <p className="text-sm">This report does not have enough connected entities to render a graph.</p>
                                  </div>
                                )
                              ) : (
		                              <div className="cg-empty-state py-12 text-center text-ink-steel">
                                  <Database className="mx-auto mb-3 h-12 w-12 text-ink-faint" />
                                  <p className="text-lg font-medium">No graph data available</p>
                                  <p className="text-sm">This document does not have a graph visualization yet.</p>
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="cg-tool-panel-soft p-4">
                            <div className="mb-4 flex items-center justify-between">
                              <div>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Inspector</div>
                                <div className="mt-1 text-base font-semibold text-ink">
                                  {selectedGraphEdge ? 'Relationship detail' : selectedGraphNode ? 'Entity detail' : 'Graph detail'}
                                </div>
                              </div>
                              <button
                                onClick={() => {
                                  setSelectedGraphEdgeId(null);
                                  setSelectedGraphNodeId(graphFocusNodeId);
                                }}
                                className="rounded-lg border border-hairline bg-white px-3 py-1.5 text-xs font-medium text-ink-charcoal transition hover:bg-surface-soft"
                              >
                                Reset
                              </button>
                            </div>

                            {selectedGraphEdge ? (
                              <div className="space-y-3">
                                <div className="rounded-xl border border-hairline bg-white p-4">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Relationship</div>
                                  <div className="mt-2 text-base font-semibold text-ink">
                                    {formatGraphLabel(selectedGraphEdge.relationship_type)}
                                  </div>
                                  <div className="mt-3 grid gap-3">
                                    <div className="rounded-lg border border-hairline bg-surface p-3">
                                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Source node</div>
                                      <div className="mt-1 text-sm font-semibold text-ink">
                                        {displayedGraph?.nodes.find((node: GraphNode) => node.id === selectedGraphEdge.source)?.label || selectedGraphEdge.source}
                                      </div>
                                    </div>
                                    <div className="rounded-lg border border-hairline bg-white p-3">
                                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Relationship detail</div>
                                      <div className="mt-1 text-sm text-ink-charcoal">
                                        Confidence {(selectedGraphEdge.confidence * 100).toFixed(0)}%
                                      </div>
                                      <p className="mt-2 text-sm leading-6 text-ink-charcoal">
                                        {selectedGraphEdge.evidence || 'No evidence snippet available for this edge.'}
                                      </p>
                                    </div>
                                    <div className="rounded-lg border border-hairline bg-surface p-3">
                                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-steel">Target node</div>
                                      <div className="mt-1 text-sm font-semibold text-ink">
                                        {displayedGraph?.nodes.find((node: GraphNode) => node.id === selectedGraphEdge.target)?.label || selectedGraphEdge.target}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            ) : selectedGraphNode ? (
                              <div className="space-y-3">
                                <div className="rounded-xl border border-hairline bg-white p-4">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Entity</div>
                                  <div className="mt-2 text-base font-semibold text-ink">{selectedGraphNode.label}</div>
                                  <div className="mt-2 text-sm text-ink-charcoal">
                                    {formatGraphLabel(selectedGraphNode.type)} · {GRAPH_DOMAIN_LABELS[normalizeGraphDomain(selectedGraphNode.domain)] || selectedGraphNode.domain}
                                  </div>
                                  {selectedGraphNode.description && (
                                    <p className="mt-3 text-sm leading-6 text-ink-charcoal">{selectedGraphNode.description}</p>
                                  )}
                                </div>
                                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                                  <div className="rounded-xl border border-hairline bg-white p-3">
                                    <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Connections</div>
                                    <div className="mt-2 text-base font-semibold text-ink">
                                      {graphDegreeMap.get(selectedGraphNode.id) || 0}
                                    </div>
                                  </div>
                                  <div className="rounded-xl border border-hairline bg-white p-3">
                                    <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Confidence</div>
                                    <div className="mt-2 text-base font-semibold text-ink">
                                      {(selectedGraphNode.confidence * 100).toFixed(0)}%
                                    </div>
                                  </div>
                                  {(selectedGraphNode.company || selectedGraphNode.year) && (
                                    <div className="rounded-xl border border-hairline bg-white p-3 sm:col-span-2 xl:col-span-1">
                                      <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Context</div>
                                      <div className="mt-2 text-sm text-ink-charcoal">
                                        {[selectedGraphNode.company, selectedGraphNode.year].filter(Boolean).join(' · ')}
                                      </div>
                                    </div>
                                  )}
                                </div>
                                <div className="rounded-xl border border-hairline bg-white p-3">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Connected relationships</div>
                                  <div className="mt-2 space-y-2">
                                    {displayedGraph?.edges
                                      .filter((edge: GraphEdge) => edge.source === selectedGraphNode.id || edge.target === selectedGraphNode.id)
                                      .slice(0, 4)
                                      .map((edge: GraphEdge) => (
                                        <button
                                          key={getGraphEdgeId(edge)}
                                          onClick={() => {
                                            setSelectedGraphEdgeId(getGraphEdgeId(edge));
                                            setSelectedGraphNodeId(null);
                                          }}
                                          className="flex w-full items-center justify-between rounded-lg border border-hairline bg-surface px-3 py-2 text-left text-sm text-ink-charcoal transition hover:border-hairline hover:bg-white"
                                        >
                                          <span className="truncate pr-3">{formatGraphLabel(edge.relationship_type)}</span>
                                          <span className="shrink-0 text-xs text-ink-stone">
                                            {(edge.confidence * 100).toFixed(0)}%
                                          </span>
                                        </button>
                                      ))}
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <div className="space-y-3">
                                <div className="rounded-xl border border-hairline bg-white p-4">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Current focus</div>
                                  <div className="mt-2 text-base font-semibold text-ink">
                                    {displayedGraph?.nodes.find((node: GraphNode) => node.id === graphFocusNodeId)?.label || 'No focus entity'}
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-ink-charcoal">
                                    Select a node or edge to inspect its meaning, type, and evidence in the current drill-down.
                                  </p>
                                </div>
                                <div className="rounded-xl border border-hairline bg-white p-4">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-steel">Reading hint</div>
                                  <p className="mt-2 text-sm leading-6 text-ink-charcoal">
                                    Select a node or edge in the graph to inspect its context, evidence, and connected relationships here.
                                  </p>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="mb-4 flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
	                      <h4 className="text-lg font-medium text-ink">Key relationships</h4>
	                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                        <div className="relative">
                          <input
                            ref={searchInputRef}
                            type="text"
                            placeholder="Search relationships"
                            value={searchTerm}
                            className="w-full rounded-lg border border-hairline bg-white px-3 py-2 pr-8 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-hairline sm:w-64"
                            onChange={(e) => setSearchTerm(e.target.value)}
                          />
                          {searchTerm && (
                            <button
                              onClick={() => setSearchTerm('')}
                              className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-stone hover:text-ink-charcoal"
                            >
                              ×
                            </button>
                          )}
                        </div>
                        <select
                          value={filterType}
                          onChange={(e) => setFilterType(e.target.value)}
                          className="w-full rounded-lg border border-hairline bg-white px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-hairline sm:w-auto"
                        >
                          <option value="">All Types</option>
                          <option value="causes">Causes</option>
                          <option value="influences">Influences</option>
                          <option value="leads_to">Leads To</option>
                          <option value="affects">Affects</option>
                          <option value="improves">Improves</option>
                          <option value="harms">Harms</option>
                        </select>
                      </div>
                    </div>
                    <div className="text-sm text-ink-steel mb-3">
                      Showing {filteredSelectedRelationships.length} of {selectedDocument.relationships?.length || 0} relationships
                    </div>
                    <div className="space-y-3">
                      {filteredSelectedRelationships.length === 0 && (
	                        <div className="cg-empty-state py-10 text-center text-ink-steel">
                          <Search className="mx-auto mb-3 h-10 w-10 text-ink-faint" />
                          <p className="text-lg font-medium">No relationships found</p>
                          <p className="text-sm">Try a broader search or clear the current filters.</p>
                        </div>
                      )}
                      {filteredSelectedRelationships.map((rel, index) => (
	                        <div key={index} className="rounded-lg border border-hairline bg-white p-4">
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                            <div className="flex-1 text-sm">
                              <span className="font-semibold text-ink">{rel.cause}</span>
                              <span className="mx-2 text-ink-stone">→</span>
                              <span className="font-semibold text-ink">{rel.effect}</span>
                            </div>
                            <div className="flex items-center gap-3 text-xs">
	                              <span className="rounded-md bg-surface-soft px-2.5 py-1 font-medium text-ink-charcoal">{rel.relationship_type}</span>
                              <span className="text-ink-steel">{(rel.confidence * 100).toFixed(0)}% confidence</span>
                            </div>
                          </div>
                          {rel.evidence && <p className="mt-3 border-l-2 border-hairline pl-3 text-sm leading-6 text-ink-charcoal">Evidence: {rel.evidence}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          )}

          </div>
        </main>

	    </div>
	  </div>
	  );
	};
export default Agent;
