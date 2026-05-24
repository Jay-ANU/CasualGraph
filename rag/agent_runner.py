"""Bounded evidence-gathering runner for the hybrid agent path."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from rag.agent_types import (
    AgentBudget,
    AgentRunResult,
    AgentStage,
    AgentToolCall,
    AgentToolObservation,
    AgentTraceStep,
    StepStatus,
)


INSUFFICIENT_CONTEXT_ANSWER = "The provided reports do not contain enough information to answer this question."
_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "compare",
    "did",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


ProgressCallback = Callable[[AgentTraceStep], None]


class AgentRunner:
    """Run a fixed, bounded evidence plan against an agent tool registry."""

    def __init__(self, registry: Any, budget: AgentBudget) -> None:
        self.registry = registry
        self.budget = budget

    def run(
        self,
        question: str,
        reasoning_mode: str,
        history_block: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AgentRunResult:
        started = time.monotonic()
        mode = _normalize_reasoning_mode(reasoning_mode)
        plan = self._build_plan(question=question, reasoning_mode=mode)
        trace: List[AgentTraceStep] = []
        sources: List[Dict[str, Any]] = []
        graph_sources: Dict[str, Any] = {}
        layered_sources: Dict[str, List[Dict[str, Any]]] = {}
        evidence_summaries: List[str] = []
        executed_steps = 0
        partial = False
        partial_reason: Optional[str] = None

        for call in plan:
            if executed_steps >= max(0, int(self.budget.max_steps)):
                partial = True
                partial_reason = "max_steps_reached"
                break
            if self._deadline_reached(started):
                partial = True
                partial_reason = "deadline_reached"
                break

            step_number = executed_steps + 1
            stage = _stage_for_tool(call.tool)
            arguments = self._resolve_arguments(call, question=question, sources=sources, graph=graph_sources)
            running_step = AgentTraceStep(
                step=step_number,
                stage=stage,
                tool=call.tool,
                status="running",
                summary=f"Running {call.tool}.",
                elapsed_ms=(time.monotonic() - started) * 1000,
            )
            _emit_trace_step(trace, running_step, progress_callback)

            tool_started = time.monotonic()
            observation = self._call_tool(call.tool, arguments)
            executed_steps += 1

            _merge_sources(sources, observation.data.get("sources"))
            _merge_graph(graph_sources, observation.data.get("graph"))
            _merge_layered_sources(layered_sources, observation.data.get("layered_sources"))
            summary = _observation_summary(observation)
            if call.tool == "summarize_evidence":
                evidence_summary = str(observation.data.get("summary") or summary).strip()
                if evidence_summary:
                    evidence_summaries.append(evidence_summary)

            completed_step = AgentTraceStep(
                step=step_number,
                stage=stage,
                tool=call.tool,
                status="completed" if observation.ok else "failed",
                summary=summary,
                elapsed_ms=(time.monotonic() - tool_started) * 1000,
            )
            _emit_trace_step(trace, completed_step, progress_callback)

            if call is not plan[-1] and self._deadline_reached(started):
                partial = True
                partial_reason = "deadline_reached"
                break

        answer, backend = _synthesize_answer(
            question=question,
            reasoning_mode=mode,
            history_block=history_block,
            sources=sources,
            graph_sources=graph_sources,
            layered_sources=layered_sources,
            evidence_summaries=evidence_summaries,
        )
        final_step = AgentTraceStep(
            step=executed_steps + 1,
            stage="partial" if partial else "completed",
            tool=None,
            status="completed",
            summary="Synthesized an answer from collected evidence." if sources or graph_sources else "No usable evidence was collected.",
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
        _emit_trace_step(trace, final_step, progress_callback)

        return AgentRunResult(
            answer=answer,
            backend=backend,
            sources=sources,
            graph_sources=graph_sources,
            trace=trace,
            partial=partial,
            partial_reason=partial_reason,
        )

    def _build_plan(self, question: str, reasoning_mode: str) -> List[AgentToolCall]:
        mode = _normalize_reasoning_mode(reasoning_mode)
        if mode == "deep":
            search_args = {"query": question, "strategy": "layered", "top_k": 8, "use_hyde": False}
            graph_args = {"question": question, "limit": 16, "max_triples": 16}
        else:
            search_args = {"query": question, "strategy": "hybrid", "top_k": 5, "use_hyde": False}
            graph_args = {"question": question, "limit": 8, "max_triples": 8}
        return [
            AgentToolCall(tool="search_documents", arguments=search_args),
            AgentToolCall(tool="get_graph_context", arguments=graph_args),
            AgentToolCall(tool="summarize_evidence", arguments={}),
        ]

    def _resolve_arguments(
        self,
        call: AgentToolCall,
        *,
        question: str,
        sources: List[Dict[str, Any]],
        graph: Dict[str, Any],
    ) -> Dict[str, Any]:
        arguments = dict(call.arguments or {})
        if call.tool == "summarize_evidence":
            arguments.update({"question": question, "sources": list(sources), "graph": dict(graph)})
        return arguments

    def _deadline_reached(self, started: float) -> bool:
        deadline_seconds = max(0.0, float(self.budget.deadline_seconds))
        return (time.monotonic() - started) >= deadline_seconds

    def _call_tool(self, tool: str, arguments: Dict[str, Any]) -> AgentToolObservation:
        try:
            observation = self.registry.call(tool, arguments)
        except Exception as exc:
            return AgentToolObservation(
                tool=tool,
                ok=False,
                summary=f"{tool} failed: {type(exc).__name__}",
                data={},
                error=str(exc) or type(exc).__name__,
            )
        if isinstance(observation, AgentToolObservation):
            return observation
        return AgentToolObservation(
            tool=tool,
            ok=False,
            summary=f"{tool} returned an invalid observation.",
            data={},
            error="invalid_tool_observation",
        )


def agent_result_to_payload(result: AgentRunResult, reasoning_mode: str) -> Dict[str, Any]:
    """Convert an agent result to the API response shape used by the UI."""

    mode = _normalize_reasoning_mode(reasoning_mode)
    return {
        "answer": result.answer,
        "mode": "ask",
        "reasoning_mode": mode,
        "path": "agent",
        "agent_path": "agent",
        "agent_trace": [step.to_dict() for step in result.trace],
        "partial": bool(result.partial),
        "partial_reason": result.partial_reason,
        "sources": _serialize_sources(result.sources),
        "graph_sources": _serialize_graph_sources(result.graph_sources),
        "backend": result.backend,
    }


def stream_agent_run(
    *,
    runner: Optional[AgentRunner] = None,
    question: str,
    reasoning_mode: str = "flash",
    history_block: str = "",
    registry: Optional[Any] = None,
    budget: Optional[AgentBudget] = None,
    retrieval_filters: Optional[Dict[str, Any]] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield planning, trace, answer token, and done events for an agent run."""

    mode = _normalize_reasoning_mode(reasoning_mode)
    active_runner = runner or AgentRunner(
        registry=registry or _build_default_registry(retrieval_filters, history_block),
        budget=budget or _default_budget(mode),
    )

    yield {
        "type": "meta",
        "payload": {
            "mode": "ask",
            "reasoning_mode": mode,
            "path": "agent",
            "agent_path": "agent",
            "stream_stage": "planning",
        },
    }

    trace_events: "queue.Queue[AgentTraceStep]" = queue.Queue()
    result_box: Dict[str, Any] = {}

    def _progress(step: AgentTraceStep) -> None:
        trace_events.put(step)

    def _target() -> None:
        try:
            result_box["result"] = active_runner.run(
                question=question,
                reasoning_mode=mode,
                history_block=history_block,
                progress_callback=_progress,
            )
        except Exception as exc:
            result_box["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    while thread.is_alive() or not trace_events.empty():
        try:
            step = trace_events.get(timeout=0.05)
        except queue.Empty:
            continue
        yield {
            "type": "meta",
            "payload": {
                "mode": "ask",
                "reasoning_mode": mode,
                "path": "agent",
                "agent_path": "agent",
                "stream_stage": "agent_trace",
                "agent_trace": [step.to_dict()],
            },
        }
    thread.join()

    result = result_box.get("result")
    if not isinstance(result, AgentRunResult):
        result = AgentRunResult(
            answer=INSUFFICIENT_CONTEXT_ANSWER,
            backend="agent_error",
            sources=[],
            graph_sources={},
            trace=[],
            partial=True,
            partial_reason="agent_error",
        )

    yield {"type": "token", "text": result.answer}
    yield {"type": "done", "payload": agent_result_to_payload(result, mode)}


def _synthesize_answer(
    *,
    question: str,
    reasoning_mode: str,
    history_block: str,
    sources: List[Dict[str, Any]],
    graph_sources: Dict[str, Any],
    layered_sources: Dict[str, List[Dict[str, Any]]],
    evidence_summaries: List[str],
) -> Tuple[str, str]:
    graph_text = str(graph_sources.get("text") or "").strip() if isinstance(graph_sources, dict) else ""

    if reasoning_mode == "deep" and _claude_answering_available():
        try:
            from rag.claude_answering import generate_claude_deep_rag_answer

            answer = generate_claude_deep_rag_answer(
                question=question,
                sources=sources,
                history_block=history_block,
                graph_context=graph_text or None,
                priors=list(layered_sources.get("priors") or []),
                regulatory=list(layered_sources.get("regulatory") or []),
                answer_intent="evidence",
            )
            if answer:
                return answer, "claude_deep+graph" if graph_text else "claude_deep"
        except Exception as exc:
            print(f"[agent_runner] Claude synthesis failed: {type(exc).__name__}: {exc}")

    if _openai_answering_available():
        try:
            from rag.openai_answering import generate_openai_rag_answer

            answer = generate_openai_rag_answer(
                question=question,
                sources=sources,
                history_block=history_block,
                graph_context=graph_text or None,
                allow_speculation=False,
                answer_intent="evidence",
            )
            if answer:
                return answer, "openai+graph" if graph_text else "openai"
        except Exception as exc:
            print(f"[agent_runner] OpenAI synthesis failed: {type(exc).__name__}: {exc}")

    return _extractive_fallback_answer(
        question=question,
        sources=sources,
        graph_sources=graph_sources,
        evidence_summaries=evidence_summaries,
    ), "extractive_fallback"


def _extractive_fallback_answer(
    *,
    question: str,
    sources: List[Dict[str, Any]],
    graph_sources: Dict[str, Any],
    evidence_summaries: List[str],
) -> str:
    query_terms = _extract_query_terms(question)
    scored_sentences: List[Tuple[int, int, str]] = []
    fallback_sentences: List[str] = []

    for index, item in enumerate(sources):
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or item.get("id") or f"source_{index + 1}").strip()
        text = str(item.get("text") or item.get("content") or "").strip()
        for sentence in _split_sentences(text):
            cited = f"{sentence} [{chunk_id}]" if chunk_id else sentence
            fallback_sentences.append(cited)
            sentence_terms = _extract_query_terms(sentence)
            overlap = len(query_terms & sentence_terms)
            if overlap:
                scored_sentences.append((overlap, len(sentence), cited))

    if scored_sentences:
        scored_sentences.sort(key=lambda row: (-row[0], row[1], row[2]))
        selected: List[str] = []
        seen = set()
        for _, _, sentence in scored_sentences:
            if sentence in seen:
                continue
            selected.append(sentence)
            seen.add(sentence)
            if len(selected) >= 2:
                break
        if selected:
            return " ".join(selected)

    if fallback_sentences:
        return fallback_sentences[0]

    graph_text = str((graph_sources or {}).get("text") or "").strip()
    if graph_text:
        return _truncate_words(graph_text, 80)

    for summary in evidence_summaries:
        if str(summary or "").strip():
            return str(summary).strip()

    return INSUFFICIENT_CONTEXT_ANSWER


