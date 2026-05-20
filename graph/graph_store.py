"""Persist graph JSON to local disk."""

from __future__ import annotations

from pathlib import Path
from typing import Dict
import json


def save_graph(graph: Dict, path: str) -> None:
    """Save graph JSON to disk."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(graph, handle, ensure_ascii=False, indent=2)


def load_graph(path: str) -> Dict:
    """Load graph JSON from disk."""
    target = Path(path)
    with open(target, "r", encoding="utf-8") as handle:
        return json.load(handle)
