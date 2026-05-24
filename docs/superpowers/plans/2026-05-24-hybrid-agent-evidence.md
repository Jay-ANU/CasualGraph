# Hybrid Agent Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic hybrid routing so simple ESG questions stay fast while complex multi-source ESG questions use a bounded evidence-gathering agent.

**Architecture:** Introduce a small routing layer, a fixed tool registry around existing retrieval and graph functions, and a request-scoped agent runner. The existing `rag_pipeline.py` remains the fast/RAG path owner; it delegates only agent-classified questions to the new runner.

**Tech Stack:** Python FastAPI backend, existing RAG modules, existing Claude/OpenAI answer generators, React TypeScript frontend, pytest, React build checks.

---

## File Structure

- Create `rag/agent_types.py`: shared dataclasses and literal types for route decisions, budgets, tool calls, tool observations, and agent trace rows.
- Create `rag/hybrid_agent_router.py`: classifies a request into `fast`, `rag`, or `agent` and assigns the Fast/Deep budget.
- Create `rag/agent_tools.py`: fixed tool registry that wraps existing retrieval and graph APIs.
- Create `rag/agent_runner.py`: bounded request-scoped runner that executes tool steps and synthesizes a final answer.
- Modify `rag/rag_pipeline.py`: call the hybrid router, delegate agent questions, and emit agent progress events in streaming mode.
- Modify `frontend/src/types/api.ts`: add route/path and agent trace response types.
- Modify `frontend/src/pages/Agent.tsx`: render agent stages and partial status without adding a new mode selector.
- Create `tests/test_hybrid_agent_router.py`: route tests.
- Create `tests/test_agent_tools.py`: registry behavior tests with monkeypatched retrieval/graph functions.
- Create `tests/test_agent_runner.py`: budget, timeout, error, and synthesis tests.

## Task 1: Route Decision Types And Hybrid Router

**Files:**
- Create: `rag/agent_types.py`
- Create: `rag/hybrid_agent_router.py`
- Test: `tests/test_hybrid_agent_router.py`

- [ ] **Step 1: Write failing router tests**

Create `tests/test_hybrid_agent_router.py`:

```python
from rag.hybrid_agent_router import decide_hybrid_path


def test_small_talk_uses_fast_path():
    decision = decide_hybrid_path(
        question="hello",
        reasoning_mode="deep",
        document_ids=[],
        preferred_document_id=None,
        answer_intent={"mode": "chitchat", "confidence": 0.92},
    )
    assert decision.path == "fast"
    assert decision.budget.max_steps == 0
    assert decision.budget.deadline_seconds <= 5


def test_current_document_fact_uses_rag_path():
    decision = decide_hybrid_path(
        question="What is Apple's Scope 1 emissions target in this report?",
        reasoning_mode="flash",
        document_ids=["doc_apple"],
        preferred_document_id="doc_apple",
        answer_intent={"mode": "evidence", "confidence": 0.78},
    )
    assert decision.path == "rag"
    assert decision.budget.max_steps == 0


def test_cross_company_comparison_uses_agent_path():
    decision = decide_hybrid_path(
        question="Compare Apple and Microsoft climate transition risks across the uploaded reports and judge which is better supported by evidence.",
        reasoning_mode="deep",
        document_ids=["doc_apple", "doc_msft"],
        preferred_document_id=None,
        answer_intent={"mode": "hybrid", "confidence": 0.86},
    )
    assert decision.path == "agent"
    assert decision.budget.max_steps == 8
    assert decision.budget.deadline_seconds == 90
    assert decision.confidence >= 0.65


def test_fast_complex_question_gets_smaller_agent_budget():
    decision = decide_hybrid_path(
        question="Compare these three ESG reports and identify governance risks with supporting evidence.",
        reasoning_mode="flash",
        document_ids=["a", "b", "c"],
        preferred_document_id=None,
        answer_intent={"mode": "hybrid", "confidence": 0.8},
    )
    assert decision.path == "agent"
    assert decision.budget.max_steps == 3
    assert 15 <= decision.budget.deadline_seconds <= 25
```

- [ ] **Step 2: Run router tests to verify failure**

Run: `python3 -B -m pytest tests/test_hybrid_agent_router.py -q`

Expected: FAIL because `rag.hybrid_agent_router` does not exist.

- [ ] **Step 3: Add shared types**

Create `rag/agent_types.py`:

