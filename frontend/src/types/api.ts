export type SourceType = 'report_evidence' | 'graph_inference' | 'general_knowledge' | 'speculation';

export interface CausalChainStep {
  step: string;
  source_type: SourceType;
  evidence_refs: string[];
}

export interface PredictionAnswer {
  prediction: string;
  confidence: 'low' | 'medium' | 'high';
  confidence_score?: number;
  confidence_breakdown?: {
    evidence_coverage?: number;
    source_quality?: number;
    citation_density?: number;
    speculation_load?: number;
    counter_pressure?: number;
    assumption_pressure?: number;
  };
  confidence_rationale?: string;
  causal_chain: CausalChainStep[];
  key_assumptions: string[];
  counter_evidence: string[];
  disclaimer: string;
  raw?: string;
  parse_error?: string | null;
}

export type RagIntent = 'answer' | 'prediction' | 'comparison' | 'graph_reasoning' | 'summary' | 'chitchat';
export type RagReasoningMode = 'flash' | 'deep';
export type AgentPath = 'rag' | 'agent';
export type AgentTraceStatus = 'pending' | 'running' | 'completed' | 'failed' | string;

export interface AgentTraceStep {
  step: number;
  stage: string;
  tool?: string | null;
  status: AgentTraceStatus;
  summary: string;
  elapsed_ms?: number;
  meta?: Record<string, unknown>;
}

export interface RagBlock {
  type: 'summary' | 'markdown' | 'evidence' | 'graph' | 'prediction' | 'reasoning' | 'warning' | 'next_steps';
  title?: string;
  content?: string;
  items?: unknown[];
  confidence?: string;
  confidence_score?: number;
  assumptions?: string[];
  counter_evidence?: string[];
  disclaimer?: string;
}

export interface RagSource {
  chunk_id: string;
  text: string;
  document_id?: string;
  document_title?: string;
  document_group?: string;
  source_type?: string;
  domain?: string;
  retrieval_scope?: string;
  relevance_score?: number;
}

export interface RagGraphSource {
  used?: boolean;
  matched_entities?: Array<Record<string, unknown>>;
  edges?: Array<{
    source?: string;
    target?: string;
    relation_type?: string;
    relationship_type?: string;
    confidence?: number;
    evidence?: string;
    chunk_id?: string;
    document_id?: string;
  }>;
  skipped_reason?: string | null;
}

export interface RagTimingsMs {
  rewrite?: number;
  route?: number;
  hyde?: number;
  retrieval?: number;
  rerank?: number;
  graph?: number;
  generate?: number;
  total?: number;
}

export interface RagReasoningTraceStep {
  title: string;
  detail: string;
  items?: string[];
  meta?: Record<string, unknown>;
}

export interface RagResponse {
  answer: string;
  // Deprecated: the backend always returns "ask" now; tier lives on reasoning_mode.
  mode?: 'ask' | 'predict';
  reasoning_mode?: RagReasoningMode;
  intent?: RagIntent;
  blocks?: RagBlock[];
  // Deprecated: legacy structured-prediction payload. The Deep tier now returns
  // plain markdown via `answer`. Left on the type so cached responses from
  // older sessions still parse.
  prediction?: PredictionAnswer;
  sources: RagSource[];
  graph_sources?: RagGraphSource;
  layered_sources?: {
    primary?: RagSource[];
    priors?: RagSource[];
    regulatory?: RagSource[];
  };
  backend: string;
  reasoning_trace?: RagReasoningTraceStep[];
  timings_ms?: RagTimingsMs;
  retrieval_strategy?: string;
  rewritten_query?: string;
  sub_queries?: string[];
  memory_backend?: string;
  session_id?: string;
  path?: AgentPath;
  agent_path?: AgentPath;
  agent_trace?: AgentTraceStep[];
  partial?: boolean;
  partial_reason?: string | null;
}

export type FeedbackRating = 'up' | 'down';
export type FeedbackReasonTag = 'missing_evidence' | 'wrong_citation' | 'hallucination' | 'irrelevant' | 'other';

export interface FeedbackPayload {
  session_id: string;
  message_id: string;
  query: string;
  answer: string;
  rating: FeedbackRating;
  reason_tags?: FeedbackReasonTag[];
  reason_text?: string;
  sources?: RagSource[];
  timings_ms?: RagTimingsMs;
}

export type RagStreamStage = 'routing' | 'context_ready' | 'generating' | 'planning' | 'agent_trace' | 'done';

export type RagStreamEvent =
  | {
      type: 'meta';
      payload: Partial<RagResponse> & {
        rewritten_query?: string;
        retrieval_strategy?: string;
        sub_queries?: string[];
        stream_stage?: RagStreamStage;
        fallback_to_flash?: boolean;
        reason?: string;
      };
    }
  | { type: 'token'; text: string }
  | { type: 'done'; payload: RagResponse }
  | { type: 'error'; message: string };
