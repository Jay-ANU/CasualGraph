import type { AgentTraceStep } from '../../types/api';
import { pick, type Lang } from '../../i18n/core';

type AgentTraceUiStep = Partial<AgentTraceStep> & {
  stage?: string;
  tool?: string | null;
  status?: string;
  summary?: string;
};

/** Interface copy as [Chinese, English], read in the current language when it is shown. */
type Copy = readonly [zh: string, en: string];
const say = ([zh, en]: Copy, lang?: Lang): string => pick(zh, en, lang);

// Keys come from the API, so only the table's own entries count.
const lookup = <T>(table: Record<string, T>, key: string): T | undefined => (
  Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined
);

const traceEventKey = (step: Partial<AgentTraceStep>): string => [
  String(step.step || ''),
  String(step.phase || ''),
  String(step.tool || ''),
  String(step.plan_step || ''),
].join('|');

const TOOL_LABELS: Record<string, Copy> = {
  search_documents: ['检索文档', 'Searching documents'],
  read_chunks: ['阅读证据摘录', 'Reading evidence excerpts'],
  get_graph_context: ['读取图谱上下文', 'Reading graph context'],
  query_neo4j: ['读取图谱上下文', 'Reading graph context'],
  summarize_evidence: ['基于证据起草回答', 'Drafting grounded answer'],
};

const STAGE_LABELS: Record<string, Copy> = {
  routing: ['判断处理路径', 'Routing request'],
  context_ready: ['准备 RAG 上下文', 'Preparing RAG context'],
  generating: ['基于证据撰写回答', 'Writing grounded answer'],
  planning: ['规划证据检索', 'Planning evidence search'],
  searching_reports: ['检索文档', 'Searching documents'],
  querying_graph: ['读取图谱上下文', 'Reading graph context'],
  reading_evidence: ['阅读证据摘录', 'Reading evidence excerpts'],
  synthesizing: ['基于证据起草回答', 'Drafting grounded answer'],
  completed: ['回答已生成', 'Answer ready'],
  partial: ['证据覆盖有限', 'Evidence coverage limited'],
  failed: ['证据检索已中止', 'Evidence search stopped'],
};

const PHASE_LABELS: Record<string, Copy> = {
  plan: ['制定证据计划', 'Build evidence plan'],
  thought: ['确定下一步取证', 'Choose next evidence step'],
  action: ['执行步骤', 'Working step'],
  observation: ['证据更新', 'Evidence update'],
  replan: ['针对缺失证据重新规划', 'Replan missing evidence'],
  reflexion: ['检查证据覆盖', 'Check evidence coverage'],
  final: ['最终回答', 'Final answer'],
};

const PARTIAL_LABELS: Record<string, Copy> = {
  missing_entity_evidence: ['证据覆盖有限', 'Limited evidence coverage'],
  max_rounds_reached: ['证据检索已达轮次上限', 'Evidence search hit the round limit'],
  max_steps_reached: ['证据检索已达轮次上限', 'Evidence search hit the round limit'],
  deadline_reached: ['证据检索超时，回答仍可参考', 'Answer still useful, evidence search timed out'],
  stream_interrupted: ['回答输出中断', 'Answer stream interrupted'],
  agent_error: ['证据复核已恢复', 'Evidence review recovered'],
};

const PARTIAL_DESCRIPTIONS: Record<string, Copy> = {
  missing_entity_evidence: [
    '回答有据可依，但 Agent 未能为每个所问对象找到可比的证据。',
    'The answer is grounded, but the agent could not find comparable evidence for every requested entity.',
  ],
  max_rounds_reached: [
    'Agent 已用完可用的取证轮次，并给出了现有证据所能支持的最佳回答。',
    'The agent used its available evidence rounds and returned the best grounded answer it could support.',
  ],
  max_steps_reached: [
    'Agent 已用完可用的取证轮次，并给出了现有证据所能支持的最佳回答。',
    'The agent used its available evidence rounds and returned the best grounded answer it could support.',
  ],
  deadline_reached: [
    '在较长的证据检索完成之前，Agent 先给出了现有证据所能支持的最佳回答。',
    'The agent returned the best grounded answer before the longer evidence search completed.',
  ],
  stream_interrupted: [
    '与回答流的连接已中断。请重新提问以生成完整回答。',
    'The connection to the answer stream was interrupted. Retry the question to generate a complete response.',
  ],
  agent_error: [
    '系统已从证据复核异常中恢复，并给出了基于现有证据的回答。',
    'The system recovered from an evidence review issue and returned the available grounded answer.',
  ],
};

