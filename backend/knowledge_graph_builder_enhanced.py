# knowledge_graph_builder_enhanced.py
from __future__ import annotations
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from merge_utils import NodeStore

@dataclass
class Relation:
    source: str
    target: str
    predicate: str = "causes"
    confidence: float = 0.6
    evidence: str = ""
    source_surface: str = ""
    target_surface: str = ""
    source_span: Optional[List[int]] = None
    target_span: Optional[List[int]] = None

@dataclass
class Graph:
    nodes: List[Dict] = field(default_factory=list)
    edges: List[Dict] = field(default_factory=list)

class KnowledgeGraphBuilderEnhanced:
    def __init__(self, sim_threshold: float = 0.8):
        self.store = NodeStore(sim_threshold=sim_threshold)
        self.relations: List[Relation] = []

    def add_relation(self,
                     cause: str,
                     effect: str,
                     predicate: str = "causes",
                     confidence: float = 0.6,
                     evidence: str = "",
                     cause_span: Optional[List[int]] = None,
                     effect_span: Optional[List[int]] = None) -> None:
        sid = self.store.get_or_create(cause)
        tid = self.store.get_or_create(effect)
        self.relations.append(Relation(
            source=sid, target=tid, predicate=predicate,
            confidence=confidence, evidence=evidence,
            source_surface=cause, target_surface=effect,
            source_span=cause_span, target_span=effect_span
        ))

    def build(self) -> Graph:
        nodes = self.store.export()
        agg: Dict[tuple, Dict] = {}
        for r in self.relations:
            key = (r.source, r.target, r.predicate)
            if key not in agg:
                agg[key] = {
                    "source": r.source,
                    "target": r.target,
                    "predicate": r.predicate,
                    "count": 0,
                    "confidence_sum": 0.0,
                    "evidence": set(),
                    "spans": []
                }
            item = agg[key]
            item["count"] += 1
            item["confidence_sum"] += max(0.0, min(1.0, r.confidence))
            if r.evidence:
                item["evidence"].add(r.evidence)
            if r.source_span and r.target_span:
                item["spans"].append({"source_span": r.source_span, "target_span": r.target_span})

        edges: List[Dict] = []
        for key, item in agg.items():
            avg_conf = item["confidence_sum"] / float(item["count"] or 1)
            edges.append({
                "source": item["source"],
                "target": item["target"],
                "predicate": item["predicate"],
                "weight": round(avg_conf, 3),
                "count": item["count"],
                "evidence": sorted(item["evidence"])[:5],
                "spans": item["spans"][:10]
            })

        return Graph(nodes=nodes, edges=edges)

    def query(self, text: str, topk: int = 20) -> Dict[str, List[Dict]]:
        q = text.lower().strip()
        matched_nodes = []
        exported = self.store.export()
        for n in exported:
            if q in n["label"].lower() or any(q in a.lower() for a in n["aliases"]):
                matched_nodes.append(n)
                if len(matched_nodes) >= topk:
                    break
        matched_edges = []
        edges = self.build().edges
        for e in edges:
            if q in e["predicate"].lower():
                matched_edges.append(e)
                if len(matched_edges) >= topk:
                    break
        return {"nodes": matched_nodes, "edges": matched_edges}
