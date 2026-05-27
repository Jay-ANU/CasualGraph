import {
  formatAgentPartialLabel,
  formatAgentStageLabel,
  formatAgentTraceSummary,
  mergeAgentTraceSteps,
  shouldShowLiveAgentTracePanel,
} from './agentTraceUi';

describe('agent trace UI labels', () => {
  it('hides backend tool names behind user-facing action labels', () => {
    expect(formatAgentStageLabel({ step: 1, stage: 'searching_reports', tool: 'search_documents', status: 'running', summary: '' })).toBe('Searching reports');
    expect(formatAgentStageLabel({ step: 2, stage: 'querying_graph', tool: 'query_neo4j', status: 'completed', summary: '' })).toBe('Reading graph context');
    expect(formatAgentStageLabel({ step: 3, stage: 'synthesizing', tool: 'summarize_evidence', status: 'completed', summary: '' })).toBe('Drafting grounded answer');
  });

  it('uses project flow labels for plan-execute-reflexion traces', () => {
    expect(formatAgentStageLabel({ step: 1, stage: 'routing', status: 'completed', summary: '' })).toBe('Routing request');
    expect(formatAgentStageLabel({ step: 2, stage: 'context_ready', status: 'completed', summary: '' })).toBe('Preparing RAG context');
    expect(formatAgentStageLabel({ step: 3, stage: 'planning', phase: 'plan', status: 'planned', summary: '' })).toBe('Build evidence plan');
    expect(formatAgentStageLabel({ step: 4, stage: 'planning', phase: 'thought', status: 'completed', summary: '' })).toBe('Choose next evidence step');
    expect(formatAgentStageLabel({ step: 5, stage: 'planning', phase: 'reflexion', status: 'completed', summary: '' })).toBe('Check evidence coverage');
    expect(formatAgentStageLabel({ step: 4, stage: 'planning', phase: 'action', tool: 'search_documents', status: 'completed', summary: '' })).toBe('Searching reports');
  });

  it('sanitizes trace summaries that mention backend function names', () => {
    expect(formatAgentTraceSummary({
      step: 1,
      stage: 'searching_reports',
      tool: 'search_documents',
      status: 'running',
      summary: 'Running search_documents.',
    })).toBe('Checking the most relevant report sections.');

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
    })).toBe('Searching report evidence for Apple.');

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
});