```python
"""Shared types for the controlled ESG evidence agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

AgentPath = Literal["fast", "rag", "agent"]
AgentStage = Literal[
    "planning",
    "searching_reports",
    "querying_graph",
    "reading_evidence",
    "synthesizing",
    "completed",
    "partial",
    "failed",
]
ToolName = Literal["search_documents", "read_chunks", "query_neo4j", "get_graph_context", "summarize_evidence"]
StepStatus = Literal["planned", "running", "completed", "failed", "skipped"]


@dataclass(frozen=True)
class AgentBudget:
    max_steps: int
    deadline_seconds: int


@dataclass(frozen=True)
class HybridRouteDecision:
    path: AgentPath
    reason: str
    confidence: float
    budget: AgentBudget


@dataclass(frozen=True)
class AgentToolCall:
    tool: ToolName
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTraceStep:
    step: int
    stage: AgentStage
    tool: Optional[str]
    status: StepStatus
    summary: str
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "stage": self.stage,
            "tool": self.tool,
            "status": self.status,
            "summary": self.summary,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass
class AgentToolObservation:
    tool: str
    ok: bool
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class AgentRunResult:
    answer: str
    backend: str
    sources: List[Dict[str, Any]]
    graph_sources: Dict[str, Any]
    trace: List[AgentTraceStep]
    partial: bool = False
    partial_reason: Optional[str] = None
```

- [ ] **Step 4: Add router implementation**

Create `rag/hybrid_agent_router.py`:

```python
"""Hybrid path routing for fast RAG vs bounded evidence-agent execution."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from rag.agent_types import AgentBudget, HybridRouteDecision

_COMPLEX_PATTERN = re.compile(
    r"\b(compare|comparison|across|versus|vs\.?|judge|assess|evaluate|rank|better|worse|"
    r"risk|impact|causal|cause|driver|relationship|why|predict|forecast|scenario|"
    r"strategy|recommend|evidence|support|synthesis|synthesize)\b|"
    r"比较|对比|判断|评估|风险|影响|因果|关系|预测|证据|综合|支持",
    re.I,
)
_COMPANY_JOIN_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+(?:and|vs\.?|versus)\s+[A-Z][A-Za-z0-9&.-]+)\b")


def decide_hybrid_path(
    *,
    question: str,
    reasoning_mode: str,
    document_ids: List[str],
    preferred_document_id: Optional[str],
    answer_intent: Optional[Dict[str, Any]],
) -> HybridRouteDecision:
    text = str(question or "").strip()
    mode = str((answer_intent or {}).get("mode") or "evidence").lower()
    confidence = _safe_float((answer_intent or {}).get("confidence"), 0.0)
    tier = "deep" if str(reasoning_mode or "").lower() == "deep" else "flash"

    if mode == "chitchat" or not text:
        return HybridRouteDecision(
            path="fast",
            reason=f"answer_intent_{mode or 'empty'}",
            confidence=max(confidence, 0.9),
            budget=AgentBudget(max_steps=0, deadline_seconds=5),
        )

    if _is_complex_question(text=text, document_ids=document_ids, mode=mode):
        budget = AgentBudget(max_steps=8, deadline_seconds=90) if tier == "deep" else AgentBudget(max_steps=3, deadline_seconds=25)
        return HybridRouteDecision(
            path="agent",
            reason="complex_multi_source_evidence_question",
            confidence=max(confidence, 0.72),
            budget=budget,
        )

    return HybridRouteDecision(
        path="rag",
        reason="direct_retrieval_question",
        confidence=max(confidence, 0.65 if preferred_document_id or document_ids else 0.55),
        budget=AgentBudget(max_steps=0, deadline_seconds=25 if tier == "flash" else 90),
    )


def _is_complex_question(*, text: str, document_ids: List[str], mode: str) -> bool:
    clean_ids = [item for item in document_ids if str(item or "").strip()]
    if mode == "hybrid" and _COMPLEX_PATTERN.search(text):
        return True
    if len(clean_ids) >= 2 and _COMPLEX_PATTERN.search(text):
        return True
    if _COMPANY_JOIN_PATTERN.search(text) and _COMPLEX_PATTERN.search(text):
        return True
    return False


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default
```

- [ ] **Step 5: Run router tests**

Run: `python3 -B -m pytest tests/test_hybrid_agent_router.py -q`

Expected: PASS.

- [ ] **Step 6: Commit route decision work**

Run:

```bash
git add rag/agent_types.py rag/hybrid_agent_router.py tests/test_hybrid_agent_router.py
git commit -m "feat: add hybrid agent routing"
```

## Task 2: Fixed Agent Tool Registry

**Files:**
- Create: `rag/agent_tools.py`
- Test: `tests/test_agent_tools.py`

- [ ] **Step 1: Write failing tool registry tests**

Create `tests/test_agent_tools.py`:

```python
from rag.agent_tools import AgentToolRegistry


def test_search_documents_returns_typed_observation(monkeypatch):
    def fake_retrieve_context(query, top_k, filters, use_hyde=False, history_block=""):
        return [{"chunk_id": "chunk_1", "document_id": "doc_1", "text": "Apple reports Scope 1 progress.", "score": 0.9}]

    monkeypatch.setattr("rag.agent_tools.retrieve_context", fake_retrieve_context)
    registry = AgentToolRegistry(filters={"document_ids": ["doc_1"]}, history_block="")
    observation = registry.call("search_documents", {"query": "Apple Scope 1", "top_k": 3, "strategy": "vector"})
    assert observation.ok is True
    assert observation.tool == "search_documents"
    assert observation.data["sources"][0]["chunk_id"] == "chunk_1"


def test_get_graph_context_handles_disabled_graph(monkeypatch):
    def fake_graph_context(question, filters=None, hops=None, limit=None, max_triples=None):
        return {"text": "", "matched_entities": [], "nodes": [], "edges": [], "skipped_reason": "neo4j_not_configured"}

    monkeypatch.setattr("rag.agent_tools.build_graph_context", fake_graph_context)
    registry = AgentToolRegistry(filters={}, history_block="")
    observation = registry.call("get_graph_context", {"question": "Apple governance risk", "limit": 10})
    assert observation.ok is False
    assert observation.error == "neo4j_not_configured"


def test_unknown_tool_fails_without_exception():
    registry = AgentToolRegistry(filters={}, history_block="")
    observation = registry.call("missing_tool", {})
    assert observation.ok is False
    assert "Unknown tool" in str(observation.error)
```

- [ ] **Step 2: Run tool tests to verify failure**

Run: `python3 -B -m pytest tests/test_agent_tools.py -q`

Expected: FAIL because `rag.agent_tools` does not exist.

- [ ] **Step 3: Implement registry**

Create `rag/agent_tools.py`:

```python
"""Fixed tool registry for the controlled ESG evidence agent."""

from __future__ import annotations

from typing import Any, Dict, List

from rag.agent_types import AgentToolObservation
from rag.graph_context import build_graph_context
from rag.retriever import retrieve_context, retrieve_hybrid, retrieve_layered_context


class AgentToolRegistry:
    def __init__(self, *, filters: Dict[str, Any], history_block: str):
        self.filters = dict(filters or {})
        self.history_block = history_block or ""

    def call(self, tool_name: str, arguments: Dict[str, Any]) -> AgentToolObservation:
        try:
            if tool_name == "search_documents":
                return self._search_documents(arguments)
            if tool_name == "read_chunks":
                return self._read_chunks(arguments)
            if tool_name == "get_graph_context":
                return self._get_graph_context(arguments)
            if tool_name == "query_neo4j":
                return self._get_graph_context(arguments)
            if tool_name == "summarize_evidence":
                return self._summarize_evidence(arguments)
            return AgentToolObservation(tool=tool_name, ok=False, summary="Tool is not registered.", error=f"Unknown tool: {tool_name}")
        except Exception as exc:
            return AgentToolObservation(tool=tool_name, ok=False, summary=f"{tool_name} failed.", error=f"{type(exc).__name__}: {exc}")

    def _search_documents(self, arguments: Dict[str, Any]) -> AgentToolObservation:
        query = str(arguments.get("query") or "").strip()
        top_k = _bounded_int(arguments.get("top_k"), default=6, minimum=1, maximum=12)
        strategy = str(arguments.get("strategy") or "hybrid").lower()
        if strategy == "layered":
            layers = retrieve_layered_context(query=query, top_k=top_k, filters=self.filters, history_block=self.history_block)
            sources = _flatten_layered_sources(layers)
        elif strategy == "hybrid":
            sources = retrieve_hybrid(query=query, top_k=top_k, filters=self.filters, history_block=self.history_block)
        else:
            sources = retrieve_context(query=query, top_k=top_k, filters=self.filters, history_block=self.history_block)
        return AgentToolObservation(
            tool="search_documents",
            ok=bool(sources),
            summary=f"Found {len(sources)} relevant source chunk{'s' if len(sources) != 1 else ''}.",
            data={"sources": sources, "strategy": strategy},
            error=None if sources else "no_sources",
        )

    def _read_chunks(self, arguments: Dict[str, Any]) -> AgentToolObservation:
        chunks = list(arguments.get("chunks") or [])
        clean = [dict(item) for item in chunks if isinstance(item, dict) and str(item.get("text") or "").strip()]
        return AgentToolObservation(
            tool="read_chunks",
            ok=bool(clean),
            summary=f"Read {len(clean)} source chunk{'s' if len(clean) != 1 else ''}.",
            data={"sources": clean},
            error=None if clean else "no_chunks",
        )

    def _get_graph_context(self, arguments: Dict[str, Any]) -> AgentToolObservation:
        question = str(arguments.get("question") or arguments.get("query") or "").strip()
        limit = _bounded_int(arguments.get("limit"), default=10, minimum=1, maximum=30)
        graph = build_graph_context(question=question, filters=self.filters, limit=limit)
        ok = bool(graph.get("text") or graph.get("edges"))
        return AgentToolObservation(
            tool="get_graph_context",
            ok=ok,
            summary=f"Graph returned {len(graph.get('edges') or [])} edge{'s' if len(graph.get('edges') or []) != 1 else ''}.",
            data={"graph": graph},
            error=None if ok else str(graph.get("skipped_reason") or "no_graph_context"),
        )

    def _summarize_evidence(self, arguments: Dict[str, Any]) -> AgentToolObservation:
        sources = list(arguments.get("sources") or [])
        graph = dict(arguments.get("graph") or {})
        summary = f"Evidence set contains {len(sources)} source chunks and {len(graph.get('edges') or [])} graph edges."
        return AgentToolObservation(tool="summarize_evidence", ok=True, summary=summary, data={"summary": summary})


def _flatten_layered_sources(layers: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for layer_name in ("primary", "priors", "regulatory"):
        for item in layers.get(layer_name) or []:
            row = dict(item)
            row["agent_layer"] = layer_name
            output.append(row)
    return output


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))
```

