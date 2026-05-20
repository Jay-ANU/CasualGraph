# merge_utils.py
from __future__ import annotations
from typing import Dict, List, Optional
from normalize import normalize_term, slugify, similar

class NodeStore:
    def __init__(self, sim_threshold: float = 0.8):
        self.sim_threshold = sim_threshold
        self.nodes: Dict[str, Dict] = {}
        self._by_label: Dict[str, str] = {}

    def _find_similar_id(self, label: str) -> Optional[str]:
        key = label.lower().strip()
        if key in self._by_label:
            return self._by_label[key]
        for norm_label, nid in self._by_label.items():
            if similar(norm_label, key, self.sim_threshold):
                return nid
        return None

    def get_or_create(self, surface: str) -> str:
        if not surface:
            surface = "unknown"
        label = normalize_term(surface) or "unknown"
        nid = self._find_similar_id(label)
        if nid is not None:
            node = self.nodes[nid]
            node["aliases"].add(surface)
            return nid

        nid = slugify(label)
        base = nid
        i = 2
        while nid in self.nodes:
            nid = f"{base}-{i}"
            i += 1
        self.nodes[nid] = {
            "id": nid,
            "label": label,
            "aliases": set([surface])
        }
        self._by_label[label.lower()] = nid
        return nid

    def export(self) -> List[Dict]:
        out = []
        for node in self.nodes.values():
            out.append({
                "id": node["id"],
                "label": node["label"],
                "aliases": sorted(node["aliases"])
            })
        return out
