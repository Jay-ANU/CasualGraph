"""Controlled causal relation taxonomy for graph reasoning."""

from __future__ import annotations

from typing import Dict


CAUSAL_TYPES = {
    "causes": {"polarity": +1, "strength": "strong", "is_causal": True},
    "leads_to": {"polarity": +1, "strength": "strong", "is_causal": True},
    "results_in": {"polarity": +1, "strength": "strong", "is_causal": True},
    "contributes_to": {"polarity": +1, "strength": "weak", "is_causal": True},
    "affects": {"polarity": 0, "strength": "medium", "is_causal": True},
    "predicts": {"polarity": +1, "strength": "medium", "is_causal": True},
    "moderates": {"polarity": 0, "strength": "weak", "is_causal": True},
    "increases": {"polarity": +1, "strength": "medium", "is_causal": True},
    "drives": {"polarity": +1, "strength": "medium", "is_causal": True},
    "decreases": {"polarity": -1, "strength": "medium", "is_causal": True},
    "reduces": {"polarity": -1, "strength": "medium", "is_causal": True},
    "mitigates": {"polarity": -1, "strength": "medium", "is_causal": True},
    "prevents": {"polarity": -1, "strength": "strong", "is_causal": True},
    "correlates_with": {"polarity": 0, "strength": "weak", "is_causal": False},
    "related_to": {"polarity": 0, "strength": "weak", "is_causal": False},
    "mentions": {"polarity": 0, "strength": "weak", "is_causal": False},
    "part_of": {"polarity": 0, "strength": "weak", "is_causal": False},
}

RELATION_ALIASES = {
    "cause": "causes",
    "caused": "causes",
    "caused_by": "causes",
    "lead to": "leads_to",
    "lead_to": "leads_to",
    "result in": "results_in",
    "result_in": "results_in",
    "contribute": "contributes_to",
    "contribute_to": "contributes_to",
    "affect": "affects",
    "affects": "affects",
    "predict": "predicts",
    "predicts": "predicts",
    "moderate": "moderates",
    "moderates": "moderates",
    "increase": "increases",
    "raise": "increases",
    "boost": "increases",
    "decrease": "decreases",
    "lower": "decreases",
    "reduce": "reduces",
    "cut": "reduces",
    "lessen": "reduces",
    "mitigate": "mitigates",
    "prevent": "prevents",
    "avoid": "prevents",
    "correlate": "correlates_with",
    "associated_with": "correlates_with",
    "related": "related_to",
    "relates_to": "related_to",
    "mention": "mentions",
    "part of": "part_of",
    "subset_of": "part_of",
}


def canonicalize_relation(raw: str) -> Dict:
    """Return canonical causal metadata, falling back to related_to."""
    key = _normalize(raw)
    alias_map = {_normalize(alias): canonical for alias, canonical in RELATION_ALIASES.items()}

    if key in CAUSAL_TYPES:
        canonical = key
    elif key in alias_map:
        canonical = alias_map[key]
    else:
        canonical = next(
            (canonical for alias, canonical in alias_map.items() if alias and alias in key),
            "related_to",
        )

    meta = CAUSAL_TYPES[canonical]
    return {"canonical": canonical, **meta}


def _normalize(value: str) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")