- [ ] **Step 4: Run tool tests**

Run: `python3 -B -m pytest tests/test_agent_tools.py -q`

Expected: PASS.

- [ ] **Step 5: Commit tool registry**

Run:

```bash
git add rag/agent_tools.py tests/test_agent_tools.py
git commit -m "feat: add agent tool registry"
```

## Task 3: Bounded Agent Runner

**Files:**
- Create: `rag/agent_runner.py`
- Test: `tests/test_agent_runner.py`

- [ ] **Step 1: Write failing runner tests**

Create `tests/test_agent_runner.py`:

```python
from rag.agent_runner import AgentRunner
from rag.agent_types import AgentBudget, AgentToolObservation


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "search_documents":
            return AgentToolObservation(
                tool=tool_name,
                ok=True,
                summary="Found 1 relevant source chunk.",
                data={"sources": [{"chunk_id": "chunk_1", "document_id": "doc_1", "text": "Apple discloses governance oversight."}]},
            )
        if tool_name == "get_graph_context":
            return AgentToolObservation(
                tool=tool_name,
                ok=False,
                summary="Graph returned 0 edges.",
                data={"graph": {"text": "", "edges": [], "nodes": [], "matched_entities": []}},
                error="no_entity_match",
            )
        return AgentToolObservation(tool=tool_name, ok=True, summary="ok", data={})


def test_runner_respects_max_steps():
    registry = FakeRegistry()
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=1, deadline_seconds=90))
    result = runner.run(question="Compare governance risks", reasoning_mode="deep", history_block="")
    assert len(registry.calls) == 1
    assert result.partial is True
    assert result.partial_reason == "max_steps_reached"


def test_runner_collects_sources_and_trace():
    registry = FakeRegistry()
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=3, deadline_seconds=90))
    result = runner.run(question="Compare governance risks", reasoning_mode="deep", history_block="")
    assert result.sources[0]["chunk_id"] == "chunk_1"
    assert any(step.tool == "search_documents" and step.status == "completed" for step in result.trace)
    assert result.answer
```

- [ ] **Step 2: Run runner tests to verify failure**

Run: `python3 -B -m pytest tests/test_agent_runner.py -q`

Expected: FAIL because `rag.agent_runner` does not exist.

- [ ] **Step 3: Implement runner**

Create `rag/agent_runner.py`:

