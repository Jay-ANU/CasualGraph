"""Phase 1 (WP1-C): give every user a personal workspace and file existing documents into matters.

For every user: ensure the personal organization "<name> 的工作区" and its default matter "未分类".
For every document registry entry with an ``owner_user_id``: attach it to that user's default
matter unless it already belongs to a matter. Idempotent. ``--dry-run`` runs the same single
transaction and rolls it back, so it prints exactly what a real run would do and writes nothing.

    python scripts/migrate_phase1_matters.py --dry-run
    python scripts/migrate_phase1_matters.py

The same migration is ``services.matters.migrate_existing_documents()`` for startup use.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import document_registry  # noqa: E402
from services import db as db_service  # noqa: E402
from services.matters import migrate_existing_documents  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="File existing documents into per-user default matters (Phase 1, WP1-C).")
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    args = parser.parse_args(argv)

    if not args.dry_run:
        # The schema the app creates at startup (users, matters, audit); idempotent.
        asyncio.run(db_service._init_auth_db())
    counts = migrate_existing_documents(dry_run=args.dry_run)

    mode = "dry run, nothing written" if args.dry_run else "applied"
    print(f"[migrate_phase1_matters] {mode}")
    print(f"[migrate_phase1_matters] auth db: {db_service._DB_PATH}")
    print(f"[migrate_phase1_matters] registry: {document_registry.DOCUMENT_REGISTRY_FILE}")
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
