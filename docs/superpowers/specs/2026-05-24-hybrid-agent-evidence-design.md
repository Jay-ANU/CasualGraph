# Hybrid Agent Evidence Design

Date: 2026-05-24

## Goal

Add a controlled agent path for complex ESG questions while keeping the current fast RAG experience for simple questions.

The first version should improve evidence quality for multi-source ESG analysis. It should automatically decide whether a request needs a fast answer, the existing RAG pipeline, or a bounded multi-step agent run.

## Non-Goals

- Do not build long-running monitoring or scheduled report generation in this version.
- Do not expose hidden model chain-of-thought.
- Do not add unrestricted external web search.
- Do not replace the existing RAG pipeline for simple or direct document questions.

## Product Behavior

The user keeps one chat interface. They do not need to manually choose "Agent".

The existing Fast and Deep controls become budget hints:

- Fast: target 15-25 seconds, at most 3 tool steps.
- Deep: target 90 seconds, at most 8 tool steps.

Simple questions stay fast even if Deep is selected. Complex questions automatically enter the agent path when the router confidence is at least 0.65. If the user selects Fast but the question is clearly complex, the UI should show that a deeper evidence search is running.

The UI should show observable progress only:

1. Planning evidence search
2. Searching reports
3. Querying graph
4. Reading evidence
5. Synthesizing answer

## Routing

Introduce a routing layer before answer generation:

- Fast Path: greetings, thanks, small talk, and general questions that do not require document evidence.
- RAG Path: direct factual questions over the current document or selected documents.
- Agent Path: cross-document comparison, multi-company analysis, ESG risk or impact assessment, prediction, graph relationship questions, and requests that ask for evidence synthesis or judgment.

The router should return a structured decision:

```json
{
  "path": "fast|rag|agent",
  "reason": "short user-facing reason",
  "confidence": 0.0,
  "budget": {
    "max_steps": 8,
    "deadline_seconds": 90
  }
}
```

Low-confidence routing should prefer the safer evidence path when the question mentions a company, report, uploaded document, ESG topic, or graph relationship.

## Architecture

### Agent Runner

Add an agent runner that executes bounded steps:

1. Build a short plan from the user question, document scope, history summary, and budget.
2. Select one tool call at a time from a fixed tool registry.
3. Store the tool observation.
4. Continue until enough evidence is gathered, the step budget is exhausted, the deadline is reached, or the user cancels.
5. Generate the final answer from collected evidence.

The runner must not recursively call itself. It should be a deterministic loop owned by backend code, with explicit step and time limits.

### Tool Registry

V1 tools should wrap existing capabilities:

- `search_documents`: semantic, hybrid, or layered retrieval over scoped documents.
- `read_chunks`: fetch full source chunk text and metadata for selected chunk IDs.
- `query_neo4j`: run safe graph queries through existing Neo4j graph-store methods, not arbitrary Cypher from the model.
- `get_graph_context`: fetch graph neighborhood or causal context for named entities.
- `summarize_evidence`: compress accumulated evidence into a smaller synthesis input.

Each tool needs:

- JSON schema for input.
- Permission and document-scope checks.
- Timeout.
- Small, typed observation output.
- Error output that the runner can continue from.

### State Model

Agent runs are request-scoped in V1. They are not persistent background tasks.

The response should include:

```json
{
  "answer": "...",
  "path": "agent",
  "reasoning_mode": "deep",
  "agent_trace": [
    {
      "step": 1,
      "stage": "searching_reports",
      "tool": "search_documents",
      "status": "completed",
      "summary": "Found 6 relevant chunks across 3 reports."
    }
  ],
  "sources": [],
  "graph_sources": {},
  "timings_ms": {}
}
```

`agent_trace` is an observable audit trail. It should not contain private chain-of-thought.

## Data Flow

1. Frontend sends the existing chat request with question, history, selected document IDs, preferred document ID, and reasoning mode.
2. Backend builds retrieval filters and calls the hybrid route decision.
3. Fast Path returns from the existing chitchat or general answer logic.
4. RAG Path calls the existing `answer_question` or streaming equivalent.
5. Agent Path creates an agent run context with budget, scope, and allowed tools.
6. The runner emits progress events for streaming clients.
7. The runner produces a final grounded answer using collected observations and source metadata.
8. Frontend renders the final answer, source cards, graph evidence, and the observable progress trace.

## Error Handling

- Tool timeout: record a failed step and continue if enough budget remains.
- Tool permission failure: stop using that tool and continue with accessible evidence.
- Empty evidence: return an insufficient-context answer with the attempted trace.
- Deadline reached: synthesize from collected evidence and mark the answer as partial.
- User cancellation: stop the loop and return partial evidence if any was collected.
- Model JSON parsing failure: retry once with a stricter prompt, then fall back to RAG Path.

## Frontend Changes

Keep the current interface. Add progress rendering that can represent both current RAG stages and agent stages.

Required additions:

- Show when the backend chose Fast, RAG, or Agent Path.
- Show agent stages as short status rows.
- Support cancellation for long Deep runs.
- Display partial-answer status clearly when a deadline or cancellation occurs.

The UI should not add another major mode selector in V1.

## Testing

Backend tests:

- Router sends small talk to Fast Path.
- Router sends direct current-document questions to RAG Path.
- Router sends cross-document ESG comparison to Agent Path.
- Agent runner respects max steps.
- Agent runner respects deadline.
- Tool errors are recorded and do not crash the request.
- Agent final answer includes sources when evidence exists.
- Entity-scope misses still return insufficient-context answers.

Frontend tests:

- Progress UI renders RAG and Agent stages.
- Cancellation action calls the backend cancellation endpoint or aborts the stream.
- Partial-answer state is visible.

Manual checks:

- Simple greeting returns quickly.
- Current-document factual question returns through RAG.
- Cross-company ESG comparison enters Agent Path and shows progress.
- Deep question can run close to 90 seconds without the UI appearing stuck.

## Implementation Order

1. Add route decision types and hybrid router wrapper.
2. Add tool registry with wrappers around existing retrieval and graph functions.
3. Add non-streaming agent runner.
4. Add streaming progress events.
5. Add frontend progress and cancellation UI.
6. Add tests for routing, runner budgets, and tool failure behavior.

## Decisions

- Cancellation transport uses the existing streaming request abort in V1. A persistent cancellation endpoint is out of scope for V1.
- Agent planning uses the current Deep model configuration in V1. A separate planning model is out of scope for V1.