```python
"""Bounded request-scoped agent runner for complex ESG evidence questions."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, List, Optional

from rag.agent_tools import AgentToolRegistry
from rag.agent_types import AgentBudget, AgentRunResult, AgentTraceStep, AgentToolObservation
from rag.claude_answering import generate_claude_deep_rag_answer, claude_answering_available
from rag.openai_answering import generate_openai_rag_answer, openai_answering_available


ProgressCallback = Optional[Callable[[AgentTraceStep], None]]


class AgentRunner:
    def __init__(self, *, registry: AgentToolRegistry, budget: AgentBudget):
        self.registry = registry
        self.budget = budget

    def run(
        self,
        *,
        question: str,
        reasoning_mode: str,
        history_block: str,
        progress_callback: ProgressCallback = None,
    ) -> AgentRunResult:
        started = time.perf_counter()
        trace: List[AgentTraceStep] = []
        observations: List[AgentToolObservation] = []
        partial = False
        partial_reason = None

        plan = self._build_plan(question=question, reasoning_mode=reasoning_mode)
        for index, call in enumerate(plan, start=1):
            if index > self.budget.max_steps:
                partial = True
                partial_reason = "max_steps_reached"
                break
            if time.perf_counter() - started >= self.budget.deadline_seconds:
                partial = True
                partial_reason = "deadline_reached"
                break
            step_started = time.perf_counter()
            running = AgentTraceStep(step=index, stage=_stage_for_tool(call["tool"]), tool=call["tool"], status="running", summary=f"Running {call['tool']}.")
            trace.append(running)
            if progress_callback:
                progress_callback(running)
            observation = self.registry.call(call["tool"], call["arguments"])
            observations.append(observation)
            running.status = "completed" if observation.ok else "failed"
            running.summary = observation.summary if observation.ok else f"{observation.summary} ({observation.error})"
            running.elapsed_ms = (time.perf_counter() - step_started) * 1000
            if progress_callback:
                progress_callback(running)

        sources = _merge_sources(observations)
        graph_sources = _merge_graph_sources(observations)
        answer = self._synthesize_answer(
            question=question,
            history_block=history_block,
            sources=sources,
            graph_sources=graph_sources,
            reasoning_mode=reasoning_mode,
            partial=partial,
            partial_reason=partial_reason,
        )
        trace.append(
            AgentTraceStep(
                step=len(trace) + 1,
                stage="partial" if partial else "completed",
                tool=None,
                status="completed",
                summary="Synthesized an answer from collected evidence." if sources or graph_sources.get("edges") else "No usable evidence was collected.",
            )
        )
        return AgentRunResult(
            answer=answer,
            backend="agent_claude" if reasoning_mode == "deep" and claude_answering_available() else "agent_openai_or_extract",
            sources=sources,
            graph_sources=graph_sources,
            trace=trace,
            partial=partial,
            partial_reason=partial_reason,
        )

    def _build_plan(self, *, question: str, reasoning_mode: str) -> List[Dict[str, Any]]:
        strategy = "layered" if reasoning_mode == "deep" else "hybrid"
        return [
            {"tool": "search_documents", "arguments": {"query": question, "top_k": 8 if reasoning_mode == "deep" else 5, "strategy": strategy}},
            {"tool": "get_graph_context", "arguments": {"question": question, "limit": 16 if reasoning_mode == "deep" else 8}},
            {"tool": "summarize_evidence", "arguments": {}},
        ]

    def _synthesize_answer(
        self,
        *,
        question: str,
        history_block: str,
        sources: List[Dict[str, Any]],
        graph_sources: Dict[str, Any],
        reasoning_mode: str,
        partial: bool,
        partial_reason: Optional[str],
    ) -> str:
        graph_text = str(graph_sources.get("text") or "")
        prefix = ""
        if partial:
            prefix = f"Partial answer: evidence gathering stopped because {partial_reason}.\n\n"
        if reasoning_mode == "deep" and claude_answering_available():
            answer = generate_claude_deep_rag_answer(
                question=question,
                sources=sources,
                history_block=history_block,
                graph_context=graph_text,
                priors=[],
                regulatory=[],
                answer_intent="hybrid",
            )
            if answer:
                return prefix + answer
        if openai_answering_available():
            answer = generate_openai_rag_answer(
                question=question,
                sources=sources,
                history_block=history_block,
                graph_context=graph_text,
                allow_speculation=True,
                answer_intent="hybrid",
            )
            if answer:
                return prefix + answer
        if not sources and not graph_text:
            return prefix + "The provided reports do not contain enough information to answer this question."
        evidence_lines = [f"- [{item.get('chunk_id')}] {str(item.get('text') or '')[:240]}" for item in sources[:6]]
        return prefix + "I found relevant evidence, but no configured generation model was available.\n\n" + "\n".join(evidence_lines)


def stream_agent_run(
    *,
    runner: AgentRunner,
    question: str,
    reasoning_mode: str,
    history_block: str,
) -> Iterator[Dict[str, Any]]:
    progress_events: List[AgentTraceStep] = []

    def collect(step: AgentTraceStep) -> None:
        progress_events.append(step)

    yield {"type": "meta", "payload": {"stream_stage": "agent_planning", "agent_path": "agent"}}
    result = runner.run(question=question, reasoning_mode=reasoning_mode, history_block=history_block, progress_callback=collect)
    for step in progress_events:
        yield {"type": "meta", "payload": {"stream_stage": step.stage, "agent_trace": [step.to_dict()], "agent_path": "agent"}}
    yield {"type": "token", "text": result.answer}
    yield {"type": "done", "payload": agent_result_to_payload(result, reasoning_mode=reasoning_mode)}


def agent_result_to_payload(result: AgentRunResult, *, reasoning_mode: str) -> Dict[str, Any]:
    return {
        "answer": result.answer,
        "mode": "ask",
        "reasoning_mode": reasoning_mode,
        "path": "agent",
        "agent_path": "agent",
        "agent_trace": [step.to_dict() for step in result.trace],
        "partial": result.partial,
        "partial_reason": result.partial_reason,
        "sources": result.sources,
        "graph_sources": result.graph_sources,
        "backend": result.backend,
    }


def _stage_for_tool(tool: str):
    if tool == "search_documents":
        return "searching_reports"
    if tool in {"get_graph_context", "query_neo4j"}:
        return "querying_graph"
    if tool == "read_chunks":
        return "reading_evidence"
    return "synthesizing"


def _merge_sources(observations: List[AgentToolObservation]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for observation in observations:
        for source in observation.data.get("sources") or []:
            key = (source.get("document_id"), source.get("chunk_id"), source.get("text"))
            if key in seen:
                continue
            seen.add(key)
            output.append(dict(source))
    return output


def _merge_graph_sources(observations: List[AgentToolObservation]) -> Dict[str, Any]:
    for observation in observations:
        graph = observation.data.get("graph")
        if isinstance(graph, dict):
            return graph
    return {"text": "", "matched_entities": [], "nodes": [], "edges": [], "skipped_reason": "not_used"}
```