def _build_default_registry(retrieval_filters: Optional[Dict[str, Any]], history_block: str) -> Any:
    from rag.agent_tools import AgentToolRegistry

    return AgentToolRegistry(filters=retrieval_filters or {}, history_block=history_block)


def _default_budget(reasoning_mode: str) -> AgentBudget:
    if _normalize_reasoning_mode(reasoning_mode) == "deep":
        return AgentBudget(max_steps=8, deadline_seconds=90)
    return AgentBudget(max_steps=3, deadline_seconds=20)


def _normalize_reasoning_mode(reasoning_mode: str) -> str:
    return "deep" if str(reasoning_mode or "flash").strip().lower() == "deep" else "flash"


def _stage_for_tool(tool: str) -> AgentStage:
    if tool == "search_documents":
        return "searching_reports"
    if tool in {"get_graph_context", "query_neo4j"}:
        return "querying_graph"
    if tool == "summarize_evidence":
        return "synthesizing"
    return "planning"


def _emit_trace_step(
    trace: List[AgentTraceStep],
    step: AgentTraceStep,
    progress_callback: Optional[ProgressCallback],
) -> None:
    for index, existing in enumerate(trace):
        if existing.step == step.step and existing.tool == step.tool:
            trace[index] = step
            break
    else:
        trace.append(step)
    if progress_callback is None:
        return
    try:
        progress_callback(step)
    except Exception as exc:
        print(f"[agent_runner] progress callback failed: {type(exc).__name__}: {exc}")


