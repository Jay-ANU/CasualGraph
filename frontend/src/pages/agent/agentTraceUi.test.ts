import {
  formatAgentPartialLabel,
  formatAgentStageLabel,
  formatAgentTraceSummary,
} from './agentTraceUi';

describe('agent trace UI labels', () => {
  it('hides backend tool names behind user-facing action labels', () => {
    expect(formatAgentStageLabel({ step: 1, stage: 'searching_reports', tool: 'search_documents', status: 'running', summary: '' })).toBe('Searching reports');
    expect(formatAgentStageLabel({ step: 2, stage: 'querying_graph', tool: 'query_neo4j', status: 'completed', summary: '' })).toBe('Reading graph context');
    expect(formatAgentStageLabel({ step: 3, stage: 'synthesizing', tool: 'summarize_evidence', status: 'completed', summary: '' })).toBe('Drafting grounded answer');
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
  });

  it('uses evidence-quality wording for partial answers', () => {
    expect(formatAgentPartialLabel('missing_entity_evidence')).toBe('Limited evidence coverage');
    expect(formatAgentPartialLabel('deadline_reached')).toBe('Answer still useful, evidence search timed out');
    expect(formatAgentPartialLabel('stream_interrupted')).toBe('Answer stream interrupted');
  });
});
