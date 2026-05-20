"""ESG metric taxonomy loader.

The taxonomy is the contract between extractor (what to look for), normalizer
(what unit to convert to), and store (what id to write). Loaded once at startup
and held in memory; re-loaded only when the YAML mtime changes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class MetricSpec:
    metric_id: str
    display_name_en: str
    display_name_zh: str
    canonical_unit: str
    category: str
    description: str
    framework_refs: List[str]
    aliases: List[str]
    scope_qualifiers: Optional[List[str]]
    expected_min: float
    expected_max: float

    def alias_set(self) -> List[str]:
        return [a.lower() for a in self.aliases]


@dataclass
class Taxonomy:
    version: str
    metrics: Dict[str, MetricSpec] = field(default_factory=dict)

    def get(self, metric_id: str) -> Optional[MetricSpec]:
        return self.metrics.get(metric_id)

    def all_metric_ids(self) -> List[str]:
        return list(self.metrics.keys())

    def is_value_in_expected_range(self, metric_id: str, value: float) -> bool:
        spec = self.get(metric_id)
        if spec is None:
            return False
        return spec.expected_min <= value <= spec.expected_max


_CACHE_LOCK = threading.Lock()
_CACHED: Dict[str, dict] = {}


def _build(metric_id: str, raw: dict) -> MetricSpec:
    display = raw.get("display_name") or {}
    expected = raw.get("expected_magnitude") or {}
    return MetricSpec(
        metric_id=metric_id,
        display_name_en=str(display.get("en") or metric_id),
        display_name_zh=str(display.get("zh") or display.get("en") or metric_id),
        canonical_unit=str(raw.get("canonical_unit") or ""),
        category=str(raw.get("category") or "uncategorized"),
        description=str(raw.get("description") or ""),
        framework_refs=list(raw.get("framework_refs") or []),
        aliases=list(raw.get("aliases") or []),
        scope_qualifiers=raw.get("scope_qualifiers"),
        expected_min=float(expected.get("min", 0.0)),
        expected_max=float(expected.get("max", float("inf"))),
    )


def load_taxonomy(path: str | Path) -> Taxonomy:
    """Load taxonomy from YAML, cached by mtime."""
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {resolved}")
    mtime = resolved.stat().st_mtime_ns
    cache_key = str(resolved)

    with _CACHE_LOCK:
        cached = _CACHED.get(cache_key)
        if cached and cached["mtime"] == mtime:
            return cached["taxonomy"]
        with resolved.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        version = str(raw.get("taxonomy_version") or "unversioned")
        metrics_raw = raw.get("metrics") or {}
        metrics = {mid: _build(mid, body) for mid, body in metrics_raw.items()}
        taxonomy = Taxonomy(version=version, metrics=metrics)
        _CACHED[cache_key] = {"mtime": mtime, "taxonomy": taxonomy}
        return taxonomy
