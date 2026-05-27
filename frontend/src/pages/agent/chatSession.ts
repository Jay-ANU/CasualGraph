import type { AgentPath, AgentTraceStep, RagBlock, RagGraphSource, RagReasoningMode, RagResponse, RagSource } from '../../types/api';

export interface ChatMessage {
  type: 'user' | 'agent';
  content: string;
  timestamp: Date;
  data?: {
    sources?: RagSource[];
    graphSources?: RagGraphSource;
    blocks?: RagBlock[];
    intent?: string;
    reasoningMode?: RagReasoningMode;
    mode?: string;
    backend?: string;
    agentPath?: AgentPath;
    flowTrace?: AgentTraceStep[];
    agentTrace?: AgentTraceStep[];
    partial?: boolean;
    partialReason?: string | null;
    timingsMs?: RagResponse['timings_ms'];
    messageId?: string;
    feedback?: {
      rating: 'up' | 'down';
      submittedAt?: string;
    };
  };
}

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: string;
  selectedDocumentId?: string;
  mode?: string;
  messageCount?: number;
}

export const STORAGE_KEYS = {
  selectedDocumentId: 'causalgraph_agent_selected_document_id',
  currentSessionId: 'causalgraph_agent_current_session_id_v1',
};

export const deriveSessionTitle = (messages: ChatMessage[]): string => {
  const firstUser = messages.find((m) => m.type === 'user' && m.content?.trim());
  if (!firstUser) return 'New chat';
  const text = firstUser.content.trim().replace(/\s+/g, ' ');
  return text.length > 48 ? `${text.slice(0, 48)}...` : text;
};

export const buildChatMessage = (
  type: 'user' | 'agent',
  content: string,
  data?: ChatMessage['data'],
  timestamp?: string | Date,
): ChatMessage => ({
  type,
  content,
  timestamp: timestamp instanceof Date ? timestamp : new Date(timestamp || Date.now()),
  data,
});

export const toSessionSummary = (raw: any): ChatSession => ({
  id: String(raw?.id || ''),
  title: String(raw?.title || 'New chat'),
  updatedAt: String(raw?.updated_at || raw?.updatedAt || new Date().toISOString()),
  selectedDocumentId: String(raw?.selected_document_id || raw?.selectedDocumentId || ''),
  mode: String(raw?.mode || 'ask'),
  messageCount: Number(raw?.message_count || raw?.messageCount || 0),
});

export const formatRelativeTime = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
};
