import {
  formatAgentPartialLabel,
  formatAgentStageLabel,
  formatAgentTraceSummary,
  shouldShowLiveAgentTracePanel,
} from './agentTraceUi';

describe('agent trace UI labels', () => {
  it('hides backend tool names behind user-facing action labels', () => {
    expect(formatAgentStageLabel({ step: 1, stage: 'searching_reports', tool: 'search_documents', status: 'running', summary: '' })).toBe('Searching reports');
    expect(formatAgentStageLabel({ step: 2, stage: 'querying_graph', tool: 'query_neo4j', status: 'completed', summary: '' })).toBe('Reading graph context');
    expect(formatAgentStageLabel({ step: 3, stage: 'synthesizing', tool: 'summarize_evidence', status: 'completed', summary: '' })).toBe('Drafting grounded answer');
  });

  it('uses MiniMax-style phase labels for plan-execute-react traces', () => {
    expect(formatAgentStageLabel({ step: 1, stage: 'planning', phase: 'plan', status: 'planned', summary: '' })).toBe('Thinking Process');
    expect(formatAgentStageLabel({ step: 2, stage: 'planning', phase: 'thought', status: 'completed', summary: '' })).toBe('Thinking Process');
    expect(formatAgentStageLabel({ step: 3, stage: 'planning', phase: 'reflexion', status: 'completed', summary: '' })).toBe('Thinking Process');
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
});
