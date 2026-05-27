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
from rag.source_titles import display_document_title


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
    """Run a bounded evidence plan with reflexion-driven replanning."""

    def __init__(self, registry: Any, budget: AgentBudget) -> None:
        self.registry = registry
        self.budget = budget

    def run(
        self,
        question: str,
        reasoning_mode: str,
        history_block: str,
        answer_intent: str = "evidence",
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AgentRunResult:
        started = time.monotonic()
        mode = _normalize_reasoning_mode(reasoning_mode)
        pending = list(self._build_plan(question=question, reasoning_mode=mode))
        trace: List[AgentTraceStep] = []
        _emit_trace_step(
            trace,
            AgentTraceStep(
                step=1,
                stage="planning",
                tool=None,
                status="planned",
                summary=_plan_summary(pending),
                elapsed_ms=(time.monotonic() - started) * 1000,
                phase="plan",
                plan=_serialize_plan(pending),
            ),
            progress_callback,
        )
        sources: List[Dict[str, Any]] = []
        graph_sources: Dict[str, Any] = {}
        layered_sources: Dict[str, List[Dict[str, Any]]] = {}
        evidence_summaries: List[str] = []
        executed_steps = 0
        partial = False
        partial_reason: Optional[str] = None
        replanned_entities: set[str] = set()

        while pending:
            if executed_steps >= max(0, int(self.budget.max_steps)):
                partial = True
                partial_reason = "max_steps_reached"
                break
            if self._deadline_reached(started):
                partial = True
                partial_reason = "deadline_reached"
                break

            call = pending.pop(0)
            plan_step = executed_steps + 1
            stage = _stage_for_tool(call.tool)
            arguments = self._resolve_arguments(call, question=question, sources=sources, graph=graph_sources)
            thought_step = AgentTraceStep(
                step=len(trace) + 1,
                stage="planning",
                tool=call.tool,
                status="completed",
                summary=_react_thought_summary(call, arguments, plan_step=plan_step),
                elapsed_ms=(time.monotonic() - started) * 1000,
                phase="thought",
                plan_step=plan_step,
                meta=_react_meta(call, arguments),
            )
            _emit_trace_step(trace, thought_step, progress_callback)

            action_step = AgentTraceStep(
                step=len(trace) + 1,
                stage=stage,
                tool=call.tool,
                status="running",
                summary=_react_action_summary(call, arguments),
                elapsed_ms=(time.monotonic() - started) * 1000,
                phase="action",
                plan_step=plan_step,
                meta=_react_meta(call, arguments),
            )
            _emit_trace_step(trace, action_step, progress_callback)

            tool_started = time.monotonic()
            observation = self._call_tool(call.tool, arguments)
            executed_steps += 1
            tool_elapsed_ms = (time.monotonic() - tool_started) * 1000
            action_step.status = "completed" if observation.ok else "failed"
            action_step.elapsed_ms = tool_elapsed_ms
            action_step.meta = {
                **action_step.meta,
                "ok": bool(observation.ok),
                "error": observation.error,
            }

            _merge_sources(sources, observation.data.get("sources"))
            _merge_graph(graph_sources, observation.data.get("graph"))
            _merge_layered_sources(layered_sources, observation.data.get("layered_sources"))
            summary = _observation_summary(observation)
            if call.tool == "summarize_evidence":
                evidence_summary = str(observation.data.get("summary") or summary).strip()
                if evidence_summary:
                    evidence_summaries.append(evidence_summary)

            observation_step = AgentTraceStep(
                step=len(trace) + 1,
                stage=stage,
                tool=call.tool,
                status="completed" if observation.ok else "failed",
                summary=_react_observation_summary(observation, summary),
                elapsed_ms=tool_elapsed_ms,
                phase="observation",
                plan_step=plan_step,
                meta={
                    **_react_meta(call, arguments),
                    "ok": bool(observation.ok),
                    "error": observation.error,
                },
            )
            _emit_trace_step(trace, observation_step, progress_callback)

            if call.tool == "search_documents":
                replan_calls = self._build_reflexion_replan(
                    question=question,
                    reasoning_mode=mode,
                    sources=sources,
                    graph_sources=graph_sources,
                    pending=pending,
                    replanned_entities=replanned_entities,
                )
                if replan_calls:
                    for replan_call in replan_calls:
                        entity_key = _entity_key(str(replan_call.arguments.get("expected_entity") or ""))
                        if entity_key:
                            replanned_entities.add(entity_key)
                    replanning_step = AgentTraceStep(
                        step=len(trace) + 1,
                        stage="planning",
                        tool=None,
                        status="completed",
                        summary=_replan_summary(replan_calls),
                        elapsed_ms=(time.monotonic() - started) * 1000,
                        phase="replan",
                        plan=_serialize_plan(replan_calls),
                        reflexion={"status": "replanned_missing_entity_evidence"},
                    )
                    _emit_trace_step(trace, replanning_step, progress_callback)
                    pending = [*replan_calls, *pending]

            if pending and self._deadline_reached(started):
                partial = True
                partial_reason = "deadline_reached"
                break

        reflexion = self._build_reflexion_report(
            sources=sources,
            graph_sources=graph_sources,
            replanned_entities=replanned_entities,
        )
        if reflexion.get("missing_entities") and not partial:
            partial = True
            partial_reason = "missing_entity_evidence"
        reflexion_step = AgentTraceStep(
            step=len(trace) + 1,
            stage="partial" if partial else "completed",
            tool=None,
            status="completed",
            summary=_reflexion_summary(reflexion),
            elapsed_ms=(time.monotonic() - started) * 1000,
            phase="reflexion",
            reflexion=reflexion,
        )
        _emit_trace_step(trace, reflexion_step, progress_callback)

        answer, backend = _synthesize_answer(
            question=question,
            reasoning_mode=mode,
            history_block=history_block,
            sources=sources,
            graph_sources=graph_sources,
            layered_sources=layered_sources,
            evidence_summaries=evidence_summaries,
            answer_intent=answer_intent,
        )
        final_step = AgentTraceStep(
            step=len(trace) + 1,
            stage="partial" if partial else "completed",
            tool=None,
            status="completed",
            summary="Synthesized an answer from collected evidence." if sources or graph_sources else "No usable evidence was collected.",
            elapsed_ms=(time.monotonic() - started) * 1000,
            phase="final",
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
            reflexion=reflexion,
        )

    def _build_plan(self, question: str, reasoning_mode: str) -> List[AgentToolCall]:
        mode = _normalize_reasoning_mode(reasoning_mode)
        if mode == "deep":
            search_args = {"query": question, "strategy": "layered", "top_k": 8, "use_hyde": False}
            graph_args = {"question": question, "limit": 16, "max_triples": 16}
        else:
            search_args = {"query": question, "strategy": "hybrid", "top_k": 5, "use_hyde": False}
            graph_args = {"question": question, "limit": 8, "max_triples": 8}
        targets = _routing_targets(getattr(self.registry, "filters", None), question=question)
        if targets:
            search_calls = [_search_call_for_target(search_args, target) for target in targets]
            graph_targets = [target for target in targets if str(target.get("document_id") or "").strip()]
            if graph_targets:
                graph_slots = max(1, int(self.budget.max_steps) - len(search_calls) - 1)
                graph_calls = [_graph_call_for_target(graph_args, target) for target in graph_targets[:graph_slots]]
            else:
                graph_calls = [AgentToolCall(tool="get_graph_context", arguments=graph_args)]
        else:
            search_queries = _routing_sub_questions(getattr(self.registry, "filters", None)) or [question]
            search_calls = [
                AgentToolCall(tool="search_documents", arguments={**search_args, "query": search_query})
                for search_query in search_queries
            ]
            graph_calls = [AgentToolCall(tool="get_graph_context", arguments=graph_args)]
        return [
            *search_calls,
            *graph_calls,
            AgentToolCall(tool="summarize_evidence", arguments={}),
        ]

    def _build_reflexion_replan(
        self,
        *,
        question: str,
        reasoning_mode: str,
        sources: List[Dict[str, Any]],
        graph_sources: Dict[str, Any],
        pending: List[AgentToolCall],
        replanned_entities: set[str],
    ) -> List[AgentToolCall]:
        targets = _routing_targets(getattr(self.registry, "filters", None), question=question)
        if not targets:
            return []
        pending_entities = {
            _entity_key(str(call.arguments.get("expected_entity") or ""))
            for call in pending
            if call.tool == "search_documents"
        }
        if reasoning_mode == "deep":
            search_args = {"query": question, "strategy": "layered", "top_k": 8, "use_hyde": False}
        else:
            search_args = {"query": question, "strategy": "hybrid", "top_k": 5, "use_hyde": False}
        output: List[AgentToolCall] = []
        for target in _missing_targets(targets, sources=sources, graph_sources=graph_sources):
            entity_key = _entity_key(target.get("entity") or "")
            if not entity_key or entity_key in pending_entities or entity_key in replanned_entities:
                continue
            replan_target = dict(target)
            replan_target["query"] = _replan_query(question=question, entity=str(target.get("entity") or ""))
            call = _search_call_for_target(search_args, replan_target)
            call.arguments["replan_reason"] = "missing_entity_evidence"
            output.append(call)
        return output

    def _build_reflexion_report(
        self,
        *,
        sources: List[Dict[str, Any]],
        graph_sources: Dict[str, Any],
        replanned_entities: set[str],
    ) -> Dict[str, Any]:
        targets = _routing_targets(getattr(self.registry, "filters", None), question="")
        if not targets:
            return {"status": "not_required", "replanned_entities": []}
        missing = _missing_targets(targets, sources=sources, graph_sources=graph_sources)
        missing_entities = [str(item.get("entity") or "").strip().lower() for item in missing if str(item.get("entity") or "").strip()]
        covered_entities = [
            str(item.get("entity") or "").strip().lower()
            for item in targets
            if str(item.get("entity") or "").strip().lower() not in missing_entities
        ]
        return {
            "status": "complete" if not missing_entities else "partial_entity_coverage",
            "covered_entities": covered_entities,
            "missing_entities": missing_entities,
            "replanned_entities": sorted(replanned_entities),
        }

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
        "reflexion": dict(result.reflexion or {}),
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
    answer_intent: str = "evidence",
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
                answer_intent=answer_intent,
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
    answer_intent: str = "evidence",
) -> Tuple[str, str]:
    normalized_answer_intent = _normalize_answer_intent(answer_intent)
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
                answer_intent=normalized_answer_intent,
            )
            if answer:
                backend = "claude_deep+graph" if graph_text else "claude_deep"
                return _apply_hybrid_synthesis_fallback(
                    answer=answer,
                    backend=backend,
                    answer_intent=normalized_answer_intent,
                    question=question,
                    sources=sources,
                    graph_sources=graph_sources,
                    evidence_summaries=evidence_summaries,
                )
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
                allow_speculation=normalized_answer_intent == "hybrid",
                answer_intent=normalized_answer_intent,
            )
            if answer:
                backend = "openai+graph" if graph_text else "openai"
                return _apply_hybrid_synthesis_fallback(
                    answer=answer,
                    backend=backend,
                    answer_intent=normalized_answer_intent,
                    question=question,
                    sources=sources,
                    graph_sources=graph_sources,
                    evidence_summaries=evidence_summaries,
                )
        except Exception as exc:
            print(f"[agent_runner] OpenAI synthesis failed: {type(exc).__name__}: {exc}")

    return _extractive_fallback_answer(
        question=question,
        sources=sources,
        graph_sources=graph_sources,
        evidence_summaries=evidence_summaries,
    ), "extractive_fallback"


