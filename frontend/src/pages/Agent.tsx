import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowUp,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronsUpDown,
  Circle,
  Copy,
  Eye,
  FileText,
  FileUp,
  FolderOpen,
  GitBranch,
  Home,
  Library,
  Loader2,
  LogOut,
  MessageSquare,
  Network,
  PanelLeft,
  Paperclip,
  PenSquare,
  Search,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  X,
} from 'lucide-react';
import BrandLogo from '../components/BrandLogo';
import ModelStatus from '../components/ModelStatus';
import WorkbenchWelcome from '../components/WorkbenchWelcome';
import { ApiError, apiFetch, jsonRequest } from '../api/client';
import { apiBase } from '../api/config';
import { openEventStream, readSseEvents } from '../api/sse';
import { useAuth } from '../contexts/AuthContext';
import useDocumentTitle from '../utils/useDocumentTitle';
import { DOCUMENT_CATEGORIES, documentCategoryLabel } from '../utils/documentCategories';
import type {
  AgentTraceStep,
  ChatSessionDetailResponse,
  ChatSessionListResponse,
  ChatSessionResponse,
  DocumentDetailResponse,
  DocumentListResponse,
  DocumentSummary,
  FeedbackPayload,
  FeedbackRating,
  FeedbackReasonTag,
  RagReasoningMode,
  RagResponse,
  RagSource,
  UploadJobCreatedResponse,
  UploadJobResponse,
} from '../types/api';
import {
  STORAGE_KEYS,
  buildChatMessage,
  deriveSessionTitle,
  formatRelativeTime,
  toSessionSummary,
  type ChatMessage,
  type ChatSession,
} from './agent/chatSession';
import { formatAccountPlanLabel } from './agent/accountPlan';
import {
  formatSourceDocumentTitle,
  getLoadingSteps,
  linkCitations,
  normalizeMathForMarkdown,
  normalizeStreamingMarkdown,
} from './agent/ragUi';
import {
  formatAgentPartialDescription,
  formatAgentPartialLabel,
  formatAgentStageLabel,
  formatAgentTraceSummary,
  mergeAgentTraceSteps,
} from './agent/agentTraceUi';

type Document = DocumentSummary;

const QUERY_TOKEN_PATTERN = /[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}/g;
const QUERY_STOP_WORDS = new Set([
  'about', 'against', 'company', 'document', 'does', 'doing', 'for', 'from', 'have',
]);

const CONTEXTUAL_QUERY_PATTERN =
  /^(it|its|they|them|their|this|that|these|those|what about|how about|and|also|then|why|how|when|where)\b/i;

const DOCUMENT_REFERENCE_PATTERN =
  /\b(this (?:contract|agreement|report|document|company)|the (?:contract|agreement|report|document|company))\b|这份合同|该合同|本合同|这份协议|这份报告|这个报告|该报告|这个文件/iu;

const CHAT_AUTO_SCROLL_THRESHOLD_PX = 120;
const STREAM_RENDER_INTERVAL_MS = 80;

const normalizeQueryToken = (value: string) => value.trim().toLowerCase();

const extractQueryTokens = (value: string): string[] => {
  const matches = value.match(QUERY_TOKEN_PATTERN) || [];
  return matches
    .map(normalizeQueryToken)
    .filter(token => token.length >= 2 && !QUERY_STOP_WORDS.has(token));
};

const getDocumentCompanyTerms = (doc: Document): Set<string> => new Set(extractQueryTokens(doc.title || ''));

const formatDocumentDate = (value?: string) => {
  const date = new Date(value || '');
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleDateString() : '—';
};

const shouldPreferSelectedDocument = (query: string, selectedDocument: Document | null, documents: Document[]) => {
  if (!selectedDocument) return false;

  const trimmed = query.trim();
  if (!trimmed) return false;
  if (CONTEXTUAL_QUERY_PATTERN.test(trimmed) || trimmed.endsWith('呢') || DOCUMENT_REFERENCE_PATTERN.test(trimmed)) {
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

// The chat endpoints answer 503 with error "chat_memory_unavailable" when chat
// memory is switched off; the desk then works without saved sessions.
const isChatMemoryUnavailableResponse = (error: unknown) =>
  error instanceof ApiError &&
  error.status === 503 &&
  (error.code === 'chat_memory_unavailable' || error.message.toLowerCase().includes('chat memory is unavailable'));

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
        phase: typeof raw.phase === 'string' ? raw.phase : undefined,
        plan_step: typeof raw.plan_step === 'number' ? raw.plan_step : undefined,
        plan: Array.isArray(raw.plan) ? raw.plan as Record<string, unknown>[] : undefined,
        reflexion: raw.reflexion && typeof raw.reflexion === 'object' ? raw.reflexion as Record<string, unknown> : undefined,
        meta: raw.meta && typeof raw.meta === 'object' ? raw.meta as Record<string, unknown> : undefined,
      };
    });
};

const getTracePhaseCounts = (steps: AgentTraceStep[]) => {
  const uniqueSteps = new Set<string>();
  steps.forEach(step => {
    uniqueSteps.add(`${step.plan_step || step.step}-${step.phase || step.stage || step.tool || 'event'}`);
  });
  return uniqueSteps.size;
};

const formatSourceDocumentLabel = (source: RagSource): string => (
  formatSourceDocumentTitle(source)
);

const AnswerWarningBadge: React.FC<{
  partial?: boolean;
  partialReason?: string | null;
}> = ({ partial, partialReason }) => {
  if (!partial) return null;
  return (
    <span
      className="tag border-warn-line bg-warn-bg text-warn"
      title={formatAgentPartialDescription(partialReason)}
    >
      <AlertCircle className="h-3.5 w-3.5" />
      {formatAgentPartialLabel(partialReason)}
    </span>
  );
};

type AgentDrawerTab = 'process' | 'files';

const getTraceStatus = (step: AgentTraceStep) => String(step.status || '').toLowerCase();

const getTraceMetaValue = (step: AgentTraceStep, key: string): string => {
  const value = step.meta?.[key];
  return value === undefined || value === null ? '' : String(value).trim();
};

const formatTraceDuration = (step: AgentTraceStep) => {
  if (typeof step.elapsed_ms !== 'number' || step.elapsed_ms <= 0) return '';
  const seconds = step.elapsed_ms / 1000;
  return `${seconds >= 10 ? seconds.toFixed(0) : seconds.toFixed(2)}s`;
};

// Short, human phrasing for each trace step: present tense while it runs,
// past tense once it is done.
const describeStep = (step: AgentTraceStep, running: string, done: string, failed?: string) => {
  const status = getTraceStatus(step);
  if (status === 'running') return running;
  if (status === 'failed') return failed || `${running} failed`;
  if (status === 'planned' || status === 'pending') return `Queued: ${running.charAt(0).toLowerCase()}${running.slice(1)}`;
  return done;
};

const formatTraceEventTitle = (step: AgentTraceStep) => {
  const phase = String(step.phase || '').toLowerCase();
  const stage = String(step.stage || '').toLowerCase();
  const tool = String(step.tool || '').trim();
  const expectedEntity = getTraceMetaValue(step, 'expected_entity');

  if (stage === 'routing') return describeStep(step, 'Reading the question', 'Read the question');
  if (stage === 'context_ready') return describeStep(step, 'Gathering passages', 'Gathered passages');
  if (stage === 'planning') return describeStep(step, 'Planning the search', 'Planned the search');
  if (stage === 'generating') return describeStep(step, 'Writing the answer', 'Wrote the answer');

  if (phase === 'plan') return 'Planned the search';
  if (phase === 'thought' && tool === 'search_documents' && expectedEntity) return `Decided to search for ${expectedEntity}`;
  if (phase === 'thought' && tool === 'search_documents') return 'Decided to search the documents';
  if (phase === 'thought' && (tool === 'get_graph_context' || tool === 'query_neo4j')) return 'Decided to check the graph';
  if (phase === 'thought' && tool === 'summarize_evidence') return 'Decided to summarise the evidence';
  if (phase === 'thought') return 'Chose the next step';

  if (tool === 'search_documents') return describeStep(step, 'Searching the documents', 'Searched the documents', 'Document search failed');
  if (tool === 'read_chunks') return describeStep(step, 'Reading passages', 'Read passages', 'Reading passages failed');
  if (tool === 'get_graph_context' || tool === 'query_neo4j') return describeStep(step, 'Checking the graph', 'Checked the graph', 'Graph check failed');
  if (tool === 'summarize_evidence') return describeStep(step, 'Summarising the evidence', 'Summarised the evidence');
  if (phase === 'reflexion') return 'Checked the evidence covers the question';
  if (phase === 'replan') return 'Searched again for missing evidence';
  if (phase === 'observation') return 'Noted what was found';
  if (phase === 'final') return 'Finished the answer';
  return formatAgentStageLabel(step);
};

const getTraceEventIcon = (step: AgentTraceStep) => {
  const phase = String(step.phase || '').toLowerCase();
  const tool = String(step.tool || '').trim();
  if (tool === 'search_documents') return Search;
  if (tool === 'read_chunks') return FileText;
  if (tool === 'get_graph_context' || tool === 'query_neo4j') return Network;
  if (tool === 'summarize_evidence' || phase === 'final') return CheckCircle2;
  if (phase === 'replan') return GitBranch;
  if (phase === 'observation') return Eye;
  if (phase === 'reflexion') return ShieldCheck;
  if (phase === 'plan' || phase === 'thought') return BrainCircuit;
  return Circle;
};