def _observation_summary(observation: AgentToolObservation) -> str:
    summary = str(observation.summary or "").strip()
    if summary:
        return summary
    if observation.error:
        return str(observation.error)
    return f"{observation.tool} completed."


def _merge_sources(target: List[Dict[str, Any]], value: Any) -> None:
    if not isinstance(value, list):
        return
    seen = {_source_key(item) for item in target if isinstance(item, dict)}
    for item in value:
        if not isinstance(item, dict):
            continue
        key = _source_key(item)
        if key in seen:
            continue
        target.append(dict(item))
        seen.add(key)


def _source_key(item: Dict[str, Any]) -> str:
    chunk_id = str(item.get("chunk_id") or item.get("id") or "").strip()
    document_id = str(item.get("document_id") or "").strip()
    if chunk_id or document_id:
        return f"{document_id}::{chunk_id}"
    return str(item.get("text") or item.get("content") or "").strip()[:240]


def _merge_layered_sources(target: Dict[str, List[Dict[str, Any]]], value: Any) -> None:
    if not isinstance(value, dict):
        return
    for layer_name, rows in value.items():
        if not isinstance(rows, list):
            continue
        layer = target.setdefault(str(layer_name), [])
        _merge_sources(layer, rows)


def _merge_graph(target: Dict[str, Any], value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, incoming in value.items():
        if key in {"edges", "nodes", "matched_entities"}:
            target[key] = _merge_dict_list(target.get(key), incoming)
        elif key == "text":
            merged_text = _merge_text(target.get("text"), incoming)
            if merged_text:
                target["text"] = merged_text
        elif key not in target or target.get(key) in (None, "", [], {}):
            target[key] = incoming


def _merge_dict_list(existing: Any, incoming: Any) -> List[Any]:
    output = list(existing) if isinstance(existing, list) else []
    if not isinstance(incoming, list):
        return output
    seen = {_stable_key(item) for item in output}
    for item in incoming:
        key = _stable_key(item)
        if key in seen:
            continue
        output.append(dict(item) if isinstance(item, dict) else item)
        seen.add(key)
    return output


def _merge_text(existing: Any, incoming: Any) -> str:
    current = str(existing or "").strip()
    addition = str(incoming or "").strip()
    if not current:
        return addition
    if not addition or addition in current:
        return current
    return f"{current}\n{addition}"


def _stable_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _serialize_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        output.append(
            {
                "chunk_id": item.get("chunk_id") or item.get("id"),
                "text": item.get("text") or item.get("content"),
                "document_id": item.get("document_id"),
                "document_title": item.get("document_title"),
                "document_group": item.get("document_group"),
                "source_type": item.get("source_type"),
                "domain": item.get("domain"),
                "retrieval_scope": item.get("retrieval_scope"),
                "sub_question": item.get("sub_question"),
                "fusion_score": item.get("fusion_score"),
                "fusion_method": item.get("fusion_method"),
                "agent_layer": item.get("agent_layer"),
            }
        )
    return output


def _serialize_graph_sources(graph_sources: Dict[str, Any]) -> Dict[str, Any]:
    graph = graph_sources or {}
    edges = list(graph.get("edges") or [])
    nodes = list(graph.get("nodes") or [])
    matched_entities = list(graph.get("matched_entities") or [])
    text = str(graph.get("text") or "").strip()
    return {
        "used": bool(text or edges),
        "text": text,
        "matched_entities": matched_entities,
        "nodes": nodes,
        "edges": edges,
        "skipped_reason": graph.get("skipped_reason"),
    }


def _extract_query_terms(text: str) -> set[str]:
    return {term.lower() for term in _WORD_PATTERN.findall(str(text or "")) if term.lower() not in _STOP_WORDS}


def _split_sentences(text: str) -> List[str]:
    sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")):
        cleaned = sentence.strip()
        if cleaned:
            sentences.append(cleaned)
    return sentences


def _truncate_words(text: str, limit: int) -> str:
    words = str(text or "").split()
    if len(words) <= limit:
        return str(text or "").strip()
    return " ".join(words[:limit]).rstrip() + "..."


def _claude_answering_available() -> bool:
    try:
        from rag.claude_answering import claude_answering_available

        return bool(claude_answering_available())
    except Exception:
        return False


def _openai_answering_available() -> bool:
    try:
        from rag.openai_answering import openai_answering_available

        return bool(openai_answering_available())
    except Exception:
        return False


__all__ = ["AgentRunner", "agent_result_to_payload", "stream_agent_run"]
