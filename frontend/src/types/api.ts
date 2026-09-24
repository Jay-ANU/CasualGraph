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
  phase?: 'plan' | 'thought' | 'action' | 'observation' | 'replan' | 'reflexion' | 'final' | string;
  plan_step?: number;
  plan?: Record<string, unknown>[];
  reflexion?: Record<string, unknown>;
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
  source?: string;
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

// ---- Accounts --------------------------------------------------------------

export interface AuthUser {
  id: string;
  email: string;
  username: string;
  role?: string;
  plan?: string;
  plan_label?: string;
  points_limit?: number | null;
  unlimited?: boolean;
  created_at?: string;
}

/** `POST /auth/login` and `POST /auth/register`. */
export interface AuthResponse {
  token: string;
  user: AuthUser;
}

/** `GET /auth/me` wraps the user; older servers returned it bare. */
export type MeResponse = { user?: AuthUser } & Partial<AuthUser>;

export interface CaptchaResponse {
  captcha_id: string;
  image: string;
}

export interface EmailCodeResponse {
  cooldown_seconds?: number;
}

// ---- Documents -------------------------------------------------------------

/** A library document as `GET /documents` and `GET /documents/{id}` return it. */
export interface DocumentSummary {
  id: string;
  title: string;
  domain: string;
  source: string;
  document_group?: string;
  owner_user_id?: string;
  visibility_scope?: string;
  source_type?: string;
  chunk_count?: number;
  ingested_at?: string;
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

export interface DocumentListResponse {
  documents?: DocumentSummary[];
}

export interface DocumentDetailResponse {
  document: DocumentSummary;
}

/** `POST /documents/upload-async`. */
export interface UploadJobCreatedResponse {
  job_id?: string;
}

/** `GET /documents/jobs/{id}`. */
export interface UploadJobResponse {
  status?: 'queued' | 'running' | 'completed' | 'failed' | 'rejected' | string;
  stage?: string;
  progress?: number;
  message?: string;
  error?: string;
  result?: {
    document?: DocumentSummary;
    stats?: { chunk_count?: number };
    duplicate?: boolean;
    matched_by?: string;
  };
}

// ---- Chat sessions ---------------------------------------------------------

export interface ChatSessionPayload {
  id?: string;
  title?: string;
  selected_document_id?: string;
  mode?: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
}

/** A stored message; `data` is whatever the client saved with it. */
export interface ChatMessagePayload {
  role?: string;
  content?: string;
  timestamp?: string;
  data?: unknown;
}

export interface ChatSessionResponse {
  session?: ChatSessionPayload;
}

export interface ChatSessionListResponse {
  sessions?: ChatSessionPayload[];
}

export interface ChatSessionDetailResponse extends ChatSessionResponse {
  messages?: ChatMessagePayload[];
}

// ---- Model status ----------------------------------------------------------

/** `GET /models/status`. Other fields the server may send are ignored. */
export interface ModelConfiguration {
  provider: string;
  model: string;
  configured: boolean;
  modes: Record<'flash' | 'deep', { model: string; configured: boolean; thinking: boolean }>;
}

// ---- Admin -----------------------------------------------------------------

export interface UploadAudit {
  job_id: string;
  document_id?: string;
  title: string;
  filename?: string;
  domain?: string;
  source_type?: string;
  source?: string;
  uploader?: {
    email?: string;
    username?: string;
  };
  status: string;
  stage?: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  error?: string;
  deleted_at?: string;
  delete_reason?: string;
  cleanup_status?: string;
  cleanup_detail?: string;
  cleanup_completed_at?: string;
  duplicate_of_document_id?: string;
  stats?: {
    chunks?: number;
    entities?: number;
    relations?: number;
  };
}

/** `GET /admin/overview`. */
export interface AdminOverview {
  totals: {
    uploads: number;
    completed: number;
    failed: number;
    rejected?: number;
    deleted?: number;
    active: number;
    chunks: number;
    entities: number;
    relations: number;
  };
  daily: Array<{ date: string; uploads: number }>;
  recent_uploads: UploadAudit[];
}

export interface AdminUploadsResponse {
  uploads?: UploadAudit[];
}

export interface AdminUploadDeleteResponse {
  cleanup?: { queued?: boolean };
}

export interface RagUnlimitedUser {
  email: string;
  note?: string;
  created_by_user_id?: string;
  created_at: string;
}

export interface RagUnlimitedUsersResponse {
  users?: RagUnlimitedUser[];
}

export interface RagUnlimitedUserResponse {
  user?: { email?: string };
}

export interface InviteCodeResponse {
  invite_code?: string;
  expires_at?: string;
}