const getVisibleTraceSteps = (steps: AgentTraceStep[], limit = 12) => {
  const seen = new Set<string>();
  return steps
    .filter(step => {
      const key = `${step.step}|${step.phase || ''}|${step.tool || ''}|${step.status || ''}|${step.summary || ''}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(-limit);
};

const getGraphEdgeCount = (graphSources: unknown): number => {
  if (!graphSources || typeof graphSources !== 'object') return 0;
  const edges = (graphSources as { edges?: unknown }).edges;
  return Array.isArray(edges) ? edges.length : 0;
};

const getRoutingStrategy = (payload: Partial<RagResponse> & { routing?: Record<string, unknown> }) => (
  String(payload.retrieval_strategy || payload.routing?.strategy || '').trim()
);

const buildPipelineTraceStep = (
  payload: Partial<RagResponse> & { stream_stage?: string; routing?: Record<string, unknown> },
  stepNumber: number,
): AgentTraceStep | null => {
  const stage = String(payload.stream_stage || '').trim();
  if (!stage || stage === 'agent_trace') return null;

  const sources = Array.isArray(payload.sources) ? payload.sources.length : 0;
  const graphEdges = getGraphEdgeCount(payload.graph_sources);
  const strategy = getRoutingStrategy(payload);
  const subQueries = Array.isArray(payload.sub_queries) ? payload.sub_queries.length : 0;
  const rewrittenQuery = String(payload.rewritten_query || '').trim();
  const routingReason = String(payload.routing?.reason || '').trim();

  if (stage === 'routing') {
    return {
      step: stepNumber,
      stage: 'routing',
      tool: null,
      status: 'completed',
      summary: routingReason || 'Classified the question and selected the retrieval path.',
      phase: 'routing',
      meta: {
        strategy,
        answer_mode: String((payload as { answer_mode?: string }).answer_mode || ''),
      },
    };
  }

  if (stage === 'context_ready') {
    const detail = [
      `${sources} passage${sources === 1 ? '' : 's'}`,
      graphEdges ? `${graphEdges} graph relationship${graphEdges === 1 ? '' : 's'}` : '',
      strategy ? `${strategy} retrieval` : '',
      subQueries > 1 ? `${subQueries} sub-queries` : '',
    ].filter(Boolean).join(', ');
    return {
      step: stepNumber,
      stage: 'context_ready',
      tool: null,
      status: 'completed',
      summary: detail ? `Prepared context from ${detail}.` : 'Prepared the retrieved passages.',
      phase: 'context_ready',
      meta: {
        strategy,
        rewritten_query: rewrittenQuery,
        sub_queries: subQueries,
      },
    };
  }

  if (stage === 'planning') {
    return {
      step: stepNumber,
      stage: 'planning',
      tool: null,
      status: 'completed',
      summary: 'Routing selected the reflexion agent path and started the evidence plan.',
      phase: 'planning',
      meta: {
        agent_path: payload.agent_path || payload.path || 'agent',
        reasoning_mode: payload.reasoning_mode || '',
      },
    };
  }

  if (stage === 'generating') {
    return {
      step: stepNumber,
      stage: 'generating',
      tool: null,
      status: 'running',
      summary: 'Writing the answer from the retrieved passages.',
      phase: 'generating',
    };
  }

  return {
    step: stepNumber,
    stage,
    tool: null,
    status: 'completed',
    summary: formatAgentStageLabel({ step: stepNumber, stage, status: 'completed', summary: '' }),
    phase: stage,
  };
};

const TraceEvents: React.FC<{
  steps: AgentTraceStep[];
  compact?: boolean;
}> = ({ steps, compact = false }) => {
  const visibleSteps = getVisibleTraceSteps(steps, compact ? 6 : 16);
  if (visibleSteps.length === 0) return null;

  return (
    <ol className={compact ? 'space-y-1.5' : ''}>
      {visibleSteps.map((step, traceIndex) => {
        const status = getTraceStatus(step);
        const running = status === 'running';
        const failed = status === 'failed';
        const Icon = running ? Loader2 : failed ? AlertCircle : getTraceEventIcon(step);
        const summary = formatAgentTraceSummary(step);
        const duration = formatTraceDuration(step);
        const title = formatTraceEventTitle(step);
        const key = `${step.step}-${traceIndex}-${title}`;

        if (compact) {
          return (
            <li key={key} className="flex min-w-0 items-center gap-2 text-[13px] text-ink-3">
              <Icon className={`h-3.5 w-3.5 shrink-0 ${running ? 'animate-spin text-ink' : failed ? 'text-err' : 'text-ink-5'}`} />
              <span className="truncate">{title}</span>
              {duration && <span className="shrink-0 font-mono text-[11px] text-ink-5">{duration}</span>}
            </li>
          );
        }

        const isLast = traceIndex === visibleSteps.length - 1;
        return (
          <li key={key} className="relative flex gap-3 pb-5 last:pb-0">
            {!isLast && <span aria-hidden="true" className="absolute bottom-0 left-[11px] top-7 w-px bg-line" />}
            <span
              className={`relative mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-white ${
                failed ? 'border-err-line text-err' : running ? 'border-ink-4 text-ink' : 'border-line text-ink-4'
              }`}
            >
              <Icon className={`h-3 w-3 ${running ? 'animate-spin' : ''}`} />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex min-w-0 items-baseline gap-2">
                <span className="truncate text-[13px] font-medium text-ink-2">{title}</span>
                {duration && <span className="shrink-0 font-mono text-[11px] text-ink-4">{duration}</span>}
              </div>
              {summary && <p className="mt-0.5 line-clamp-2 text-[13px] leading-5 text-ink-3">{summary}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
};

type NumberedSource = { source: RagSource; n: number };

// Group cited passages by document while keeping the answer's citation numbers.
const groupSourcesByDocument = (sources: RagSource[]) => {
  const groups = new Map<string, { key: string; title: string; items: NumberedSource[] }>();
  sources.forEach((source, index) => {
    const title = formatSourceDocumentLabel(source);
    const key = String(source.document_id || source.document_title || title || index);
    const item = { source, n: index + 1 };
    const existing = groups.get(key);
    if (existing) {
      existing.items.push(item);
      return;
    }
    groups.set(key, { key, title, items: [item] });
  });
  return Array.from(groups.values());
};

const SourceStrip: React.FC<{
  sources: RagSource[];
  onOpen: (sourceNumber?: number) => void;
}> = ({ sources, onOpen }) => {
  if (!sources.length) return null;
  const shown = sources.slice(0, 4);
  return (
    <div className="mt-5">
      <div className="section-label mb-2">Sources</div>
      <div className="cg-scroll -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {shown.map((source, index) => (
          <button
            key={`${source.chunk_id || 'source'}-${index}`}
            type="button"
            onClick={() => onOpen(index + 1)}
            className="w-[200px] shrink-0 rounded-lg border border-line bg-white px-3 py-2 text-left transition-colors hover:border-line-strong hover:bg-paper-sunken"
          >
            <span className="flex min-w-0 items-center gap-1.5 font-mono text-[11px] text-ink-4">
              <span className="text-ink-2">{index + 1}</span>
              <span className="truncate">{source.chunk_id || 'passage'}</span>
            </span>
            <span className="mt-0.5 line-clamp-2 block text-[13px] leading-snug text-ink-2">
              {formatSourceDocumentLabel(source)}
            </span>
          </button>
        ))}
        {sources.length > shown.length && (
          <button
            type="button"
            onClick={() => onOpen()}
            className="shrink-0 rounded-lg border border-dashed border-line-strong px-3 text-[13px] text-ink-3 transition-colors hover:border-ink-5 hover:text-ink"
          >
            All {sources.length} sources
          </button>
        )}
      </div>
    </div>
  );
};

const AgentWorkspaceDrawer: React.FC<{
  open: boolean;
  tab: AgentDrawerTab;
  onTabChange: (tab: AgentDrawerTab) => void;
  onClose: () => void;
  steps: AgentTraceStep[];
  sources: RagSource[];
  isLoading: boolean;
  currentLoadingStep: string;
  highlightedSource: number | null;
}> = ({ open, tab, onTabChange, onClose, steps, sources, isLoading, currentLoadingStep, highlightedSource }) => {
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open || tab !== 'files' || !highlightedSource) return;
    const target = bodyRef.current?.querySelector(`[data-source-number="${highlightedSource}"]`);
    target?.scrollIntoView({ block: 'nearest' });
  }, [open, tab, highlightedSource, sources]);

  if (!open) return null;
  const currentStep = [...steps].reverse().find(step => getTraceStatus(step) === 'running') || [...steps].reverse()[0];
  const fileGroups = groupSourcesByDocument(sources);
  const stepCount = getTracePhaseCounts(steps);

  return (
    <>
      <button
        type="button"
        aria-label="Close process drawer"
        className="fixed inset-0 z-30 bg-ink/10 xl:hidden"
        onClick={onClose}
      />
      <aside className="fixed inset-y-0 right-0 z-40 flex w-[min(92vw,400px)] min-h-0 shrink-0 flex-col border-l border-line bg-paper shadow-lg xl:static xl:z-auto xl:w-[400px] xl:shadow-none">
        <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-line px-3">
          <div className="segmented" role="tablist" aria-label="Answer details">
            {([
              ['process', 'Process'],
              ['files', sources.length ? `Sources · ${sources.length}` : 'Sources'],
            ] as const).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => onTabChange(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <button type="button" onClick={onClose} className="icon-btn" aria-label="Close process drawer" title="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div ref={bodyRef} className="cg-scroll min-h-0 flex-1 overflow-y-auto px-4 py-5">
          {tab === 'process' ? (
            <>
              <div className="flex items-center gap-2.5">
                {isLoading ? (
                  <span className="cg-working" aria-hidden="true" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" />
                )}
                <span className="min-w-0 truncate text-sm font-medium text-ink">
                  {isLoading ? (currentStep ? formatTraceEventTitle(currentStep) : currentLoadingStep) : 'Finished'}
                </span>
                {stepCount > 0 && <span className="ml-auto shrink-0 text-xs text-ink-4">{stepCount} steps</span>}
              </div>

              <div className="mt-5">
                {steps.length > 0 ? (
                  <TraceEvents steps={steps} />
                ) : (
                  <p className="text-sm text-ink-4">Searching, reading and checking steps will appear here.</p>
                )}
              </div>

              {fileGroups.length > 0 && (
                <div className="mt-6 border-t border-line pt-4">
                  <div className="section-label mb-2">Documents used</div>
                  <ul className="space-y-2">
                    {fileGroups.map(group => (
                      <li key={group.key}>
                        <button
                          type="button"
                          onClick={() => onTabChange('files')}
                          className="flex w-full min-w-0 items-baseline justify-between gap-3 text-left text-[13px] hover:text-ink"
                        >
                          <span className="truncate text-ink-2">{group.title}</span>
                          <span className="shrink-0 font-mono text-[11px] text-ink-4">
                            {group.items.length} {group.items.length === 1 ? 'passage' : 'passages'}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : sources.length === 0 ? (
            <p className="text-sm text-ink-4">No sources cited yet.</p>
          ) : (
            <div className="space-y-6">
              {fileGroups.map(group => (
                <section key={group.key}>
                  <h3 className="flex items-start gap-2 text-[13px] font-medium leading-5 text-ink">
                    <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-4" />
                    <span>{group.title}</span>
                  </h3>
                  <ol className="mt-2 space-y-2">
                    {group.items.map(({ source, n }) => (
                      <li
                        key={`${group.key}-${source.chunk_id || n}`}
                        data-source-number={n}
                        className={`rounded-lg border bg-white px-3 py-2.5 transition-colors ${
                          highlightedSource === n ? 'border-ink-4' : 'border-line'
                        }`}
                      >
                        <div className="flex min-w-0 items-center gap-2 font-mono text-[11px] text-ink-4">
                          <span className="text-ink-2">{n}</span>
                          <span className="truncate">{source.chunk_id || 'passage'}</span>
                        </div>
                        {source.text && (
                          <p className="mt-1.5 line-clamp-6 text-[13px] leading-5 text-ink-2">{source.text}</p>
                        )}
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
};

const REMARK_PLUGINS = [remarkGfm, remarkMath];
const REHYPE_PLUGINS: NonNullable<React.ComponentProps<typeof ReactMarkdown>['rehypePlugins']> = [
  [rehypeKatex, { throwOnError: false, strict: 'ignore' }],
];

// Citation clicks are routed through context so the markdown components stay
// the same between renders; a new component type would remount every link.
const CitationContext = React.createContext<(sourceNumber: number) => void>(() => undefined);

type AnswerLinkProps = React.ComponentPropsWithoutRef<'a'> & { node?: unknown };

// Answer markdown links: citations become buttons that open the cited passage,
// web links open in a new tab, in-page links (such as footnotes) stay in place.
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- `node` is react-markdown's AST node; it must not reach the <a>
const AnswerLink = ({ href, children, node, ...rest }: AnswerLinkProps) => {
  const openCitation = React.useContext(CitationContext);
  const citation = /^#cite-(\d+)$/.exec(href || '');
  if (citation) {
    const sourceNumber = Number(citation[1]);
    return (
      <button type="button" className="cg-cite" onClick={() => openCitation(sourceNumber)} aria-label={`Source ${sourceNumber}`}>
        {children}
      </button>
    );
  }
  const external = /^https?:\/\//i.test(href || '');
  return (
    <a href={href} {...(external ? { target: '_blank', rel: 'noreferrer noopener' } : {})} {...rest}>
      {children}
    </a>
  );
};

const ANSWER_COMPONENTS: Components = { a: AnswerLink };

// On narrow screens the process drawer covers the conversation, so it only
// opens on its own where there is room to show it beside the answer.
const drawerFitsBesideConversation = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(min-width: 1280px)').matches
    : true;

const Agent: React.FC = () => {
  const { isAuthenticated, token, user, logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const isAdmin = (user?.role || '').toLowerCase() === 'admin';
  const accountPlanLabel = formatAccountPlanLabel(user);
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
  const [pipelineTrace, setPipelineTrace] = useState<AgentTraceStep[]>([]);
  const [agentTrace, setAgentTrace] = useState<AgentTraceStep[]>([]);
  const [agentDrawerOpen, setAgentDrawerOpen] = useState(drawerFitsBesideConversation);
  const [agentDrawerTab, setAgentDrawerTab] = useState<AgentDrawerTab>('process');
  const [agentDrawerSourcesOverride, setAgentDrawerSourcesOverride] = useState<RagSource[] | null>(null);
  const [highlightedSource, setHighlightedSource] = useState<number | null>(null);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [copiedMessageKey, setCopiedMessageKey] = useState<string | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement>(null);
  // Id of a session created for a first question whose answer is still streaming.
  const pendingFirstTurnSessionIdRef = useRef('');
  // Fast disables thinking; Deep enables reasoning with layered retrieval and
  // graph context on the configured provider. URL accepts ?tier=deep; legacy
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
  const [activeTab, setActiveTab] = useState('chat');
  const [isSearchPaletteOpen, setIsSearchPaletteOpen] = useState(false);
  const [taskSearchTerm, setTaskSearchTerm] = useState('');
  const taskSearchInputRef = useRef<HTMLInputElement>(null);
  const uploadStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conversationScrollRef = useRef<HTMLDivElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const hasAppliedInitialPromptRef = useRef(false);
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
    if (activeTab !== 'chat') return;
    if (conversation.length === 0) {
      const frameId = window.requestAnimationFrame(() => {
        conversationScrollRef.current?.scrollTo({ top: 0 });
        shouldAutoFollowConversationRef.current = true;
      });
      return () => window.cancelAnimationFrame(frameId);
    }
    if (!shouldAutoFollowConversationRef.current) return;
    const frameId = window.requestAnimationFrame(() => scrollToBottom('auto'));
    return () => window.cancelAnimationFrame(frameId);
  }, [activeTab, conversation.length, scrollToBottom]);
  useEffect(() => {
    if (hasAppliedInitialPromptRef.current) return;

    const prompt = (searchParams.get('prompt') || '').trim();
    if (!prompt) return;

    hasAppliedInitialPromptRef.current = true;
    setInputText(prompt.slice(0, 2000));
    setActiveTab('chat');

    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.delete('prompt');
    setSearchParams(nextParams, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!isSearchPaletteOpen) return;
    const frameId = window.requestAnimationFrame(() => {
      taskSearchInputRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [isSearchPaletteOpen]);
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if ((e.metaKey || e.ctrlKey) && key === 'k') {
        e.preventDefault();
        setIsSearchPaletteOpen(true);
        return;
      }
      if (e.key === 'Escape' && isSearchPaletteOpen) {
        e.preventDefault();
        setIsSearchPaletteOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isSearchPaletteOpen]);

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
    const payload = await apiFetch<DocumentDetailResponse>(`/documents/${encodeURIComponent(documentId)}`);
    return payload.document;
  }, []);

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
      const payload = await apiFetch<ChatSessionListResponse>('/chat/sessions');
      const sessions = Array.isArray(payload?.sessions) ? payload.sessions.map(toSessionSummary) : [];
      setChatSessions(sessions);
    } catch (error) {
      if (isChatMemoryUnavailableResponse(error)) {
        setChatSessions([]);
        setCurrentSessionId('');
        persistCurrentSessionId('');
        setConversation([]);
        return;
      }
      console.error('Failed to load chat sessions:', error);
      setChatSessionsError(error instanceof Error ? error.message : 'Unable to load chat sessions');
      setChatSessions([]);
    } finally {
      setIsChatSessionsLoading(false);
      setHasLoadedChatSessions(true);
    }
  }, [isAuthenticated, persistCurrentSessionId]);

  const fetchSessionDetail = useCallback(async (sessionId: string) => {
    const payload = await apiFetch<ChatSessionDetailResponse>(`/chat/sessions/${encodeURIComponent(sessionId)}`);

    const session = toSessionSummary(payload?.session || {});
    const messages = Array.isArray(payload?.messages)
      ? payload.messages
          .map((message) =>
            buildChatMessage(
              String(message?.role || '').toLowerCase() === 'user' ? 'user' : 'agent',
              String(message?.content || ''),
              message?.data as ChatMessage['data'],
              message?.timestamp,
            )
          )
          .filter((message: ChatMessage) => message.content.trim())
      : [];

    return {
      session,
      messages,
    };
  }, []);

  const createServerSession = useCallback(async (initial?: Partial<ChatSession>) => {
    const payload = await apiFetch<ChatSessionResponse>('/chat/sessions', jsonRequest('POST', {
      title: initial?.title || '',
      selected_document_id: initial?.selectedDocumentId || selectedDocument?.id || '',
      mode: initial?.mode || 'ask',
    }));
    const session = toSessionSummary(payload?.session || {});
    upsertChatSession(session);
    return session;
  }, [selectedDocument?.id, upsertChatSession]);

  const appendSessionMessage = useCallback(async (sessionId: string, message: ChatMessage) => {
    const payload = await apiFetch<ChatSessionResponse>(
      `/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
      jsonRequest('POST', {
        role: message.type === 'agent' ? 'assistant' : 'user',
        content: message.content,
        timestamp: message.timestamp.toISOString(),
        data: message.data || {},
      }),
    );
    const session = toSessionSummary(payload?.session || {});
    upsertChatSession(session);
    return session;
  }, [upsertChatSession]);

  const updateServerSession = useCallback(async (sessionId: string, update: { title?: string; selected_document_id?: string; mode?: string }) => {
    const payload = await apiFetch<ChatSessionResponse>(
      `/chat/sessions/${encodeURIComponent(sessionId)}`,
      jsonRequest('PATCH', update),
    );
    const session = toSessionSummary(payload?.session || {});
    upsertChatSession(session);
    return session;
  }, [upsertChatSession]);

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
        const payload = await apiFetch<DocumentListResponse>('/documents');
        const nextDocuments: Document[] = Array.isArray(payload?.documents) ? payload.documents : [];
        setDocuments(nextDocuments);

        const savedSelectedDocumentId = localStorage.getItem(STORAGE_KEYS.selectedDocumentId) || '';
        const initialSelected =
          nextDocuments.find(doc => doc.id === savedSelectedDocumentId) ||
          nextDocuments[0] ||
          null;
        setSelectedDocument(initialSelected);

        if (initialSelected) {
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
          persistSelectedDocumentId();
        }
      } catch (error) {
        console.error('Failed to load documents from backend:', error);
        setDocumentsError(error instanceof Error ? error.message : 'Unable to load documents');
        setDocuments([]);
        setSelectedDocument(null);
        persistSelectedDocumentId();
      } finally {
        setIsDocumentsLoading(false);
      }
    };

    void loadDocuments();
    // pendingSessionDocumentId is intentionally read inside but not in deps:
    // session-restore flow uses useEffect@918 to apply the pending id once
    // documents arrive, so document list reload should not be triggered by it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSessionId, fetchDocumentDetail, isAuthenticated, persistSelectedDocumentId, selectDocument]);

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

  const handleUpload = async () => {
    const fileToUpload = uploadedFile;
    const contentToUpload = fileContent || uploadForm.content;
    const titleToUpload = uploadForm.title.trim();

    if (!titleToUpload || (!contentToUpload && !fileToUpload)) {
      addAgentMessage("Add a title and a file or some text before indexing.", "error");
      return;
    }
    if (!isAuthenticated) {
      addAgentMessage("Sign in to upload documents.", "error");
      return;
    }
    setIsUploading(true);
    clearUploadStatusTimer();
    setUploadStatusTitle(fileToUpload?.name || titleToUpload || 'Uploaded document');
    setUploadProgress(1);
    setUploadStage('queued');
    setUploadMessage('Queued for processing');
    addAgentMessage(`Indexing “${titleToUpload}”. You can keep working while it is processed.`, "processing");
    try {
      const formData = new FormData();
      formData.append('title', titleToUpload);
      formData.append('domain', uploadForm.domain);
      formData.append('source_type', uploadForm.source_type);
      formData.append('source', uploadForm.source);
      if (fileToUpload) {
        formData.append('file', fileToUpload);
      } else {
        formData.append('content', contentToUpload);
      }

      const payload = await apiFetch<UploadJobCreatedResponse>('/documents/upload-async', {
        method: 'POST',
        body: formData,
      });
      const jobId = payload?.job_id;
      if (!jobId) {
        throw new Error('Upload job was created without a job id.');
      }

      let uploadedDocument: Document | null = null;
      let finalStats: { chunk_count?: number } | null = null;
      let isDuplicate = false;
      let duplicateMatchedBy = '';
      let lastMessage = 'Queued for processing';

      while (!uploadedDocument) {
        await new Promise(resolve => setTimeout(resolve, 1200));
        const jobPayload = await apiFetch<UploadJobResponse>(`/documents/jobs/${jobId}`);

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
      scheduleUploadStatusDismiss();
      const successMessage = isDuplicate
        ? `“${completedDocument.title}” is already in your library (matched by ${duplicateMatchedBy || 'content hash'}), so the existing copy will be used.`
        : `“${completedDocument.title}” is indexed and ready to search: ${finalStats?.chunk_count || 0} passages.`;
      addAgentMessage(successMessage, "success");
      setActiveTab('documents');
      setSelectedDocument(completedDocument);
      persistSelectedDocumentId(completedDocument.id);
    } catch (error) {
        console.error('Upload error:', error);
        const message = error instanceof Error ? error.message : 'Unknown error';
        const rejected = /rejected/i.test(message);
        clearUploadStatusTimer();
        setUploadStage('failed');
        setUploadMessage(message);
        setUploadProgress(current => Math.max(current, 100));
        addAgentMessage(
          rejected
            ? `The upload was rejected: ${message}`
            : `The upload didn’t finish: ${message}`,
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

      const response = await openEventStream('/rag/ask/stream', requestBody);

      const placeholderTimestamp = new Date();
      const placeholderMessage = buildChatMessage('agent', '', {
        mode: 'ask',
        backend: 'streaming',
        sources: [],
        messageId: createMessageId(),
      }, placeholderTimestamp);
      pushConversationMessage(placeholderMessage);

      let latestMessageData: ChatMessage['data'] = placeholderMessage.data;
      let latestFlowTrace: AgentTraceStep[] = [];
      let pendingStreamingContent = '';
      let streamingRenderTimer: number | null = null;
      let lastStreamingRenderAt = 0;
      const appendFlowStep = (
        payload: Partial<RagResponse> & { stream_stage?: string; routing?: Record<string, unknown> },
      ) => {
        const step = buildPipelineTraceStep(payload, latestFlowTrace.length + 1);
        if (!step) return latestFlowTrace;
        latestFlowTrace = [...latestFlowTrace, step];
        setPipelineTrace(latestFlowTrace);
        return latestFlowTrace;
      };
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
            const nextFlowTrace = appendFlowStep(event.payload);
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
              setAgentTrace(prev => mergeAgentTraceSteps(prev, traceSteps));
            }
            const nextData: Partial<NonNullable<ChatMessage['data']>> = {
              mode: event.payload.mode || latestMessageData?.mode || 'ask',
              flowTrace: nextFlowTrace,
            };
            if (event.payload.agent_path) {
              nextData.agentPath = event.payload.agent_path;
            }
            if (traceSteps.length > 0) {
              nextData.agentTrace = mergeAgentTraceSteps(latestMessageData?.agentTrace || [], traceSteps);
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
            const finalFlowTrace = latestFlowTrace.length > 0
              ? [
                  ...latestFlowTrace,
                  {
                    step: latestFlowTrace.length + 1,
                    stage: 'generating',
                    tool: null,
                    status: 'completed',
                    summary: 'Delivered the final answer payload with citations and timings.',
                    phase: 'final',
                    meta: {
                      backend: event.payload.backend,
                      retrieval_strategy: event.payload.retrieval_strategy,
                    },
                  },
                ]
              : latestFlowTrace;
            if (finalFlowTrace !== latestFlowTrace) {
              latestFlowTrace = finalFlowTrace;
              setPipelineTrace(finalFlowTrace);
            }
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
              flowTrace: finalFlowTrace,
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
        ? `Couldn’t finish the answer: ${error.message}`
        : `Couldn’t reach the research service at ${apiBase() || 'the configured API'}. Check that the API is running.`;
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
    setPipelineTrace([]);
    setAgentTrace([]);
    setAgentDrawerOpen(drawerFitsBesideConversation());
    setAgentDrawerTab('process');
    setAgentDrawerSourcesOverride(null);
    setHighlightedSource(null);
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

      pendingFirstTurnSessionIdRef.current = sessionIdToActivateAfterFirstTurn;
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
      pendingFirstTurnSessionIdRef.current = '';
      setIsLoading(false);
      setShowPipelineStatus(false);
    }
  };
  const handleNewSession = () => {
    setCurrentSessionId('');
    persistCurrentSessionId('');
    setConversation([]);
    setActiveAgentPath(null);
    setPipelineTrace([]);
    setAgentTrace([]);
    setAgentDrawerOpen(false);
    setAgentDrawerTab('process');
    setAgentDrawerSourcesOverride(null);
    setActiveTab('chat');
  };
  const handleSelectSession = (id: string) => {
    // Reloading the open session (or one whose first answer is still
    // streaming) would replace the live conversation, so just return to it.
    if (id === currentSessionId || (id !== '' && id === pendingFirstTurnSessionIdRef.current)) {
      setActiveTab('chat');
      return;
    }
    setCurrentSessionId(id);
    setActiveAgentPath(null);
    setPipelineTrace([]);
    setAgentTrace([]);
    setAgentDrawerOpen(drawerFitsBesideConversation());
    setAgentDrawerTab('process');
    setAgentDrawerSourcesOverride(null);
    setHighlightedSource(null);
    setActiveTab('chat');
  };
  const handleDeleteSession = async (id: string) => {
    try {
      await apiFetch(`/chat/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
      setChatSessions(prev => prev.filter(session => session.id !== id));
      if (id === currentSessionId) {
        setCurrentSessionId('');
        persistCurrentSessionId('');
        setConversation([]);
        setPipelineTrace([]);
        setAgentTrace([]);
        setAgentDrawerOpen(false);
      }
    } catch (error) {
      console.error('Delete chat session failed:', error);
      addAgentMessage(
        error instanceof Error ? `Couldn’t delete the conversation: ${error.message}` : 'Couldn’t delete the conversation.',
        'error'
      );
    }
  };
  const deleteDocument = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this document?')) {
      return;
    }

    try {
      await apiFetch(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
      const remaining = documents.filter(doc => doc.id !== id);
      setDocuments(remaining);
      setQueryDocumentIds(prev => prev.filter(docId => docId !== id));
      if (selectedDocument?.id === id) {
        const nextSelected = remaining[0] || null;
        setSelectedDocument(nextSelected);
        persistSelectedDocumentId(nextSelected?.id);
        if (nextSelected) {
          void selectDocument(nextSelected);
        }
      }
      addAgentMessage("Document deleted.");
    } catch (error) {
      console.error('Delete document failed:', error);
      addAgentMessage(
        error instanceof Error ? `Couldn’t delete the document: ${error.message}` : 'Couldn’t delete the document.',
        "error"
      );
    }
  };
  const handleFileUpload = async (file: File) => {
    console.log('File upload triggered:', file.name, file.type, file.size);
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      addAgentMessage(`That file is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is 50 MB.`, "error");
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
      const inferredTitle = uploadForm.title || file.name.replace(/\.[^/.]+$/, '');
      setFileContent(preview);
      if (!uploadForm.title) {
        setUploadForm(prev => ({
          ...prev,
          title: inferredTitle
        }));
      }
      addAgentMessage(`“${file.name}” is ready. Select “Index this document” to process it.`, "success");
    } catch (error) {
      console.error('File processing error:', error);
      addAgentMessage(`Couldn’t read that file: ${error instanceof Error ? error.message : 'unknown error'}. Try a different file.`, "error");
      setUploadedFile(null);
    } finally {
      setIsProcessingFile(false);
    }
  };

  const handleUploadEntry = () => {
    if (!isAuthenticated) {
      addAgentMessage("Sign in to upload documents.", "error");
      return;
    }
    setActiveTab('upload');
  };

  const totalDocuments = documents.length;
  const agentStarterCards: Array<{ title: string; prompt: string; tier: RagReasoningMode }> = [
    { title: '总结', prompt: '总结这份合同的关键条款', tier: 'flash' },
    { title: '评估风险', prompt: '违约责任条款有哪些风险？', tier: 'deep' },
    { title: '对比', prompt: '对比两份合同的付款条件', tier: 'flash' },
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
      ? 'All documents'
      : scopedDocumentCount > 0
        ? `${scopedDocumentCount} selected`
        : 'Current document';
  const queryScopeDetail =
    queryScopeMode === 'all'
      ? `${totalDocuments} documents available`
      : selectedQueryDocuments.length > 0
        ? selectedQueryDocuments.map((doc) => doc.title).join(', ')
        : selectedDocument?.title || 'No document selected';
  const loadingSteps = getLoadingSteps(tier);
  const currentLoadingStep = loadingSteps[Math.min(loadingStepIndex, loadingSteps.length - 1)];
  const showLongWaitHint = isLoading && loadingElapsedMs >= 8000;
  const loadingHintText =
    loadingElapsedMs >= 15000
      ? 'Still working. Large libraries can take a little longer.'
      : 'Gathering evidence can take a few more seconds.';
  const sortedTaskSessions = [...chatSessions].sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''));
  const normalizedTaskSearch = taskSearchTerm.trim().toLowerCase();
  const filteredTaskSessions = sortedTaskSessions.filter((session) => {
    if (!normalizedTaskSearch) return true;
    return (
      session.title.toLowerCase().includes(normalizedTaskSearch) ||
      formatRelativeTime(session.updatedAt).toLowerCase().includes(normalizedTaskSearch)
    );
  });
  const uploadDisabled = isUploading || isProcessingFile || !uploadForm.title || (!uploadedFile && !fileContent && !uploadForm.content);
  const displayedConversation = conversation.filter(
    (message, index) => !(index === 0 && message.type === 'agent' && message.content.includes('CausalGraph'))
  );
  const hasPendingAssistantMessage = displayedConversation.some(message => (
    message.type === 'agent' &&
    !message.content.trim() &&
    Boolean(message.data?.messageId)
  ));
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
      await apiFetch('/feedback', jsonRequest('POST', payload));
      markFeedbackSubmitted(message, messageId, rating);
    } catch (error) {
      // 409: this answer already has feedback on the server.
      if (error instanceof ApiError && error.status === 409) {
        markFeedbackSubmitted(message, messageId, rating);
        return;
      }
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
  const uploadDisplayTitle = uploadStatusTitle || uploadedFile?.name || uploadForm.title || 'Uploaded document';
  const latestAgentMessage = [...displayedConversation].reverse().find((message) => (
    message.type === 'agent' &&
    (
      Boolean(message.content.trim()) ||
      Boolean(message.data?.flowTrace?.length) ||
      Boolean(message.data?.agentTrace?.length) ||
      Boolean(message.data?.sources?.length)
    )
  ));
  const liveTrace = [...pipelineTrace, ...agentTrace];
  const persistedTrace = [
    ...(latestAgentMessage?.data?.flowTrace || []),
    ...(latestAgentMessage?.data?.agentTrace || []),
  ];
  const drawerTrace = liveTrace.length > 0 ? liveTrace : persistedTrace;
  const drawerSources = agentDrawerSourcesOverride || latestAgentMessage?.data?.sources || [];
  const hasAgentWorkspace = activeTab === 'chat' && (
    isLoading ||
    activeAgentPath === 'agent' ||
    pipelineTrace.length > 0 ||
    drawerTrace.length > 0 ||
    drawerSources.length > 0
  );
  const isEmptyChat = displayedConversation.length === 0 && !showPipelineStatus;
  const currentSession = chatSessions.find(session => session.id === currentSessionId);
  const sessionTitle = currentSession?.title?.trim() || deriveSessionTitle(conversation);
  const accountLabel = user?.username || user?.email || 'Account';
  const accountInitial = String(accountLabel).trim().charAt(0).toUpperCase() || '?';
  const mobileTitle =
    activeTab === 'documents' ? 'Library'
      : activeTab === 'upload' ? 'Upload'
        : isEmptyChat ? 'New research' : sessionTitle;
  useDocumentTitle(activeTab === 'chat' && isEmptyChat ? 'Research desk' : mobileTitle);
  const searchShortcut =
    typeof navigator !== 'undefined' && /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent) ? '⌘K' : 'Ctrl K';

  // Grow the composer with its content, up to a limit.
  useEffect(() => {
    const element = composerInputRef.current;
    if (!element) return;
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
  }, [inputText, isEmptyChat, activeTab]);

  // The composer is disabled while an answer streams; hand focus back afterwards
  // on devices with a mouse so the next question can be typed straight away.
  const wasLoadingRef = useRef(false);
  useEffect(() => {
    if (wasLoadingRef.current && !isLoading && activeTab === 'chat') {
      const hasFinePointer = typeof window.matchMedia === 'function' && window.matchMedia('(pointer: fine)').matches;
      if (hasFinePointer && (!document.activeElement || document.activeElement === document.body)) {
        composerInputRef.current?.focus({ preventScroll: true });
      }
    }
    wasLoadingRef.current = isLoading;
  }, [isLoading, activeTab]);

  useEffect(() => {
    if (!isMobileNavOpen && !isAccountMenuOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setIsMobileNavOpen(false);
      setIsAccountMenuOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isMobileNavOpen, isAccountMenuOpen]);

  const openSourcesDrawer = (sources: RagSource[], sourceNumber?: number) => {
    setAgentDrawerSourcesOverride(sources);
    setAgentDrawerTab('files');
    setAgentDrawerOpen(true);
    setHighlightedSource(sourceNumber ?? null);
  };

  const copyMessage = async (key: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageKey(key);
      window.setTimeout(() => setCopiedMessageKey(current => (current === key ? null : current)), 1600);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  };

  const toggleDocumentInScope = (documentId: string) => {
    setQueryScopeMode('selected');
    setQueryDocumentIds(prev => {
      if (prev.includes(documentId)) return prev.filter(id => id !== documentId);
      if (prev.length >= 3) return prev;
      return [...prev, documentId];
    });
  };

  const askAboutDocument = (doc: Document) => {
    setQueryScopeMode('selected');
    setQueryDocumentIds(prev => [doc.id, ...prev.filter(id => id !== doc.id)].slice(0, 3));
    setActiveTab('chat');
    window.requestAnimationFrame(() => composerInputRef.current?.focus());
  };

  const closeMobileNav = () => setIsMobileNavOpen(false);
  const showTab = (tab: string) => {
    setActiveTab(tab);
    closeMobileNav();
  };

  const renderSidebar = () => (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-14 shrink-0 items-center justify-between pl-4 pr-2">
        <Link to="/" className="rounded-md" aria-label="CausalGraph home">
          <BrandLogo size="sm" />
        </Link>
        <button type="button" onClick={closeMobileNav} className="icon-btn lg:hidden" aria-label="Close sidebar">
          <X className="h-4 w-4" />
        </button>
      </div>

      <nav className="space-y-0.5 px-2" aria-label="Workspace">
        <button
          type="button"
          onClick={() => {
            handleNewSession();
            closeMobileNav();
          }}
          className="nav-item font-medium text-ink"
        >
          <PenSquare className="h-4 w-4" />
          New research
        </button>
        <button
          type="button"
          onClick={() => {
            setIsSearchPaletteOpen(true);
            closeMobileNav();
          }}
          className="nav-item"
        >
          <Search className="h-4 w-4" />
          Search
          <span className="kbd ml-auto hidden lg:inline-flex">{searchShortcut}</span>
        </button>
        <button
          type="button"
          onClick={() => showTab('chat')}
          aria-current={activeTab === 'chat' && !currentSessionId ? 'page' : undefined}
          className="nav-item"
        >
          <MessageSquare className="h-4 w-4" />
          Chat
        </button>
        <button
          type="button"
          onClick={() => showTab('documents')}
          aria-current={activeTab === 'documents' ? 'page' : undefined}
          className="nav-item"
        >
          <Library className="h-4 w-4" />
          Library
          <span className="ml-auto text-xs tabular-nums text-ink-4">{totalDocuments}</span>
        </button>
        <button
          type="button"
          onClick={() => {
            handleUploadEntry();
            closeMobileNav();
          }}
          aria-current={activeTab === 'upload' ? 'page' : undefined}
          className="nav-item"
        >
          <FileUp className="h-4 w-4" />
          Upload
          {isUploading && <span className="ml-auto font-mono text-[11px] text-ink-4">{uploadProgress}%</span>}
        </button>
      </nav>

      <div className="cg-scroll mt-6 min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <div className="section-label px-2.5 pb-1.5">Recents</div>
        {isChatSessionsLoading && chatSessions.length === 0 && (
          <p className="px-2.5 py-1 text-[13px] text-ink-4">Loading…</p>
        )}
        {chatSessionsError && <p className="px-2.5 py-1 text-[13px] text-err">{chatSessionsError}</p>}
        {!isChatSessionsLoading && !chatSessionsError && chatSessions.length === 0 && (
          <p className="px-2.5 py-1 text-[13px] leading-5 text-ink-4">Your research sessions will appear here.</p>
        )}
        <ul className="space-y-px">
          {sortedTaskSessions.map((session) => {
            const isActive = session.id === currentSessionId && activeTab === 'chat';
            const title = session.title || 'Untitled research';
            return (
              <li key={session.id} className="group/session relative">
                <button
                  type="button"
                  onClick={() => {
                    handleSelectSession(session.id);
                    closeMobileNav();
                  }}
                  aria-current={isActive ? 'page' : undefined}
                  className="nav-item h-8 pr-8 text-[13px]"
                  title={title}
                >
                  <span className="truncate">{title}</span>
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    if (window.confirm('Delete this conversation?')) {
                      handleDeleteSession(session.id);
                    }
                  }}
                  className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1 text-ink-4 opacity-0 transition hover:bg-paper-pressed hover:text-err focus:opacity-100 group-hover/session:opacity-100"
                  title="Delete"
                  aria-label={`Delete ${title}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="relative shrink-0 border-t border-line p-2">
        {isAccountMenuOpen && (
          <>
            <button
              type="button"
              aria-label="Close account menu"
              className="fixed inset-0 z-40 cursor-default"
              onClick={() => setIsAccountMenuOpen(false)}
            />
            <div className="menu absolute bottom-full left-2 right-2 z-50 mb-2" role="menu">
              <div className="px-2.5 pb-2 pt-1.5">
                <div className="truncate text-sm font-medium text-ink">{accountLabel}</div>
                {user?.email && <div className="truncate text-xs text-ink-4">{user.email}</div>}
              </div>
              <div className="menu-sep" />
              <Link to="/" className="menu-item" role="menuitem">
                <Home className="h-4 w-4 text-ink-4" />
                Home
              </Link>
              {isAdmin && (
                <Link to="/admin" className="menu-item" role="menuitem">
                  <ShieldCheck className="h-4 w-4 text-ink-4" />
                  Admin console
                </Link>
              )}
              <div className="menu-sep" />
              <button
                type="button"
                onClick={() => {
                  setIsAccountMenuOpen(false);
                  logout();
                }}
                className="menu-item"
                role="menuitem"
              >
                <LogOut className="h-4 w-4 text-ink-4" />
                Sign out
              </button>
            </div>
          </>
        )}
        <button
          type="button"
          onClick={() => setIsAccountMenuOpen(prev => !prev)}
          aria-haspopup="menu"
          aria-expanded={isAccountMenuOpen}
          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-paper-hover"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-xs font-medium text-white">
            {accountInitial}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium text-ink">{accountLabel}</span>
            <span className="block text-xs text-ink-4">{accountPlanLabel} plan</span>
          </span>
          <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-ink-4" />
        </button>
      </div>
    </div>
  );

  const renderSearchPalette = () => (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/10 px-4 pt-[12vh]"
      onMouseDown={() => setIsSearchPaletteOpen(false)}
      role="presentation"
    >
      <div
        className="w-full max-w-[560px] overflow-hidden rounded-xl border border-line bg-white shadow-lg"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Search research"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search className="h-4 w-4 shrink-0 text-ink-4" />
          <input
            ref={taskSearchInputRef}
            value={taskSearchTerm}
            onChange={(event) => setTaskSearchTerm(event.target.value)}
            placeholder="Search your research"
            aria-label="Search your research"
            className="h-12 min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-5"
          />
          <span className="kbd hidden sm:inline-flex">Esc</span>
          <button
            type="button"
            onClick={() => setIsSearchPaletteOpen(false)}
            className="icon-btn -mr-2 sm:hidden"
            aria-label="Close search"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="cg-scroll max-h-[400px] overflow-y-auto p-1.5">
          <button
            type="button"
            onClick={() => {
              setIsSearchPaletteOpen(false);
              setTaskSearchTerm('');
              handleNewSession();
            }}
            className="menu-item font-medium text-ink"
          >
            <PenSquare className="h-4 w-4 text-ink-4" />
            New research
          </button>
          {isChatSessionsLoading && chatSessions.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-ink-4">Loading…</p>
          ) : filteredTaskSessions.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-ink-4">
              {normalizedTaskSearch ? 'Nothing matches that search.' : 'No research sessions yet.'}
            </p>
          ) : (
            <>
              <div className="section-label px-2.5 pb-1 pt-3">{normalizedTaskSearch ? 'Results' : 'Recent'}</div>
              {filteredTaskSessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => {
                    setIsSearchPaletteOpen(false);
                    setTaskSearchTerm('');
                    handleSelectSession(session.id);
                  }}
                  className="menu-item"
                >
                  <MessageSquare className="h-4 w-4 shrink-0 text-ink-4" />
                  <span className="min-w-0 flex-1 truncate">{session.title || 'Untitled research'}</span>
                  <span className="shrink-0 text-xs text-ink-4">{formatRelativeTime(session.updatedAt)}</span>
                </button>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );

  const renderComposer = () => (
    <div className="w-full">
      <form
        onSubmit={handleSubmit}
        className="rounded-2xl border border-line-strong bg-white shadow-sm transition-[border-color,box-shadow] focus-within:border-ink-4 focus-within:shadow-md"
      >
        {queryScopeMode !== 'all' && (
          <div className="flex flex-wrap items-center gap-1.5 px-3 pt-3">
            {effectiveQueryDocumentIds.slice(0, 3).map((docId) => {
              const doc = documents.find(item => item.id === docId);
              if (!doc) return null;
              const removable = queryDocumentIds.includes(docId);
              return (
                <span key={docId} className="tag max-w-[240px]">
                  <FileText className="h-3 w-3 shrink-0 text-ink-4" />
                  <span className="truncate">{doc.title}</span>
                  {removable && (
                    <button
                      type="button"
                      onClick={() => setQueryDocumentIds((prev) => prev.filter((id) => id !== docId))}
                      className="-mr-1 rounded p-0.5 text-ink-4 transition-colors hover:text-ink"
                      title="Remove from scope"
                      aria-label={`Remove ${doc.title} from scope`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </span>
              );
            })}
            <button
              type="button"
              onClick={() => setActiveTab('documents')}
              className="px-1 text-xs font-medium text-ink-3 underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink"
            >
              {effectiveQueryDocumentIds.length ? 'Change' : 'Choose documents'}
            </button>
          </div>
        )}
        <textarea
          ref={composerInputRef}
          id="research-question"
          aria-label="Research question"
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
              ? 'Ask something that needs several documents, a comparison or a chain of reasoning…'
              : 'Ask about payment terms, liability, termination, confidentiality…'
          }
          rows={1}
          className="block max-h-[200px] min-h-[52px] w-full resize-none bg-transparent px-4 pb-2 pt-3.5 text-[15.5px] leading-6 text-ink outline-none placeholder:text-ink-5 disabled:cursor-not-allowed"
          disabled={isLoading}
        />
        <div className="flex items-center gap-1 px-2 pb-2">
          <button
            type="button"
            onClick={handleUploadEntry}
            disabled={isUploading || isProcessingFile}
            className="icon-btn"
            title="Upload document"
            aria-label="Upload document"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setQueryScopeMode(queryScopeMode === 'all' ? 'selected' : 'all')}
            className="inline-flex h-8 min-w-0 items-center gap-1.5 rounded-md px-2 text-[13px] text-ink-3 transition-colors hover:bg-paper-hover hover:text-ink"
            title={`Scope: ${queryScopeDetail}. Click to switch between all documents and selected documents.`}
          >
            <FolderOpen className="h-4 w-4 shrink-0" />
            <span className="truncate">{queryScopeLabel}</span>
          </button>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <div className="segmented" role="group" aria-label="Reasoning tier">
              <button
                type="button"
                onClick={() => setTier('flash')}
                aria-pressed={tier === 'flash'}
                title="Fast: answers directly from the most relevant passages"
              >
                Fast
              </button>
              <button
                type="button"
                onClick={() => setTier('deep')}
                aria-pressed={tier === 'deep'}
                title="Deep: plans a search, reads more evidence and checks coverage before answering"
              >
                Deep
              </button>
            </div>
            <button
              type="submit"
              disabled={!inputText.trim() || isLoading}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-ink text-white transition-colors hover:bg-ink-2 disabled:cursor-not-allowed disabled:bg-paper-hover disabled:text-ink-5"
              title="Send (Enter)"
              aria-label="Send"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </form>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-1">
        <ModelStatus tier={tier} />
        <span className="hidden text-xs text-ink-4 md:inline">Check the cited passages before relying on an answer.</span>
      </div>
    </div>
  );

  const renderMessages = () => (
    <div className="mx-auto w-full max-w-[760px] px-4 pb-8 pt-6 sm:px-6 lg:pt-2">
      <div className="space-y-8">
        {displayedConversation.map((message, index) => {
          const time = message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

          if (message.type === 'user') {
            return (
              <div key={index} className="group flex flex-col items-end">
                <div className="max-w-[85%] rounded-2xl bg-paper-hover px-4 py-2.5">
                  <div className="cg-prose cg-prose-compact">
                    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS}>
                      {normalizeMathForMarkdown(message.content)}
                    </ReactMarkdown>
                  </div>
                </div>
                <time className="mt-1 px-1 text-[11px] text-ink-5 opacity-0 transition-opacity group-hover:opacity-100">
                  {time}
                </time>
              </div>
            );
          }

          const feedbackMessageId = getFeedbackMessageId(message, index);
          const feedbackRating = submittedFeedback[feedbackMessageId] || message.data?.feedback?.rating;
          const feedbackDraft = feedbackDrafts[feedbackMessageId];
          const canSubmitFeedback = Boolean(message.content.trim() && message.data?.backend);
          const messageAgentTrace = [
            ...(message.data?.flowTrace || []),
            ...(message.data?.agentTrace || []),
          ];
          const isAgentAnswer = message.data?.agentPath === 'agent' || messageAgentTrace.length > 0;
          const hasAssistantContent = message.content.trim().length > 0;
          const messageSources = message.data?.sources || [];

          return (
            <article key={index} className="group">
              {!hasAssistantContent && (
                <>
                  <div className="flex items-center gap-2.5 text-[15px] text-ink-3">
                    <span className="cg-working" aria-hidden="true" />
                    <span>{currentLoadingStep}</span>
                  </div>
                  {isAgentAnswer && messageAgentTrace.length > 0 && (
                    <div className="mt-3 pl-[18px]">
                      <TraceEvents steps={messageAgentTrace} compact />
                    </div>
                  )}
                  {showLongWaitHint && <p className="mt-3 pl-[18px] text-xs text-ink-4">{loadingHintText}</p>}
                </>
              )}

              {isAgentAnswer && hasAssistantContent && message.data?.partial && (
                <div className="mb-3">
                  <AnswerWarningBadge partial={message.data?.partial} partialReason={message.data?.partialReason} />
                </div>
              )}

              {hasAssistantContent && (
                <div className="cg-prose">
                  <CitationContext.Provider value={(sourceNumber) => openSourcesDrawer(messageSources, sourceNumber)}>
                    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS} components={ANSWER_COMPONENTS}>
                      {linkCitations(normalizeStreamingMarkdown(message.content), messageSources)}
                    </ReactMarkdown>
                  </CitationContext.Provider>
                </div>
              )}

              {hasAssistantContent && (
                <SourceStrip sources={messageSources} onOpen={(sourceNumber) => openSourcesDrawer(messageSources, sourceNumber)} />
              )}

              {hasAssistantContent && (
                <div className="mt-3 flex items-center gap-0.5">
                  <button
                    type="button"
                    onClick={() => void copyMessage(feedbackMessageId, message.content)}
                    className="icon-btn h-7 w-7"
                    aria-label="Copy answer"
                    title="Copy"
                  >
                    {copiedMessageKey === feedbackMessageId ? <Check className="h-3.5 w-3.5 text-ok" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                  {canSubmitFeedback && (
                    <>
                      <button
                        type="button"
                        onClick={() => void submitFeedback(message, index, 'up')}
                        disabled={Boolean(feedbackRating || feedbackDraft?.submitting)}
                        aria-pressed={feedbackRating === 'up'}
                        aria-label="Mark answer helpful"
                        title="Helpful"
                        className={`icon-btn h-7 w-7 ${feedbackRating === 'up' ? 'text-ink disabled:opacity-100' : ''}`}
                      >
                        <ThumbsUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => openDownvoteFeedback(message, index)}
                        disabled={Boolean(feedbackRating || feedbackDraft?.submitting)}
                        aria-pressed={feedbackRating === 'down'}
                        aria-label="Mark answer unhelpful"
                        title="Not helpful"
                        className={`icon-btn h-7 w-7 ${feedbackRating === 'down' ? 'text-ink disabled:opacity-100' : ''}`}
                      >
                        <ThumbsDown className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                  {feedbackRating && <span className="ml-1.5 text-xs text-ink-4">Thanks for the feedback</span>}
                  {feedbackDraft?.error && feedbackDraft.rating !== 'down' && (
                    <span className="ml-1.5 inline-flex items-center gap-1 text-xs text-err">
                      <AlertCircle className="h-3 w-3" />
                      {feedbackDraft.error}
                    </span>
                  )}
                  <time className="ml-auto text-[11px] text-ink-5 opacity-0 transition-opacity group-hover:opacity-100">{time}</time>
                </div>
              )}

              {feedbackDraft && feedbackDraft.rating === 'down' && !feedbackRating && (
                <div className="mt-2 max-w-lg rounded-xl border border-line bg-white p-3">
                  <p className="text-[13px] font-medium text-ink">What was wrong with this answer?</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {FEEDBACK_REASON_OPTIONS.map(option => {
                      const selected = feedbackDraft.tags.includes(option.tag);
                      return (
                        <label
                          key={option.tag}
                          className={`inline-flex h-7 cursor-pointer items-center rounded-md border px-2.5 text-xs transition-colors ${
                            selected
                              ? 'border-ink bg-ink text-white'
                              : 'border-line bg-white text-ink-3 hover:border-line-strong hover:text-ink'
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
                      aria-label="Feedback note"
                      className="input mt-2 min-h-[64px] resize-none text-[13px]"
                    />
                  )}
                  {feedbackDraft.error && (
                    <p className="mt-2 flex items-center gap-1.5 text-xs text-err">
                      <AlertCircle className="h-3 w-3" />
                      {feedbackDraft.error}
                    </p>
                  )}
                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setFeedbackDrafts(prev => {
                          const next = { ...prev };
                          delete next[feedbackMessageId];
                          return next;
                        });
                      }}
                      className="btn btn-ghost btn-sm"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => void submitFeedback(message, index, 'down')}
                      disabled={feedbackDraft.submitting}
                      className="btn btn-primary btn-sm"
                    >
                      {feedbackDraft.submitting ? 'Sending…' : 'Send feedback'}
                    </button>
                  </div>
                </div>
              )}
            </article>
          );
        })}

        {showPipelineStatus && !hasPendingAssistantMessage && (
          <div>
            <div className="flex items-center gap-2.5 text-[15px] text-ink-3">
              <span className="cg-working" aria-hidden="true" />
              <span>{currentLoadingStep}</span>
            </div>
            {liveTrace.length > 0 && (
              <div className="mt-3 pl-[18px]">
                <TraceEvents steps={liveTrace} compact />
              </div>
            )}
            {showLongWaitHint && <p className="mt-3 pl-[18px] text-xs text-ink-4">{loadingHintText}</p>}
          </div>
        )}
        <div ref={conversationEndRef} />
      </div>
    </div>
  );

  const renderChatView = () => (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!isEmptyChat && (
          <header className="hidden h-14 shrink-0 items-center gap-3 px-6 lg:flex">
            <h1 className="min-w-0 truncate text-sm font-medium text-ink-2" title={sessionTitle}>
              {sessionTitle}
            </h1>
            {queryScopeMode !== 'all' && (
              <span className="tag shrink-0" title={queryScopeDetail}>
                <FolderOpen className="h-3 w-3 text-ink-4" />
                {queryScopeLabel}
              </span>
            )}
            {hasAgentWorkspace && (
              <button
                type="button"
                onClick={() => {
                  setAgentDrawerOpen(prev => !prev);
                  setAgentDrawerTab('process');
                }}
                aria-pressed={agentDrawerOpen}
                className={`btn btn-sm ml-auto gap-1.5 ${agentDrawerOpen ? 'bg-paper-hover text-ink' : 'btn-ghost'}`}
                title="Show how the answer was researched"
              >
                <Network className="h-3.5 w-3.5" />
                Process
              </button>
            )}
          </header>
        )}

        <div
          ref={conversationScrollRef}
          onScroll={updateAutoFollowConversation}
          className="cg-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain"
        >
          {isEmptyChat ? (
            <WorkbenchWelcome
              documentCount={totalDocuments}
              starters={agentStarterCards}
              composer={renderComposer()}
              onUpload={handleUploadEntry}
              onLibrary={() => setActiveTab('documents')}
              onPrompt={(starter) => {
                setTier(starter.tier);
                setInputText(starter.prompt);
                composerInputRef.current?.focus();
              }}
            />
          ) : (
            renderMessages()
          )}
        </div>

        {!isEmptyChat && (
          <div className="shrink-0 px-4 pb-4 pt-2 sm:px-6">
            <div className="mx-auto w-full max-w-[760px]">{renderComposer()}</div>
          </div>
        )}
      </section>

      {hasAgentWorkspace && (
        <AgentWorkspaceDrawer
          open={agentDrawerOpen}
          tab={agentDrawerTab}
          onTabChange={setAgentDrawerTab}
          onClose={() => setAgentDrawerOpen(false)}
          steps={drawerTrace}
          sources={drawerSources}
          isLoading={isLoading}
          currentLoadingStep={currentLoadingStep}
          highlightedSource={highlightedSource}
        />
      )}
    </div>
  );

  const renderSyncStatus = (doc: Document) => {
    const loadingDetail = loadingDocumentId === doc.id;
    const synced = Boolean(doc.neo4j_sync?.synced);
    const syncEnabled = doc.neo4j_sync?.enabled !== false;
    const failed = syncEnabled && !synced && !loadingDetail && Boolean(doc.neo4j_sync?.reason);
    const label = loadingDetail
      ? 'Loading details'
      : synced
        ? 'Synced to Neo4j'
        : failed
          ? `Neo4j sync failed: ${doc.neo4j_sync?.reason}`
          : 'Not synced to Neo4j';
    return (
      <span className="inline-flex h-7 w-7 items-center justify-center" title={label} aria-label={label} role="img">
        {loadingDetail ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-ink-4" />
        ) : (
          <span className={`status-dot ${synced ? 'bg-ok' : failed ? 'bg-warn' : 'bg-line-strong'}`} />
        )}
      </span>
    );
  };

  const renderDocumentDetail = (doc: Document) => (
    <section className="min-w-0" aria-label="Document details">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="break-words text-xl font-semibold leading-snug text-ink">{doc.title}</h2>
          {doc.source && <p className="mt-1 truncate font-mono text-xs text-ink-4">{doc.source}</p>}
          {loadingDocumentId === doc.id && <p className="mt-2 text-sm text-ink-3">Loading details…</p>}
        </div>
        <button type="button" onClick={() => askAboutDocument(doc)} className="btn btn-primary btn-sm">
          Ask about this document
        </button>
      </div>

      <dl className="mt-6 grid grid-cols-3 divide-x divide-line rounded-xl border border-line bg-white">
        {[
          ['Passages', String(doc.chunk_count || 0)],
          ['Category', documentCategoryLabel(doc.domain)],
          ['Added', formatDocumentDate(doc.ingested_at)],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0 px-4 py-3">
            <dt className="text-xs text-ink-4">{label}</dt>
            <dd className="mt-1 truncate text-lg font-semibold tabular-nums text-ink">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );

  const renderLibraryView = () => (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Library</h1>
          <p className="mt-1 text-sm text-ink-3">Documents you can search. Put up to three in scope to focus a question on them.</p>
        </div>
        <button type="button" onClick={handleUploadEntry} className="btn btn-secondary btn-sm">
          <FileUp className="h-4 w-4" />
          Upload document
        </button>
      </div>

      {documentsError && (
        <div className="mt-5 rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-sm text-warn">{documentsError}</div>
      )}
      {isDocumentsLoading && (
        <div className="mt-5 flex items-center gap-2 text-sm text-ink-3">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Loading documents…
        </div>
      )}

      {documents.length === 0 ? (
        !isDocumentsLoading && (
          <div className="mt-8 rounded-xl border border-dashed border-line-strong px-6 py-16 text-center">
            <p className="font-medium text-ink">No documents yet</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-ink-3">
              Upload a contract to start asking questions about it.
            </p>
            <button type="button" onClick={handleUploadEntry} className="btn btn-primary btn-sm mt-5">
              Upload a document
            </button>
          </div>
        )
      ) : (
        <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(280px,340px)_minmax(0,1fr)] xl:items-start">
          <ul className="panel divide-y divide-line overflow-hidden" aria-label="Documents">
            {documents.map((doc) => {
              const inQueryScope = queryDocumentIds.includes(doc.id);
              const canAddToScope = inQueryScope || queryDocumentIds.length < 3;
              const isSelected = selectedDocument?.id === doc.id;
              return (
                <li
                  key={doc.id}
                  className={`group relative flex items-start gap-2 py-3 pl-4 pr-2 transition-colors ${
                    isSelected ? 'bg-paper-sunken' : 'hover:bg-paper-sunken/60'
                  }`}
                >
                  {isSelected && <span aria-hidden="true" className="absolute inset-y-0 left-0 w-0.5 bg-ink" />}
                  <button
                    type="button"
                    onClick={() => {
                      void selectDocument(doc);
                    }}
                    aria-current={isSelected ? 'true' : undefined}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span className="line-clamp-2 break-words text-sm font-medium leading-snug text-ink">{doc.title}</span>
                    <span className="mt-1 block text-xs text-ink-4">
                      {doc.chunk_count || 0} passages
                    </span>
                  </button>
                  <div className="flex shrink-0 items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => toggleDocumentInScope(doc.id)}
                      disabled={!canAddToScope}
                      aria-pressed={inQueryScope}
                      title={inQueryScope ? 'Remove from question scope' : canAddToScope ? 'Add to question scope' : 'Up to three documents can be in scope'}
                      className={`h-7 rounded-md px-2 text-xs font-medium transition-colors disabled:cursor-not-allowed ${
                        inQueryScope
                          ? 'bg-ink text-white hover:bg-ink-2'
                          : 'border border-line bg-white text-ink-3 hover:border-line-strong hover:text-ink disabled:text-ink-5 disabled:hover:border-line'
                      }`}
                    >
                      {inQueryScope ? 'In scope' : canAddToScope ? 'Add' : 'Max 3'}
                    </button>
                    {isAdmin && renderSyncStatus(doc)}
                    <button
                      type="button"
                      onClick={() => deleteDocument(doc.id)}
                      className="icon-btn h-7 w-7 hover:text-err sm:opacity-0 sm:focus:opacity-100 sm:group-hover:opacity-100"
                      title="Delete document"
                      aria-label={`Delete ${doc.title}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>

          {selectedDocument ? (
            renderDocumentDetail(selectedDocument)
          ) : (
            <div className="rounded-xl border border-dashed border-line-strong px-6 py-16 text-center text-sm text-ink-3">
              Select a document to see its details.
            </div>
          )}
        </div>
      )}
    </div>
  );

  const renderUploadView = () => (
    <div className="mx-auto w-full max-w-[720px] px-4 py-6 sm:px-6 lg:py-10">
      <h1 className="page-title">Upload a document</h1>
      <p className="mt-1 text-sm leading-6 text-ink-3">
        PDF, Word, plain text or RTF, up to 50 MB. The document is split into passages and indexed for search.
      </p>

      <div className="segmented mt-6" role="tablist" aria-label="Input method">
        {([
          { id: 'file', label: 'Upload a file' },
          { id: 'text', label: 'Paste text' },
        ] as const).map((option) => (
          <button
            key={option.id}
            type="button"
            role="tab"
            aria-selected={uploadInputMode === option.id}
            onClick={() => {
              setUploadInputMode(option.id);
              if (option.id === 'file') {
                setUploadForm((prev) => ({ ...prev, content: '' }));
              } else {
                setUploadedFile(null);
                setFileContent('');
              }
            }}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
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
                aria-label="Choose a file"
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
                className={`flex min-h-[200px] cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 text-center transition-colors ${
                  isDraggingFile ? 'border-ink bg-white' : 'border-line-strong bg-white/60 hover:border-ink-5 hover:bg-white'
                }`}
              >
                <FileUp className={`h-5 w-5 ${isDraggingFile ? 'text-ink' : 'text-ink-4'}`} />
                <p className="mt-3 text-sm font-medium text-ink">
                  {isDraggingFile ? 'Drop to add the file' : 'Drop a file here, or click to browse'}
                </p>
                <p className="mt-1 text-xs text-ink-4">PDF, DOC, DOCX, TXT or RTF</p>
                {isProcessingFile && (
                  <p className="mt-4 flex items-center gap-2 text-xs text-ink-3">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Reading the file…
                  </p>
                )}
              </div>
            ) : (
              <div className="rounded-xl border border-line bg-white px-4 py-3">
                <div className="flex items-center gap-3">
                  <FileText className="h-4 w-4 shrink-0 text-ink-4" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{uploadedFile.name}</p>
                    <p className="text-xs text-ink-4">{(uploadedFile.size / 1024).toFixed(1)} KB</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setUploadedFile(null);
                      setFileContent('');
                    }}
                    className="btn btn-ghost btn-sm hover:text-err"
                  >
                    Remove
                  </button>
                </div>
                {fileContent && (
                  <details className="mt-3 border-t border-line pt-3">
                    <summary className="cursor-pointer text-xs font-medium text-ink-3 hover:text-ink">Preview</summary>
                    <p className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap text-xs leading-5 text-ink-2">
                      {fileContent.substring(0, 400)}
                      {fileContent.length > 400 && <span className="text-ink-4">…</span>}
                    </p>
                  </details>
                )}
              </div>
            )}
          </>
        ) : (
          <textarea
            value={uploadForm.content}
            onChange={(e) => setUploadForm({ ...uploadForm, content: e.target.value })}
            rows={14}
            aria-label="Document text"
            className="input min-h-[300px] resize-y text-sm"
            placeholder="Paste a section, an excerpt or the whole document."
          />
        )}
      </div>

      <div className="mt-6 space-y-4">
        <div>
          <label className="field-label" htmlFor="upload-title">Title</label>
          <input
            id="upload-title"
            type="text"
            value={uploadForm.title}
            onChange={(e) => setUploadForm({ ...uploadForm, title: e.target.value })}
            className="input"
            placeholder={uploadedFile?.name || 'For example: Equipment Purchase Agreement 2024'}
          />
        </div>

        {isAdmin && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="upload-domain">Category</label>
              <select
                id="upload-domain"
                value={uploadForm.domain}
                onChange={(e) => setUploadForm({ ...uploadForm, domain: e.target.value })}
                className="input"
              >
                {DOCUMENT_CATEGORIES.map((category) => (
                  <option key={category.value} value={category.value}>{category.label}</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <button type="button" onClick={() => handleUpload()} disabled={uploadDisabled} className="btn btn-primary">
          {isUploading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {uploadStage ? `${uploadStage.charAt(0).toUpperCase()}${uploadStage.slice(1)}…` : 'Processing…'}
            </>
          ) : (
            'Index this document'
          )}
        </button>
        {!isUploading && uploadDisabled && (
          <span className="text-xs text-ink-4">Add a file or text, and a title.</span>
        )}
      </div>

      {isUploading && (
        <div className="mt-5">
          <div className="flex items-center justify-between gap-3 text-xs text-ink-3">
            <span className="truncate">{uploadMessage || uploadStage || 'Processing'}</span>
            <span className="shrink-0 font-mono tabular-nums text-ink-2">{uploadProgress}%</span>
          </div>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-paper-hover">
            <div className="h-full bg-ink transition-all duration-500" style={{ width: `${Math.max(4, uploadProgress)}%` }} />
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="research-workspace flex h-screen h-dvh overflow-hidden bg-paper text-ink">
      {isSearchPaletteOpen && renderSearchPalette()}

      <aside className="hidden w-[260px] shrink-0 border-r border-line bg-paper-sunken lg:block">
        {renderSidebar()}
      </aside>

      {isMobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close sidebar"
            className="absolute inset-0 h-full w-full cursor-default bg-ink/20"
            onClick={closeMobileNav}
          />
          <aside className="absolute inset-y-0 left-0 w-[280px] max-w-[85vw] bg-paper-sunken shadow-lg">
            {renderSidebar()}
          </aside>
        </div>
      )}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center gap-1 border-b border-line px-2 lg:hidden">
          <button type="button" onClick={() => setIsMobileNavOpen(true)} className="icon-btn" aria-label="Open sidebar">
            <PanelLeft className="h-[18px] w-[18px]" />
          </button>
          <div className="min-w-0 flex-1 truncate px-1 text-sm font-medium text-ink">{mobileTitle}</div>
          {activeTab === 'chat' && hasAgentWorkspace && (
            <button
              type="button"
              onClick={() => {
                setAgentDrawerOpen(prev => !prev);
                setAgentDrawerTab('process');
              }}
              className="icon-btn"
              aria-label="Show process"
            >
              <Network className="h-[18px] w-[18px]" />
            </button>
          )}
          <button type="button" onClick={handleNewSession} className="icon-btn" aria-label="New research">
            <PenSquare className="h-[18px] w-[18px]" />
          </button>
        </div>

        {isUploading && activeTab !== 'upload' && (
          <div className="shrink-0 border-b border-line bg-white px-4 py-2">
            <div className="mx-auto flex max-w-[760px] items-center gap-3 text-xs text-ink-3">
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
              <span className="min-w-0 flex-1 truncate">
                Indexing {uploadDisplayTitle} · {uploadStage || 'processing'}
              </span>
              <span className="shrink-0 font-mono tabular-nums">{uploadProgress}%</span>
            </div>
          </div>
        )}

        {activeTab === 'chat' ? (
          renderChatView()
        ) : (
          <div className="cg-scroll min-h-0 flex-1 overflow-y-auto">
            {activeTab === 'documents' && renderLibraryView()}
            {activeTab === 'upload' && renderUploadView()}
          </div>
        )}
      </div>
    </div>
  );
};

export default Agent;
