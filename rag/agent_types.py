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