def _normalize_answer_intent(value: str) -> str:
    normalized = str(value or "evidence").strip().lower()
    return normalized if normalized in {"evidence", "hybrid", "general"} else "evidence"


def _is_insufficient_context_answer(answer: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(answer or "").strip()).strip()
    if not normalized:
        return False
    if normalized == INSUFFICIENT_CONTEXT_ANSWER:
        return True
    return normalized.startswith(INSUFFICIENT_CONTEXT_ANSWER) and len(normalized) <= len(INSUFFICIENT_CONTEXT_ANSWER) + 40


def _apply_hybrid_synthesis_fallback(
    *,
    answer: str,
    backend: str,
    answer_intent: str,
    question: str,
    sources: List[Dict[str, Any]],
    graph_sources: Dict[str, Any],
    evidence_summaries: List[str],
) -> Tuple[str, str]:
    if answer_intent != "hybrid" or not _is_insufficient_context_answer(answer):
        return answer, backend
    return (
        _hybrid_evidence_limit_answer(
            question=question,
            sources=sources,
            graph_sources=graph_sources,
            evidence_summaries=evidence_summaries,
        ),
        f"{backend}+hybrid_fallback",
    )


def _hybrid_evidence_limit_answer(
    *,
    question: str,
    sources: List[Dict[str, Any]],
    graph_sources: Dict[str, Any],
    evidence_summaries: List[str],
) -> str:
    extractive = _extractive_fallback_answer(
        question=question,
        sources=sources,
        graph_sources=graph_sources,
        evidence_summaries=evidence_summaries,
    )
    labels = _source_labels(sources)
    if _contains_cjk(question):
        source_note = f" 当前证据集中在：{', '.join(labels)}。" if labels else ""
        evidence_line = "" if extractive == INSUFFICIENT_CONTEXT_ANSWER else f"\n\n可用证据：{extractive}"
        return (
            f"当前证据覆盖不足，不能做完整的跨报告比较。{source_note}".strip()
            + evidence_line
            + "\n\n不确定性：目前检索结果没有覆盖足够多公司或报告的可比指标。"
            "较稳妥的比较应分别核对气候转型风险暴露、减排目标、治理责任、供应链风险、资本投入和时间线；"
            "缺少这些字段时，只能给出有限证据下的结论，不能把它当作全量报告比较。"
        )
    source_note = f" The collected evidence is concentrated in: {', '.join(labels)}." if labels else ""
    evidence_line = "" if extractive == INSUFFICIENT_CONTEXT_ANSWER else f"\n\nAvailable evidence: {extractive}"
    return (
        f"The collected evidence is not broad enough for a complete all-report comparison.{source_note}"
        + evidence_line
        + "\n\nUncertainty: the retrieved sources do not cover enough comparable companies or report sections. "
        "A defensible comparison should separately check climate-transition risk exposure, emissions targets, governance ownership, supply-chain risk, capital allocation, and timelines. "
        "Where those fields are missing, the conclusion should be treated as limited to the retrieved evidence rather than a full cross-report finding."
    )