const TOOL_RUNNING_SUMMARIES: Record<string, Copy> = {
  search_documents: ['正在查找最相关的段落。', 'Checking the most relevant passages.'],
  read_chunks: ['正在打开引用的段落。', 'Opening the cited passages.'],
  get_graph_context: ['正在交叉核对实体与关系。', 'Cross-checking entities and relationships.'],
  query_neo4j: ['正在交叉核对实体与关系。', 'Cross-checking entities and relationships.'],
  summarize_evidence: ['正在整理带引用的最终回答。', 'Preparing the final response with citations.'],
};

const TOOL_COMPLETED_SUMMARIES: Record<string, Copy> = {
  search_documents: ['已收集回答所需的段落。', 'Collected passages for the answer.'],
  read_chunks: ['已阅读引用的证据段落。', 'Read the cited evidence sections.'],
  get_graph_context: ['已交叉核对实体与关系。', 'Cross-checking entities and relationships.'],
  query_neo4j: ['已交叉核对实体与关系。', 'Cross-checking entities and relationships.'],
  summarize_evidence: ['已根据检索到的证据整理出最终回答。', 'Prepared the final answer from retrieved evidence.'],
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
    return pick(`在所选范围内找到 ${layeredMatch[1]} 个段落。`, `Found ${layeredMatch[1]} passages across the selected scope.`);
  }

  const sourceMatch = summary.match(/Retrieved\s+(\d+)\s+source chunk\(s\) with (hybrid|vector) search\./i);
  if (sourceMatch) {
    return pick(`找到 ${sourceMatch[1]} 个相关段落。`, `Found ${sourceMatch[1]} relevant passages.`);
  }

  const readMatch = summary.match(/Read\s+(\d+)\s+chunk\(s\)\./i);
  if (readMatch) {
    return pick(`已打开 ${readMatch[1]} 个引用段落。`, `Opened ${readMatch[1]} cited passages.`);
  }

  const graphMatch = summary.match(/Found graph context with\s+(\d+)\s+edge\(s\)\./i);
  if (graphMatch) {
    return pick(`匹配到 ${graphMatch[1]} 条图谱关系。`, `Matched ${graphMatch[1]} graph relationships.`);
  }

  return null;
};

// The research desk writes these summaries into its own pipeline steps. They are
// stored with the answer in English, so they are translated when they are shown.
const DESK_SUMMARIES_ZH: Record<string, string> = {
  'Classified the question and selected the retrieval path.': '已识别问题类型并选定检索路径。',
  'Prepared the retrieved passages.': '已准备好检索到的段落。',
  'Routing selected the reflexion agent path and started the evidence plan.': '已选定反思式 Agent 路径，开始执行证据计划。',
  'Writing the answer from the retrieved passages.': '正在根据检索到的段落撰写回答。',
  'Delivered the final answer payload with citations and timings.': '已返回含引用与耗时信息的最终回答。',
  ...Object.fromEntries(Object.values(STAGE_LABELS).map(([zh, en]) => [en, zh])),
};

const RETRIEVAL_STRATEGIES_ZH: Record<string, string> = {
  hybrid: '混合检索',
  vector_only: '向量检索',
  layered: '分层检索',
  multi_query: '多查询检索',
  decomposition: '问题拆解检索',
  graph_first: '图谱优先检索',
};

// "3 passages, 2 graph relationships, hybrid retrieval, 2 sub-queries"
const contextPartInChinese = (part: string): string => {
  const passages = part.match(/^(\d+) passages?$/);
  if (passages) return `${passages[1]} 个段落`;
  const relationships = part.match(/^(\d+) graph relationships?$/);
  if (relationships) return `${relationships[1]} 条图谱关系`;
  const subQueries = part.match(/^(\d+) sub-queries$/);
  if (subQueries) return `${subQueries[1]} 个子查询`;
  const strategy = part.match(/^(.+) retrieval$/);
  if (strategy) return lookup(RETRIEVAL_STRATEGIES_ZH, strategy[1]) || `${strategy[1]} 检索`;
  return part;
};

const deskSummaryInChinese = (summary: string): string | undefined => {
  const context = summary.match(/^Prepared context from (.+)\.$/);
  if (context) return `已准备上下文：${context[1].split(', ').map(contextPartInChinese).join('、')}。`;
  return lookup(DESK_SUMMARIES_ZH, summary);
};

/**
 * Label for a trace step. `lang` is only needed to store a label in a fixed
 * language; on screen the current language applies.
 */
