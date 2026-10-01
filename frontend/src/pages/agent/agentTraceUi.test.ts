import { setCurrentLang } from '../../i18n/core';
import {
  formatAgentPartialDescription,
  formatAgentPartialLabel,
  formatAgentStageLabel,
  formatAgentStepCountLabel,
  formatAgentTraceSummary,
  mergeAgentTraceSteps,
  shouldShowLiveAgentTracePanel,
} from './agentTraceUi';

describe('agent trace UI labels', () => {
  beforeEach(() => setCurrentLang('en'));
  afterEach(() => setCurrentLang('zh'));

  it('hides backend tool names behind user-facing action labels', () => {
    expect(formatAgentStageLabel({ step: 1, stage: 'searching_reports', tool: 'search_documents', status: 'running', summary: '' })).toBe('Searching documents');
    expect(formatAgentStageLabel({ step: 2, stage: 'querying_graph', tool: 'query_neo4j', status: 'completed', summary: '' })).toBe('Reading graph context');
    expect(formatAgentStageLabel({ step: 3, stage: 'synthesizing', tool: 'summarize_evidence', status: 'completed', summary: '' })).toBe('Drafting grounded answer');
  });

  it('uses project flow labels for plan-execute-reflexion traces', () => {
    expect(formatAgentStageLabel({ step: 1, stage: 'routing', status: 'completed', summary: '' })).toBe('Routing request');
    expect(formatAgentStageLabel({ step: 2, stage: 'context_ready', status: 'completed', summary: '' })).toBe('Preparing RAG context');
    expect(formatAgentStageLabel({ step: 3, stage: 'planning', phase: 'plan', status: 'planned', summary: '' })).toBe('Build evidence plan');
    expect(formatAgentStageLabel({ step: 4, stage: 'planning', phase: 'thought', status: 'completed', summary: '' })).toBe('Choose next evidence step');
    expect(formatAgentStageLabel({ step: 5, stage: 'planning', phase: 'reflexion', status: 'completed', summary: '' })).toBe('Check evidence coverage');
    expect(formatAgentStageLabel({ step: 4, stage: 'planning', phase: 'action', tool: 'search_documents', status: 'completed', summary: '' })).toBe('Searching documents');
  });

  it('sanitizes trace summaries that mention backend function names', () => {
    expect(formatAgentTraceSummary({
      step: 1,
      stage: 'searching_reports',
      tool: 'search_documents',
      status: 'running',
      summary: 'Running search_documents.',
    })).toBe('Checking the most relevant passages.');

    expect(formatAgentTraceSummary({
      step: 2,
      stage: 'querying_graph',
      tool: 'get_graph_context',
      status: 'completed',
      summary: 'get_graph_context completed.',
    })).toBe('Cross-checking entities and relationships.');

    expect(formatAgentTraceSummary({
      step: 3,
      stage: 'searching_reports',
      tool: 'search_documents',
      status: 'running',
      summary: 'Action: search_documents for Apple.',
    })).toBe('Searching the documents for Apple.');

    expect(formatAgentTraceSummary({
      step: 4,
      stage: 'planning',
      phase: 'thought',
      status: 'completed',
      summary: 'Thought: verify targeted report evidence for Apple before using it in the answer.',
    })).toBe('verify targeted report evidence for Apple before using it in the answer.');
  });

  it('uses evidence-quality wording for partial answers', () => {
    expect(formatAgentPartialLabel('missing_entity_evidence')).toBe('Limited evidence coverage');
    expect(formatAgentPartialLabel('max_rounds_reached')).toBe('Evidence search hit the round limit');
    expect(formatAgentPartialLabel('max_steps_reached')).toBe('Evidence search hit the round limit');
    expect(formatAgentPartialLabel('deadline_reached')).toBe('Answer still useful, evidence search timed out');
    expect(formatAgentPartialLabel('stream_interrupted')).toBe('Answer stream interrupted');
  });

  it('only shows the trace panel while evidence retrieval is still live', () => {
    const steps = [{ step: 1, stage: 'planning', phase: 'action', status: 'running', summary: '' }];

    expect(shouldShowLiveAgentTracePanel({
      activeAgentPath: 'agent',
      steps,
      showPipelineStatus: true,
      hasAnswerStarted: false,
    })).toBe(true);

    expect(shouldShowLiveAgentTracePanel({
      activeAgentPath: 'agent',
      steps,
      showPipelineStatus: true,
      hasAnswerStarted: true,
    })).toBe(false);

    expect(shouldShowLiveAgentTracePanel({
      activeAgentPath: 'agent',
      steps,
      showPipelineStatus: false,
      hasAnswerStarted: false,
    })).toBe(false);
  });

  it('merges streamed trace updates for the same action event', () => {
    const runningAction = {
      step: 3,
      stage: 'searching_reports',
      tool: 'search_documents',
      status: 'running',
      summary: 'Action: search_documents for Apple.',
      phase: 'action',
      plan_step: 1,
    };
    const completedAction = {
      ...runningAction,
      status: 'completed',
    };
    const observation = {
      step: 4,
      stage: 'searching_reports',
      tool: 'search_documents',
      status: 'completed',
      summary: 'Found Apple evidence.',
      phase: 'observation',
      plan_step: 1,
    };

    const merged = mergeAgentTraceSteps([runningAction], [completedAction, observation]);

    expect(merged).toHaveLength(2);
    expect(merged[0].status).toBe('completed');
    expect(merged[1].phase).toBe('observation');
  });

  it('keeps the research desk summaries and unknown stages as written in English', () => {
    expect(formatAgentTraceSummary({ step: 1, stage: 'context_ready', summary: 'Prepared context from 3 passages, hybrid retrieval.' }))
      .toBe('Prepared context from 3 passages, hybrid retrieval.');
    expect(formatAgentTraceSummary({ step: 2, stage: 'routing', summary: 'Routing request' })).toBe('Routing request');
    expect(formatAgentStageLabel({ step: 3, stage: 'custom_stage', summary: '' })).toBe('Custom Stage');
    expect(formatAgentStageLabel({ step: 4, stage: '', summary: '' })).toBe('Evidence Check');
    expect(formatAgentStepCountLabel([])).toBe('No trace yet');
  });

  it('shows the labels and summaries in Chinese by default', () => {
    setCurrentLang('zh');
    expect(formatAgentStageLabel({ step: 1, stage: 'searching_reports', tool: 'search_documents', status: 'running', summary: '' })).toBe('检索文档');
    expect(formatAgentStageLabel({ step: 2, stage: 'planning', phase: 'reflexion', status: 'completed', summary: '' })).toBe('检查证据覆盖');
    expect(formatAgentStageLabel({ step: 3, stage: 'completed', status: 'completed', summary: '' })).toBe('回答已生成');
    // A label stored with an answer stays in the language it was written in.
    expect(formatAgentStageLabel({ step: 3, stage: 'completed', status: 'completed', summary: '' }, 'en')).toBe('Answer ready');
    expect(formatAgentTraceSummary({
      step: 4,
      stage: 'searching_reports',
      tool: 'search_documents',
      status: 'running',
      summary: 'Action: search_documents for Apple.',
    })).toBe('正在文档中检索“Apple”。');
    expect(formatAgentTraceSummary({ step: 5, stage: 'searching_reports', summary: 'Retrieved 4 source chunk(s) with hybrid search.' }))
      .toBe('找到 4 个相关段落。');
    expect(formatAgentPartialLabel('max_rounds_reached')).toBe('证据检索已达轮次上限');
    expect(formatAgentPartialDescription('unknown_reason')).toBe('回答基于现有证据，但未能完全覆盖所问的每个方面。');
    expect(formatAgentStepCountLabel([{ step: 1, stage: 'planning', status: 'completed', summary: '' }])).toBe('1/1 项检查');
  });

  it('translates the research desk summaries stored in English, and leaves model wording alone', () => {
    setCurrentLang('zh');
    expect(formatAgentTraceSummary({
      step: 1,
      stage: 'context_ready',
      summary: 'Prepared context from 3 passages, 1 graph relationship, hybrid retrieval, 2 sub-queries.',
    })).toBe('已准备上下文：3 个段落、1 条图谱关系、混合检索、2 个子查询。');
    expect(formatAgentTraceSummary({ step: 2, stage: 'routing', summary: 'Classified the question and selected the retrieval path.' }))
      .toBe('已识别问题类型并选定检索路径。');
    expect(formatAgentTraceSummary({ step: 3, stage: 'completed', summary: 'Answer ready' })).toBe('回答已生成');
    expect(formatAgentTraceSummary({ step: 4, stage: 'planning', phase: 'thought', summary: 'Thought: compare Apple and Microsoft.' }))
      .toBe('compare Apple and Microsoft.');
    expect(formatAgentTraceSummary({ step: 5, stage: 'routing', summary: 'Found Apple evidence.' })).toBe('Found Apple evidence.');
    expect(formatAgentStageLabel({ step: 6, stage: 'constructor', summary: '' })).toBe('Constructor');
  });
});