def _source_labels(sources: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    labels: List[str] = []
    seen = set()
    for item in sources:
        if not isinstance(item, dict):
            continue
        title = display_document_title(item)
        chunk = str(item.get("chunk_id") or item.get("id") or "").strip()
        label = f"{title} · {chunk}" if chunk else title
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
        if len(labels) >= limit:
            break
    return labels


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


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


def _serialize_plan(calls: List[AgentToolCall]) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    for index, call in enumerate(calls or [], start=1):
        arguments = dict(call.arguments or {})
        item: Dict[str, Any] = {
            "plan_step": index,
            "tool": call.tool,
            "stage": _stage_for_tool(call.tool),
        }
        for key in ("query", "strategy", "top_k", "expected_entity", "document_ids", "preferred_document_id", "replan_reason"):
            value = arguments.get(key)
            if value not in (None, "", [], {}):
                item[key] = value
        plan.append(item)
    return plan


def _plan_summary(calls: List[AgentToolCall]) -> str:
    count = len(calls or [])
    if count == 1:
        return "Planned 1 evidence step before execution."
    return f"Planned {count} evidence steps before execution."


def _react_meta(call: AgentToolCall, arguments: Dict[str, Any]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"tool": call.tool}
    for key in ("query", "strategy", "top_k", "expected_entity", "document_ids", "preferred_document_id", "replan_reason"):
        value = arguments.get(key)
        if value not in (None, "", [], {}):
            meta[key] = value
    return meta


def _react_thought_summary(call: AgentToolCall, arguments: Dict[str, Any], *, plan_step: int) -> str:
    expected_entity = str(arguments.get("expected_entity") or "").strip()
    if call.tool == "search_documents" and expected_entity:
        return f"Thought: verify targeted report evidence for {expected_entity} before using it in the answer."
    if call.tool == "search_documents":
        return "Thought: search the selected report scope for evidence relevant to the question."
    if call.tool in {"get_graph_context", "query_neo4j"}:
        return "Thought: cross-check whether graph context can strengthen or correct the retrieved evidence."
    if call.tool == "summarize_evidence":
        return "Thought: consolidate the collected observations before drafting the answer."
    return f"Thought: choose the next action for evidence plan step {plan_step}."


def _react_action_summary(call: AgentToolCall, arguments: Dict[str, Any]) -> str:
    expected_entity = str(arguments.get("expected_entity") or "").strip()
    if expected_entity:
        return f"Action: {call.tool} for {expected_entity}."
    return f"Action: {call.tool}."


def _react_observation_summary(observation: AgentToolObservation, fallback: str) -> str:
    return fallback or _observation_summary(observation)


def _reflexion_summary(reflexion: Dict[str, Any]) -> str:
    missing = [str(item).strip() for item in (reflexion or {}).get("missing_entities") or [] if str(item).strip()]
    if missing:
        return f"Reflexion: evidence is still missing for {', '.join(missing)}."
    status = str((reflexion or {}).get("status") or "").strip()
    if status == "not_required":
        return "Reflexion: no explicit multi-entity coverage check was required."
    return "Reflexion: evidence coverage satisfies the current plan."


def _routing_sub_questions(filters: Any) -> List[str]:
    if not isinstance(filters, dict):
        return []
    hint = filters.get("routing_hint")
    if not isinstance(hint, dict) or not hint.get("needs_agent"):
        return []
    cleaned: List[str] = []
    for value in hint.get("sub_questions") or []:
        query = str(value or "").strip()
        if not query or query in cleaned:
            continue
        cleaned.append(query)
        if len(cleaned) >= 4:
            break
    return cleaned


def _routing_targets(filters: Any, *, question: str) -> List[Dict[str, Any]]:
    if not isinstance(filters, dict):
        return []
    hint = filters.get("routing_hint")
    if not isinstance(hint, dict) or not hint.get("needs_agent"):
        return []
    entities = _clean_labels(hint.get("entities"))
    if not entities:
        return []
    document_ids = _clean_labels(hint.get("target_document_ids"))
    sub_questions = _routing_sub_questions(filters)
    targets: List[Dict[str, Any]] = []
    for index, entity in enumerate(entities[:4]):
        document_id = _document_id_for_entity(index=index, entity=entity, entities=entities, document_ids=document_ids)
        targets.append(
            {
                "entity": entity,
                "document_id": document_id,
                "query": _query_for_entity(entity=entity, sub_questions=sub_questions, question=question),
            }
        )
    return targets


def _document_id_for_entity(*, index: int, entity: str, entities: List[str], document_ids: List[str]) -> str:
    if not document_ids:
        return ""
    if len(document_ids) == len(entities) and index < len(document_ids):
        return document_ids[index]
    if len(document_ids) == 1 and len(entities) == 1:
        return document_ids[0]
    entity_tokens = set(_entity_tokens(entity))
    if not entity_tokens:
        return ""
    for document_id in document_ids:
        document_tokens = set(_entity_tokens(document_id.replace("_", " ").replace("-", " ")))
        if entity_tokens and entity_tokens.issubset(document_tokens):
            return document_id
    return ""


def _search_call_for_target(search_args: Dict[str, Any], target: Dict[str, Any]) -> AgentToolCall:
    arguments = {**search_args, "query": str(target.get("query") or search_args.get("query") or "").strip()}
    entity = str(target.get("entity") or "").strip()
    document_id = str(target.get("document_id") or "").strip()
    if entity:
        arguments["expected_entity"] = entity
    if document_id:
        arguments["document_ids"] = [document_id]
        arguments["preferred_document_id"] = document_id
    return AgentToolCall(tool="search_documents", arguments=arguments)


def _graph_call_for_target(graph_args: Dict[str, Any], target: Dict[str, Any]) -> AgentToolCall:
    entity = str(target.get("entity") or "").strip()
    document_id = str(target.get("document_id") or "").strip()
    target_query = str(target.get("query") or "").strip()
    if entity and target_query:
        question = f"Find graph relationships specifically for {entity}. {target_query}"
    elif entity:
        question = f"Find graph relationships specifically for {entity}."
    else:
        question = target_query or str(graph_args.get("question") or "").strip()
    arguments = {**graph_args, "question": question}
    if entity:
        arguments["expected_entity"] = entity
    if document_id:
        arguments["document_ids"] = [document_id]
        arguments["preferred_document_id"] = document_id
    return AgentToolCall(tool="get_graph_context", arguments=arguments)


def _query_for_entity(*, entity: str, sub_questions: List[str], question: str) -> str:
    entity_key = _entity_key(entity)
    for sub_question in sub_questions:
        if entity_key and _entity_key(entity) in _entity_key(sub_question):
            return sub_question
    base = str(question or "").strip()
    if base:
        return f"Find report evidence specifically for {entity}. {base}"
    return f"Find report evidence specifically for {entity}."


def _replan_query(*, question: str, entity: str) -> str:
    base = str(question or "").strip()
    if base:
        return f"Re-check retrieved report evidence specifically for {entity}. {base}"
    return f"Re-check retrieved report evidence specifically for {entity}."


def _missing_targets(
    targets: List[Dict[str, Any]],
    *,
    sources: List[Dict[str, Any]],
    graph_sources: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [
        target
        for target in targets
        if not _target_has_coverage(target, sources=sources, graph_sources=graph_sources)
    ]


def _target_has_coverage(
    target: Dict[str, Any],
    *,
    sources: List[Dict[str, Any]],
    graph_sources: Dict[str, Any],
) -> bool:
    document_id = str(target.get("document_id") or "").strip()
    entity = str(target.get("entity") or "").strip()
    if document_id:
        for source in sources or []:
            if isinstance(source, dict) and str(source.get("document_id") or "").strip() == document_id:
                return True
    if not entity:
        return False
    blob = _entity_blob(sources=sources, graph_sources=graph_sources)
    entity_tokens = set(_entity_tokens(entity))
    if not entity_tokens:
        return False
    entity_phrase = " ".join(_entity_tokens(entity))
    if entity_phrase and entity_phrase in blob:
        return True
    return entity_tokens.issubset(set(_entity_tokens(blob)))


def _entity_blob(*, sources: List[Dict[str, Any]], graph_sources: Dict[str, Any]) -> str:
    parts: List[str] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        parts.extend(
            [
                str(source.get("document_id") or ""),
                str(source.get("document_title") or ""),
                str(source.get("title") or ""),
                str(source.get("text") or source.get("content") or ""),
            ]
        )
    if isinstance(graph_sources, dict):
        parts.append(str(graph_sources.get("text") or ""))
    return " ".join(parts).lower()


def _clean_labels(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    output: List[str] = []
    seen = set()
    for item in value:
        label = str(item or "").strip()
        key = label.lower()
        if not label or key in seen:
            continue
        output.append(label)
        seen.add(key)
    return output


def _entity_key(value: str) -> str:
    return " ".join(_entity_tokens(value))


def _entity_tokens(value: str) -> List[str]:
    return [term.lower() for term in _WORD_PATTERN.findall(str(value or "")) if len(term) >= 2]


def _replan_summary(calls: List[AgentToolCall]) -> str:
    entities = [
        str(call.arguments.get("expected_entity") or "").strip()
        for call in calls
        if str(call.arguments.get("expected_entity") or "").strip()
    ]
    if entities:
        return f"Reflexion found missing entity evidence; replanning targeted search for: {', '.join(entities)}."
    return "Reflexion found missing evidence; replanning targeted search."


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
                "document_title": display_document_title(item),
                "source": item.get("source"),
                "document_group": item.get("document_group"),
                "source_type": item.get("source_type"),
                "domain": item.get("domain"),
                "retrieval_scope": item.get("retrieval_scope"),
                "sub_question": item.get("sub_question"),
                "fusion_score": item.get("fusion_score"),
                "fusion_method": item.get("fusion_method"),
                "relevance_score": item.get("relevance_score"),
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
