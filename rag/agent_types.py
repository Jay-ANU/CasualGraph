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
    # Historical API name. In AgentRunner this now means full plan/reflexion
    # rounds, not individual tool actions.
    max_steps: int
    deadline_seconds: int

    @property
    def max_rounds(self) -> int:
        return self.max_steps


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
    phase: str = "observation"
    plan_step: Optional[int] = None
    plan: Optional[List[Dict[str, Any]]] = None
    reflexion: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "step": self.step,
            "stage": self.stage,
            "tool": self.tool,
            "status": self.status,
            "summary": self.summary,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "phase": self.phase,
        }
        if self.plan_step is not None:
            payload["plan_step"] = self.plan_step
        if self.plan is not None:
            payload["plan"] = self.plan
        if self.reflexion is not None:
            payload["reflexion"] = self.reflexion
        if self.meta:
            payload["meta"] = self.meta
        return payload


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
    reflexion: Dict[str, Any] = field(default_factory=dict)