export const formatAgentStageLabel = (step: AgentTraceUiStep, lang?: Lang): string => {
  const phase = String((step as { phase?: string }).phase || '').trim();
  const tool = String(step.tool || '').trim();
  const toolLabel = tool ? lookup(TOOL_LABELS, tool) : undefined;
  if (toolLabel) {
    return say(toolLabel, lang);
  }
  const phaseLabel = phase ? lookup(PHASE_LABELS, phase) : undefined;
  if (phaseLabel) {
    return say(phaseLabel, lang);
  }
  const stage = String(step.stage || '').trim();
  const stageLabel = lookup(STAGE_LABELS, stage);
  if (stageLabel) {
    return say(stageLabel, lang);
  }
  return stage ? prettifyFallbackLabel(stage) : pick('证据检查', 'Evidence Check', lang);
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
    return pick('未找到匹配的图谱关系。', 'No matching graph relationships found.');
  }
  if (summary === 'No usable evidence was collected.') {
    return pick('证据检索已结束，但未找到可用的段落。', 'Evidence search finished without usable passages.');
  }
  if (summary === 'Synthesized an answer from collected evidence.') {
    return pick('已根据收集到的证据整理出回答。', 'Prepared the answer from collected evidence.');
  }
  if (summary === 'Search query is required.') {
    return pick('无法准备证据检索。', 'The evidence search could not be prepared.');
  }
  if (/^Thought:\s*/i.test(summary)) {
    return summary.replace(/^Thought:\s*/i, '');
  }
  if (/^Action:\s*search_documents(?:\s+for\s+(.+?))?\.$/i.test(summary)) {
    const match = summary.match(/^Action:\s*search_documents(?:\s+for\s+(.+?))?\.$/i);
    return match?.[1]
      ? pick(`正在文档中检索“${match[1]}”。`, `Searching the documents for ${match[1]}.`)
      : pick('正在检索文档。', 'Searching the documents.');
  }
  if (/^Action:\s*(get_graph_context|query_neo4j)\.$/i.test(summary)) {
    return pick('正在核对图谱关系。', 'Checking graph relationships.');
  }
  if (/^Action:\s*summarize_evidence\.$/i.test(summary)) {
    return pick('正在提炼已收集的证据。', 'Condensing collected evidence.');
  }
  if (/^Reflexion:\s*/i.test(summary)) {
    return summary.replace(/^Reflexion:\s*/i, '');
  }

  if (TOOL_NAME_PATTERN.test(summary)) {
    if (status === 'running') {
      const running = lookup(TOOL_RUNNING_SUMMARIES, tool);
      return running ? say(running) : pick('正在执行证据计划。', 'Working through the evidence plan.');
    }
    const completed = lookup(TOOL_COMPLETED_SUMMARIES, tool);
    return completed ? say(completed) : pick('已完成此取证步骤。', 'Finished this evidence step.');
  }

  if (/^[a-z0-9_]+:/i.test(summary) || /\bchunk_\d+\b/i.test(summary)) {
    const completed = lookup(TOOL_COMPLETED_SUMMARIES, tool);
    return completed ? say(completed) : pick('已审阅支持性证据。', 'Reviewed supporting evidence.');
  }

  // Anything else is the model's or the server's own wording and is shown as written.
  const deskSummary = deskSummaryInChinese(summary);
  return deskSummary ? pick(deskSummary, summary) : summary;
};

export const formatAgentPartialLabel = (reason?: string | null): string => {
  const key = String(reason || '').trim();
  return say(lookup(PARTIAL_LABELS, key) || ['证据覆盖有限', 'Limited evidence coverage']);
};

export const formatAgentPartialDescription = (reason?: string | null): string => {
  const key = String(reason || '').trim();
  return say(lookup(PARTIAL_DESCRIPTIONS, key) || [
    '回答基于现有证据，但未能完全覆盖所问的每个方面。',
    'The response uses available evidence but does not fully cover every requested angle.',
  ]);
};

export const formatAgentStepCountLabel = (steps: AgentTraceStep[]): string => {
  const completed = steps.filter(step => String(step.status || '').toLowerCase() === 'completed').length;
  if (steps.length === 0) {
    return pick('暂无过程记录', 'No trace yet');
  }
  return pick(`${completed}/${steps.length} 项检查`, `${completed}/${steps.length} checks`);
};

export const mergeAgentTraceSteps = (
  existing: AgentTraceStep[],
  incoming: AgentTraceStep[],
): AgentTraceStep[] => {
  if (incoming.length === 0) {
    return existing;
  }
  const merged = [...existing];
  incoming.forEach(step => {
    const key = traceEventKey(step);
    const index = merged.findIndex(candidate => traceEventKey(candidate) === key);
    if (index >= 0) {
      merged[index] = step;
    } else {
      merged.push(step);
    }
  });
  return merged;
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
