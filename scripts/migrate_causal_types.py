#!/usr/bin/env python3
"""One-shot migration for causal relation metadata and CAUSAL_LINK edges."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.causal_taxonomy import canonicalize_relation
from graph.neo4j_store import get_neo4j_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-canonicalize RELATIONSHIP edges and create CAUSAL_LINK edges.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing to Neo4j.")
    parser.add_argument("--batch-size", type=int, default=500, help="Number of relationships to update per batch.")
    args = parser.parse_args()

    store = get_neo4j_store()
    if store is None:
        print("Neo4j is not configured or unavailable.", file=sys.stderr)
        return 1

    store.setup_schema()
    rows = _load_relationships(store)
    updates = [_canonicalized_row(row) for row in rows]
    causal_count = sum(1 for row in updates if row["is_causal"])
    existing_keys = _load_causal_link_keys(store)
    new_count = sum(1 for row in updates if row["is_causal"] and _causal_key(row) not in existing_keys)
    merged_count = causal_count - new_count

    if args.dry_run:
        print(f"Would update {len(updates)} relationships, would create new={new_count}, merge existing={merged_count} causal links")
        return 0

    batch_size = max(1, int(args.batch_size or 500))
    updated = 0
    for start in range(0, len(updates), batch_size):
        batch = updates[start : start + batch_size]
        _write_batch(store, batch)
        updated += len(batch)
        print(f"Updated {updated}/{len(updates)} relationships")

    print(f"Updated {len(updates)} relationships, created new={new_count}, merged existing={merged_count} causal links")
    return 0


def _load_relationships(store) -> List[Dict]:
    def operation():
        with store._session() as session:
            return session.run(
                """
                MATCH (source:Entity)-[r:RELATIONSHIP]->(target:Entity)
                RETURN
                  elementId(r) AS rel_id,
                  source.id AS source_id,
                  target.id AS target_id,
                  coalesce(r.document_id, '') AS document_id,
                  coalesce(r.chunk_id, '') AS chunk_id,
                  coalesce(r.relation_type, r.type, 'related_to') AS relation_type,
                  coalesce(r.confidence, 0.75) AS confidence,
                  coalesce(r.evidence, '') AS evidence
                """
            ).data()

    return store._run_with_reconnect(operation)


def _load_causal_link_keys(store) -> set:
    def operation():
        with store._session() as session:
            rows = session.run(
                """
                MATCH ()-[c:CAUSAL_LINK]->()
                RETURN
                  coalesce(c.document_id, '') AS document_id,
                  coalesce(c.chunk_id, '') AS chunk_id,
                  coalesce(c.source_id, '') AS source_id,
                  coalesce(c.target_id, '') AS target_id,
                  coalesce(c.causal_type, '') AS causal_type
                """
            ).data()
            return {_causal_key(row) for row in rows}

    return store._run_with_reconnect(operation)


def _causal_key(row: Dict) -> tuple:
    return (
        str(row.get("document_id") or ""),
        str(row.get("chunk_id") or ""),
        str(row.get("source_id") or ""),
        str(row.get("target_id") or ""),
        str(row.get("causal_type") or ""),
    )


def _canonicalized_row(row: Dict) -> Dict:
    canonical = canonicalize_relation(row.get("relation_type") or "")
    return {
        **row,
        "causal_type": canonical["canonical"],
        "polarity": canonical["polarity"],
        "strength": canonical["strength"],
        "is_causal": canonical["is_causal"],
    }


def _write_batch(store, rows: List[Dict]) -> None:
    def operation():
        with store._session() as session:
            session.execute_write(_write_batch_tx, rows)

    store._run_with_reconnect(operation)


def _write_batch_tx(tx, rows: List[Dict]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (source:Entity {id: row.source_id})-[r:RELATIONSHIP]->(target:Entity {id: row.target_id})
        WHERE elementId(r) = row.rel_id
        SET r.causal_type = row.causal_type,
            r.polarity = row.polarity,
            r.strength = row.strength,
            r.is_causal = row.is_causal
        WITH source, target, row
        WHERE row.is_causal = true
        MERGE (source)-[c:CAUSAL_LINK {
          document_id: row.document_id,
          chunk_id: row.chunk_id,
          source_id: row.source_id,
          target_id: row.target_id,
          causal_type: row.causal_type
        }]->(target)
        SET c.polarity = row.polarity,
            c.strength = row.strength,
            c.confidence = row.confidence,
            c.evidence = row.evidence,
            c.relation_type = row.relation_type
        """,
        rows=rows,
    )


if __name__ == "__main__":
    raise SystemExit(main())
