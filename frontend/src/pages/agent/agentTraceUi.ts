import type { AgentTraceStep } from '../../types/api';

type AgentTraceUiStep = Partial<AgentTraceStep> & {
  stage?: string;
  tool?: string | null;
  status?: string;
  summary?: string;
};

const TOOL_LABELS: Record<string, string> = {
  search_documents: 'Searching reports',
  read_chunks: 'Reading evidence excerpts',
  get_graph_context: 'Reading graph context',
  query_neo4j: 'Reading graph context',
  summarize_evidence: 'Drafting grounded answer',
};

const STAGE_LABELS: Record<string, string> = {
  planning: 'Planning evidence search',
  searching_reports: 'Searching reports',
  querying_graph: 'Reading graph context',
  reading_evidence: 'Reading evidence excerpts',
  synthesizing: 'Drafting grounded answer',
  completed: 'Answer ready',
  partial: 'Evidence coverage limited',
  failed: 'Evidence search stopped',
};

const PHASE_LABELS: Record<string, string> = {
  plan: 'Thinking Process',
  thought: 'Thinking Process',
  action: 'Working step',
  observation: 'Evidence update',
  replan: 'Replanned evidence search',
  reflexion: 'Thinking Process',
  final: 'Final answer',
};

const PARTIAL_LABELS: Record<string, string> = {
  missing_entity_evidence: 'Limited evidence coverage',
  max_steps_reached: 'Evidence search hit the step limit',
  deadline_reached: 'Answer still useful, evidence search timed out',
  stream_interrupted: 'Answer stream interrupted',
  agent_error: 'Evidence review recovered',
};

const PARTIAL_DESCRIPTIONS: Record<string, string> = {
  missing_entity_evidence: 'The answer is grounded, but the agent could not find comparable evidence for every requested entity.',
  max_steps_reached: 'The agent used its available steps and returned the best grounded answer it could support.',
  deadline_reached: 'The agent returned the best grounded answer before the longer evidence search completed.',
  stream_interrupted: 'The connection to the answer stream was interrupted. Retry the question to generate a complete response.',
  agent_error: 'The system recovered from an evidence review issue and returned the available grounded answer.',
};

const TOOL_RUNNING_SUMMARIES: Record<string, string> = {
  search_documents: 'Checking the most relevant report sections.',
  read_chunks: 'Opening cited report excerpts.',
  get_graph_context: 'Cross-checking entities and relationships.',
  query_neo4j: 'Cross-checking entities and relationships.',
  summarize_evidence: 'Preparing the final response with citations.',
};

const TOOL_COMPLETED_SUMMARIES: Record<string, string> = {
  search_documents: 'Collected report excerpts for the answer.',
  read_chunks: 'Read the cited evidence sections.',
  get_graph_context: 'Cross-checking entities and relationships.',
  query_neo4j: 'Cross-checking entities and relationships.',
  summarize_evidence: 'Prepared the final answer from retrieved evidence.',
};

const TOOL_NAME_PATTERN = /\b(search_documents|read_chunks|get_graph_context|query_neo4j|summarize_evidence)\b/i;

const prettifyFallbackLabel = (value: string): string => (
  value
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase())
);

const rewriteCountSummary = (summary: string): string | null => {
  const layeredMatch = summary.match(/Retrieved\s+(\d+)\s+primary source chunk\(s\) with layered search\./i);
  if (layeredMatch) {
    return `Found ${layeredMatch[1]} report sections across the selected scope.`;
  }

  const sourceMatch = summary.match(/Retrieved\s+(\d+)\s+source chunk\(s\) with (hybrid|vector) search\./i);
  if (sourceMatch) {
    return `Found ${sourceMatch[1]} relevant report sections.`;
  }

  const readMatch = summary.match(/Read\s+(\d+)\s+chunk\(s\)\./i);
  if (readMatch) {
    return `Opened ${readMatch[1]} cited report sections.`;
  }

  const graphMatch = summary.match(/Found graph context with\s+(\d+)\s+edge\(s\)\./i);
  if (graphMatch) {
    return `Matched ${graphMatch[1]} graph relationships.`;
  }

  return null;
};