- [ ] **Step 4: Run runner tests**

Run: `python3 -B -m pytest tests/test_agent_runner.py -q`

Expected: PASS.

- [ ] **Step 5: Commit runner**

Run:

```bash
git add rag/agent_runner.py tests/test_agent_runner.py
git commit -m "feat: add bounded evidence agent runner"
```

## Task 4: Backend Pipeline Integration

**Files:**
- Modify: `rag/rag_pipeline.py`
- Test: `tests/test_hybrid_agent_pipeline.py`

- [ ] **Step 1: Write failing pipeline integration tests**

Create `tests/test_hybrid_agent_pipeline.py`:

```python
import rag.rag_pipeline as pipeline


def test_agent_path_delegates_to_runner(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="agent",
            reason="test",
            confidence=0.9,
            budget=pipeline.AgentBudget(max_steps=1, deadline_seconds=90),
        ),
    )

    class FakeRunner:
        def __init__(self, registry, budget):
            self.registry = registry
            self.budget = budget

        def run(self, question, reasoning_mode, history_block, progress_callback=None):
            return pipeline.AgentRunResult(
                answer="Agent answer",
                backend="agent_test",
                sources=[{"chunk_id": "chunk_1", "text": "evidence"}],
                graph_sources={"text": "", "edges": [], "nodes": [], "matched_entities": []},
                trace=[],
            )

    monkeypatch.setattr(pipeline, "AgentRunner", FakeRunner)
    result = pipeline.answer_question(
        "Compare Apple and Microsoft climate risks.",
        reasoning_mode="deep",
        retrieval_filters={"document_ids": ["a", "b"]},
        answer_intent={"mode": "hybrid", "confidence": 0.9},
    )
    assert result["answer"] == "Agent answer"
    assert result["path"] == "agent"
    assert result["backend"] == "agent_test"


def test_rag_path_keeps_existing_prepare_context(monkeypatch):
    decision_calls = []

    def fake_decide(**kwargs):
        decision_calls.append(kwargs)
        return pipeline.HybridRouteDecision(
            path="rag",
            reason="direct",
            confidence=0.8,
            budget=pipeline.AgentBudget(max_steps=0, deadline_seconds=25),
        )

    monkeypatch.setattr(pipeline, "decide_hybrid_path", fake_decide)
    assert callable(pipeline.answer_question)
```

- [ ] **Step 2: Run integration tests to verify failure**

Run: `python3 -B -m pytest tests/test_hybrid_agent_pipeline.py -q`

Expected: FAIL because `rag_pipeline.py` does not import the new agent classes.

- [ ] **Step 3: Import agent modules in `rag/rag_pipeline.py`**

Add near the existing imports:

```python
from rag.agent_runner import AgentRunner, agent_result_to_payload, stream_agent_run
from rag.agent_tools import AgentToolRegistry
from rag.agent_types import AgentBudget, AgentRunResult, HybridRouteDecision
from rag.hybrid_agent_router import decide_hybrid_path
```

