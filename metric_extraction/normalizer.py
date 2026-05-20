"""Unit normalization for extracted metric values.

Uses pint as the underlying engine. Adds custom aliases for ESG-specific
units (tCO2e, kgCO2e) that pint does not know natively. Values that cannot be
parsed are returned as-is with a `normalized=False` flag, leaving the row in
review queue rather than corrupting the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

try:
    import pint
except Exception:  # pragma: no cover
    pint = None


@dataclass
class NormalizationResult:
    value: float
    unit: str
    normalized: bool
    note: str = ""


_TONNE_ALIASES = {
    # CO2-equivalent forms — pint doesn't know "tCO2e" by default.
    "tco2e": ("tCO2e", 1.0),
    "t co2e": ("tCO2e", 1.0),
    "tonne co2e": ("tCO2e", 1.0),
    "tonnes co2e": ("tCO2e", 1.0),
    "tco2-eq": ("tCO2e", 1.0),
    "tco2eq": ("tCO2e", 1.0),
    "metric tons co2e": ("tCO2e", 1.0),
    "metric tonnes co2e": ("tCO2e", 1.0),
    "tco2": ("tCO2e", 1.0),  # treat plain CO2 tons as CO2e for v1; flag in note.
    "kgco2e": ("tCO2e", 1e-3),
    "kg co2e": ("tCO2e", 1e-3),
    "mtco2e": ("tCO2e", 1e6),       # M = mega = million
    "mt co2e": ("tCO2e", 1e6),
    "million tonnes co2e": ("tCO2e", 1e6),
    "million tons co2e": ("tCO2e", 1e6),
    "百万吨二氧化碳当量": ("tCO2e", 1e6),
    "万吨二氧化碳当量": ("tCO2e", 1e4),
    "千吨二氧化碳当量": ("tCO2e", 1e3),
    "吨二氧化碳当量": ("tCO2e", 1.0),
    "百万吨": ("tCO2e", 1e6),
    "万吨": ("tCO2e", 1e4),
    "千吨": ("tCO2e", 1e3),
    "吨": ("tCO2e", 1.0),
}

_ENERGY_ALIASES = {
    "mwh": ("MWh", 1.0),
    "kwh": ("MWh", 1e-3),
    "gwh": ("MWh", 1e3),
    "twh": ("MWh", 1e6),
    "gj": ("MWh", 1.0 / 3.6),
    "tj": ("MWh", 1000.0 / 3.6),
    "兆瓦时": ("MWh", 1.0),
    "千瓦时": ("MWh", 1e-3),
    "吉瓦时": ("MWh", 1e3),
}

_VOLUME_ALIASES = {
    "m3": ("m^3", 1.0),
    "m^3": ("m^3", 1.0),
    "立方米": ("m^3", 1.0),
    "千立方米": ("m^3", 1e3),
    "万立方米": ("m^3", 1e4),
    "百万立方米": ("m^3", 1e6),
    "megaliter": ("m^3", 1e3),
    "megaliters": ("m^3", 1e3),
    "ml": ("m^3", 1e3),
    "kiloliter": ("m^3", 1.0),
    "kiloliters": ("m^3", 1.0),
    "liter": ("m^3", 1e-3),
    "liters": ("m^3", 1e-3),
    "litres": ("m^3", 1e-3),
}

_COUNT_ALIASES = {
    "person": ("persons", 1.0),
    "persons": ("persons", 1.0),
    "people": ("persons", 1.0),
    "employees": ("persons", 1.0),
    "headcount": ("persons", 1.0),
    "人": ("persons", 1.0),
    "名": ("persons", 1.0),
    "万人": ("persons", 1e4),
    "千人": ("persons", 1e3),
}

_ALL_ALIASES = {**_TONNE_ALIASES, **_ENERGY_ALIASES, **_VOLUME_ALIASES, **_COUNT_ALIASES}


@lru_cache(maxsize=1)
def _ureg() -> Optional["pint.UnitRegistry"]:
    if pint is None:
        return None
    reg = pint.UnitRegistry()
    # Custom unit definitions for things pint doesn't ship with.
    try:
        reg.define("tCO2e = tonne")
    except Exception:
        pass
    return reg


def _alias_lookup(unit_string: str) -> Optional[tuple]:
    key = unit_string.strip().lower()
    if key in _ALL_ALIASES:
        return _ALL_ALIASES[key]
    # Strip common suffixes ("of CO2e", "(market-based)", parentheticals)
    cleaned = key.split("(")[0].strip()
    if cleaned in _ALL_ALIASES:
        return _ALL_ALIASES[cleaned]
    return None


def normalize(value: float, raw_unit: str, target_unit: str) -> NormalizationResult:
    """Convert (value, raw_unit) → target_unit. Returns NormalizationResult."""
    if value is None:
        return NormalizationResult(value=0.0, unit=target_unit, normalized=False, note="value is None")
    if not raw_unit:
        return NormalizationResult(value=float(value), unit=target_unit, normalized=False, note="raw_unit empty")

    # 1. Alias table first — covers ESG-specific oddities pint can't.
    alias = _alias_lookup(raw_unit)
    if alias is not None:
        canonical, factor = alias
        if canonical == target_unit:
            return NormalizationResult(value=float(value) * factor, unit=target_unit, normalized=True)

    # 2. Fall back to pint for general unit conversion (e.g. kg→t, kWh→MWh).
    ureg = _ureg()
    if ureg is None:
        return NormalizationResult(
            value=float(value),
            unit=raw_unit,
            normalized=False,
            note="pint not installed; install via `pip install pint`",
        )

    try:
        quantity = float(value) * ureg.parse_units(raw_unit)
        converted = quantity.to(target_unit)
        return NormalizationResult(value=float(converted.magnitude), unit=target_unit, normalized=True)
    except Exception as exc:
        return NormalizationResult(
            value=float(value),
            unit=raw_unit,
            normalized=False,
            note=f"pint could not convert {raw_unit!r} → {target_unit!r}: {type(exc).__name__}",
        )