export const formatAgentStageLabel = (step: AgentTraceUiStep): string => {
  const phase = String((step as { phase?: string }).phase || '').trim();
  const tool = String(step.tool || '').trim();
  if (tool && TOOL_LABELS[tool]) {
    return TOOL_LABELS[tool];
  }
  if (phase && PHASE_LABELS[phase]) {
    return PHASE_LABELS[phase];
  }
  const stage = String(step.stage || '').trim();
  return STAGE_LABELS[stage] || prettifyFallbackLabel(stage || 'Evidence check');
};

export const formatAgentTraceSummary = (
  step: AgentTraceUiStep,
): string => {
  const summary = String(step.summary || '').trim();
  const tool = String(step.tool || '').trim();
  const status = String(step.status || '').toLowerCase();

  if (!summary) {
    return '';
  }

  const countSummary = rewriteCountSummary(summary);
  if (countSummary) {
    return countSummary;
  }

  if (summary === 'No graph context available.') {
    return 'No matching graph relationships found.';
  }
  if (summary === 'No usable evidence was collected.') {
    return 'Evidence search finished without usable report excerpts.';
  }
  if (summary === 'Synthesized an answer from collected evidence.') {
    return 'Prepared the answer from collected evidence.';
  }
  if (summary === 'Search query is required.') {
    return 'The evidence search could not be prepared.';
  }
  if (/^Thought:\s*/i.test(summary)) {
    return summary.replace(/^Thought:\s*/i, '');
  }
  if (/^Action:\s*search_documents(?:\s+for\s+(.+?))?\.$/i.test(summary)) {
    const match = summary.match(/^Action:\s*search_documents(?:\s+for\s+(.+?))?\.$/i);
    return match?.[1] ? `Searching report evidence for ${match[1]}.` : 'Searching report evidence.';
  }
  if (/^Action:\s*(get_graph_context|query_neo4j)\.$/i.test(summary)) {
    return 'Checking graph relationships.';
  }
  if (/^Action:\s*summarize_evidence\.$/i.test(summary)) {
    return 'Condensing collected evidence.';
  }
  if (/^Reflexion:\s*/i.test(summary)) {
    return summary.replace(/^Reflexion:\s*/i, '');
  }

  if (TOOL_NAME_PATTERN.test(summary)) {
    if (status === 'running') {
      return TOOL_RUNNING_SUMMARIES[tool] || 'Working through the evidence plan.';
    }
    return TOOL_COMPLETED_SUMMARIES[tool] || 'Finished this evidence step.';
  }

  if (/^[a-z0-9_]+:/i.test(summary) || /\bchunk_\d+\b/i.test(summary)) {
    return TOOL_COMPLETED_SUMMARIES[tool] || 'Reviewed supporting evidence.';
  }

  return summary;
};

export const formatAgentPartialLabel = (reason?: string | null): string => {
  const key = String(reason || '').trim();
  return PARTIAL_LABELS[key] || 'Limited evidence coverage';
};

export const formatAgentPartialDescription = (reason?: string | null): string => {
  const key = String(reason || '').trim();
  return PARTIAL_DESCRIPTIONS[key] || 'The response uses available evidence but does not fully cover every requested angle.';
};

export const formatAgentStepCountLabel = (steps: AgentTraceStep[]): string => {
  const completed = steps.filter(step => String(step.status || '').toLowerCase() === 'completed').length;
  if (steps.length === 0) {
    return 'No trace yet';
  }
  return `${completed}/${steps.length} checks`;
};

export const shouldShowLiveAgentTracePanel = ({
  activeAgentPath,
  steps,
  showPipelineStatus,
  hasAnswerStarted,
}: {
  activeAgentPath?: string | null;
  steps: Partial<AgentTraceStep>[];
  showPipelineStatus: boolean;
  hasAnswerStarted: boolean;
}): boolean => (
  activeAgentPath === 'agent' &&
  steps.length > 0 &&
  showPipelineStatus &&
  !hasAnswerStarted
);