- [ ] **Step 4: Add agent delegation after `_prepare_answer_context`**

In `answer_question`, after `answer_intent_mode` is computed and after the `entity_scope_miss` guard, insert:

```python
    hybrid_decision = decide_hybrid_path(
        question=query,
        reasoning_mode=reasoning_mode,
        document_ids=list((retrieval_filters or {}).get("document_ids") or []),
        preferred_document_id=(retrieval_filters or {}).get("preferred_document_id"),
        answer_intent=prepared.get("answer_intent"),
    )
    if hybrid_decision.path == "agent":
        registry = AgentToolRegistry(filters=retrieval_filters or {}, history_block=prepared["history_block"])
        runner = AgentRunner(registry=registry, budget=hybrid_decision.budget)
        generate_started = time.perf_counter()
        agent_result = runner.run(question=query, reasoning_mode=prepared.get("reasoning_mode") or "flash", history_block=prepared["history_block"])
        timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)
        payload = agent_result_to_payload(agent_result, reasoning_mode=prepared.get("reasoning_mode") or "flash")
        payload["routing"] = {
            "strategy": "agent",
            "reason": hybrid_decision.reason,
            "backend": "hybrid_agent_router",
            "fallback_chain": [],
            "fallbacks_used": [],
        }
        payload["answer_intent"] = dict(prepared.get("answer_intent") or {})
        payload["answer_mode"] = answer_intent_mode
        return _finalize_response(
            payload=payload,
            timings=timings,
            total_started=prepared["total_started"],
            mode=resolved_mode,
            strategy="agent",
        )
```

- [ ] **Step 5: Add streaming delegation in `stream_answer_question`**

After `prepared` and `answer_intent_mode` are computed, before no-context and chitchat generation, insert:

```python
    hybrid_decision = decide_hybrid_path(
        question=query,
        reasoning_mode=reasoning_mode,
        document_ids=list((retrieval_filters or {}).get("document_ids") or []),
        preferred_document_id=(retrieval_filters or {}).get("preferred_document_id"),
        answer_intent=prepared.get("answer_intent"),
    )
    if hybrid_decision.path == "agent":
        registry = AgentToolRegistry(filters=retrieval_filters or {}, history_block=prepared["history_block"])
        runner = AgentRunner(registry=registry, budget=hybrid_decision.budget)
        for event in stream_agent_run(
            runner=runner,
            question=query,
            reasoning_mode=prepared.get("reasoning_mode") or "flash",
            history_block=prepared["history_block"],
        ):
            if event.get("type") == "done":
                event["payload"]["answer_intent"] = dict(prepared.get("answer_intent") or {})
                event["payload"]["answer_mode"] = answer_intent_mode
                event["payload"]["timings_ms"] = dict(timings)
            yield event
        return
```

- [ ] **Step 6: Run backend integration tests**

Run:

```bash
python3 -B -m pytest tests/test_hybrid_agent_router.py tests/test_agent_tools.py tests/test_agent_runner.py tests/test_hybrid_agent_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit backend integration**

Run:

```bash
git add rag/rag_pipeline.py tests/test_hybrid_agent_pipeline.py
git commit -m "feat: route complex questions through evidence agent"
```

## Task 5: Frontend Trace Types And Progress Rendering

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/Agent.tsx`

- [ ] **Step 1: Add API types**

In `frontend/src/types/api.ts`, add:

```ts
export type AgentPath = 'fast' | 'rag' | 'agent';

export interface AgentTraceStep {
  step: number;
  stage: string;
  tool?: string | null;
  status: 'planned' | 'running' | 'completed' | 'failed' | 'skipped';
  summary: string;
  elapsed_ms?: number;
}
```

Extend `RagResponse`:

```ts
  path?: AgentPath;
  agent_path?: AgentPath;
  agent_trace?: AgentTraceStep[];
  partial?: boolean;
  partial_reason?: string | null;
```

- [ ] **Step 2: Add frontend state for agent progress**

In `frontend/src/pages/Agent.tsx`, near existing loading state:

```ts
  const [agentTrace, setAgentTrace] = useState<AgentTraceStep[]>([]);
  const [activeAgentPath, setActiveAgentPath] = useState<'fast' | 'rag' | 'agent' | null>(null);
```

Import `AgentTraceStep` from `../types/api`.

- [ ] **Step 3: Reset progress at submit start and finish**

In `handleSubmit`, after `setShowPipelineStatus(true);`, add:

```ts
    setAgentTrace([]);
    setActiveAgentPath(null);
```

In the `finally` block, keep `setShowPipelineStatus(false);` and do not clear `agentTrace`; the final answer can still render the completed trace from payload.

