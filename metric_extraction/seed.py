"""Seed the metric store with a small mock dataset for end-to-end tests.

Use:
    python -m metric_extraction.seed --db /tmp/test_metrics.sqlite

The seeded data is fictitious; it exists only so the agent + eval harness can
exercise the tool path before real PDF ingestion has populated the real DB.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from metric_extraction.store import MetricRow, init_metric_store


_FIXTURE = [
    # ABC Corp — three years of GHG + energy + water
    ("ABC Corp", "ghg_scope1_emissions", 2021, 110000, "operational_control"),
    ("ABC Corp", "ghg_scope1_emissions", 2022, 105000, "operational_control"),
    ("ABC Corp", "ghg_scope1_emissions", 2023, 98000, "operational_control"),
    ("ABC Corp", "ghg_scope2_emissions", 2023, 75000, "market_based"),
    ("ABC Corp", "ghg_scope3_emissions", 2023, 1_200_000, None),
    ("ABC Corp", "energy_consumption", 2023, 850_000, None),
    ("ABC Corp", "water_withdrawal", 2023, 4_500_000, None),
    ("ABC Corp", "employee_count", 2023, 24_500, "global"),
    # XYZ Industries — for comparisons
    ("XYZ Industries", "ghg_scope1_emissions", 2023, 220000, "operational_control"),
    ("XYZ Industries", "ghg_scope2_emissions", 2023, 95000, "market_based"),
    ("XYZ Industries", "ghg_scope3_emissions", 2023, 2_800_000, None),
    ("XYZ Industries", "energy_consumption", 2023, 1_650_000, None),
    ("XYZ Industries", "water_withdrawal", 2023, 8_200_000, None),
    ("XYZ Industries", "employee_count", 2023, 51_000, "global"),
    # GreenTech — peer for comparison
    ("GreenTech", "ghg_scope1_emissions", 2023, 35000, "operational_control"),
    ("GreenTech", "ghg_scope2_emissions", 2023, 18000, "market_based"),
    ("GreenTech", "energy_consumption", 2023, 220_000, None),
    ("GreenTech", "employee_count", 2023, 6_200, "global"),
]


def seed(db_path: str | Path) -> int:
    store = init_metric_store(db_path)
    rows = [
        MetricRow(
            document_id=f"seed_{entity.replace(' ', '_').lower()}_{year}",
            chunk_id=f"seed_chunk_{idx:03d}",
            entity_hint=entity,
            metric_id=metric_id,
            value=float(value),
            unit=_canonical_unit(metric_id),
            raw_value=float(value),
            raw_unit=_canonical_unit(metric_id),
            year=year,
            year_qualifier="fiscal",
            scope_qualifier=scope,
            confidence=0.9,
            evidence_text=f"[SEED] {entity} reported {value} {_canonical_unit(metric_id)} for {metric_id} in {year}.",
            extractor_version="seed-v1",
            taxonomy_version="esg-v1.0.0",
        )
        for idx, (entity, metric_id, year, value, scope) in enumerate(_FIXTURE)
    ]
    return store.insert_many(rows)


def _canonical_unit(metric_id: str) -> str:
    if metric_id.startswith("ghg_"):
        return "tCO2e"
    if metric_id == "energy_consumption":
        return "MWh"
    if metric_id == "water_withdrawal":
        return "m^3"
    if metric_id == "employee_count":
        return "persons"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Path to the SQLite file to seed")
    args = parser.parse_args()
    inserted = seed(args.db)
    print(f"Seeded {inserted} rows into {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