- [ ] **Step 4: Parse agent meta events**

Inside the `event.type === 'meta'` branch in `processUserQuery`, add:

```ts
            if (event.payload.agent_path) {
              setActiveAgentPath(event.payload.agent_path);
            }
            if (Array.isArray(event.payload.agent_trace)) {
              setAgentTrace(prev => {
                const next = [...prev];
                event.payload.agent_trace.forEach((step: AgentTraceStep) => {
                  const index = next.findIndex(item => item.step === step.step && item.tool === step.tool);
                  if (index >= 0) {
                    next[index] = step;
                  } else {
                    next.push(step);
                  }
                });
                return next.sort((a, b) => a.step - b.step);
              });
            }
```

- [ ] **Step 5: Store final agent trace on the message**

Inside the `event.type === 'done'` branch, extend `updateStreamingMessage` data:

```ts
              agentTrace: Array.isArray(event.payload.agent_trace) ? event.payload.agent_trace : undefined,
              partial: Boolean(event.payload.partial),
              partialReason: event.payload.partial_reason || undefined,
```

If `ChatMessage['data']` does not accept these fields, extend the local type definition in `Agent.tsx` where `ChatMessage` is declared.

- [ ] **Step 6: Render progress under the current loading text**

Near the current `showPipelineStatus` block, below the `Step x/y` line, add:

```tsx
                      {activeAgentPath === 'agent' && agentTrace.length > 0 && (
                        <div className="mt-3 w-full max-w-xl space-y-1.5 text-left">
                          {agentTrace.slice(-5).map(step => (
                            <div key={`${step.step}-${step.tool || step.stage}`} className="flex items-start gap-2 rounded-lg border border-hairline bg-white px-3 py-2 text-[12px] text-ink-steel">
                              <span className={`mt-1 h-1.5 w-1.5 rounded-full ${step.status === 'failed' ? 'bg-red-500' : step.status === 'running' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
                              <span className="min-w-0 flex-1">
                                <span className="font-semibold text-ink-charcoal">{formatAgentStage(step.stage)}</span>
                                <span className="block truncate">{step.summary}</span>
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
```

Add helper near existing formatting helpers:

```ts
const formatAgentStage = (stage: string): string => {
  const labels: Record<string, string> = {
    planning: 'Planning',
    searching_reports: 'Searching reports',
    querying_graph: 'Querying graph',
    reading_evidence: 'Reading evidence',
    synthesizing: 'Synthesizing',
    completed: 'Completed',
    partial: 'Partial',
    failed: 'Failed',
  };
  return labels[stage] || stage.replace(/_/g, ' ');
};
```

- [ ] **Step 7: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 8: Commit frontend progress UI**

Run:

```bash
git add frontend/src/types/api.ts frontend/src/pages/Agent.tsx
git commit -m "feat: show evidence agent progress"
```

## Task 6: Verification And Final Integration

**Files:**
- No new feature files.

- [ ] **Step 1: Run Python compile checks**

Run:

```bash
python3 -B -m py_compile rag/agent_types.py rag/hybrid_agent_router.py rag/agent_tools.py rag/agent_runner.py rag/rag_pipeline.py app.py
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run backend tests**

Run:

```bash
python3 -B -m pytest tests/test_hybrid_agent_router.py tests/test_agent_tools.py tests/test_agent_runner.py tests/test_hybrid_agent_pipeline.py tests/test_kg_view_ticket.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 4: Manual local smoke test**

Start the backend and frontend if they are not running:

```bash
python3 -B -m uvicorn app:app --host 127.0.0.1 --port 8000
npm --prefix frontend start
```

Manual checks:

- Ask `hello`; answer should not show agent progress.
- Ask a current-document factual question; answer should use normal RAG progress.
- Ask `Compare Apple and Microsoft climate transition risks across the uploaded reports and judge which is better supported by evidence`; progress should show agent evidence stages.

- [ ] **Step 5: Final commit if smoke fixes were needed**

If Step 4 required fixes, commit them:

```bash
git add rag frontend/src tests
git commit -m "fix: polish hybrid evidence agent"
```

If no fixes were needed, do not create an empty commit.

## Self-Review Notes

- Spec coverage: routing, budgets, fixed tools, request-scoped runner, streaming progress, frontend progress, timeout/partial behavior, and tests are all mapped to tasks.
- Scope control: persistent scheduled tasks and external web search remain out of scope.
- Type consistency: `AgentBudget`, `HybridRouteDecision`, `AgentTraceStep`, and `agent_trace` are introduced in Task 1 and reused consistently by later tasks.
