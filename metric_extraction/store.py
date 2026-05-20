"""SQLite store for extracted ESG metrics.

Schema is intentionally narrow and analytic-friendly so a future migration to
DuckDB is mechanical (just swap the connection driver). All values are stored
in canonical units; the pre-normalization (raw_value, raw_unit) is kept so we
can re-normalize after taxonomy or normalizer changes without re-running the
LLM extractor.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS esg_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    chunk_id TEXT,
    entity_id TEXT,
    entity_hint TEXT,
    metric_id TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    raw_value REAL,
    raw_unit TEXT,
    year INTEGER,
    year_qualifier TEXT,
    scope_qualifier TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    evidence_text TEXT,
    extractor_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, chunk_id, metric_id, year, scope_qualifier)
);
CREATE INDEX IF NOT EXISTS idx_metrics_lookup
    ON esg_metrics(entity_hint, metric_id, year);
CREATE INDEX IF NOT EXISTS idx_metrics_doc
    ON esg_metrics(document_id);
CREATE INDEX IF NOT EXISTS idx_metrics_metric_year
    ON esg_metrics(metric_id, year);
"""


@dataclass
class MetricRow:
    document_id: str
    metric_id: str
    value: float
    unit: str
    chunk_id: Optional[str] = None
    entity_id: Optional[str] = None
    entity_hint: Optional[str] = None
    raw_value: Optional[float] = None
    raw_unit: Optional[str] = None
    year: Optional[int] = None
    year_qualifier: Optional[str] = None
    scope_qualifier: Optional[str] = None
    confidence: float = 0.5
    evidence_text: Optional[str] = None
    extractor_version: str = "unknown"
    taxonomy_version: str = "unknown"

    def as_tuple(self) -> tuple:
        return (
            self.document_id,
            self.chunk_id,
            self.entity_id,
            self.entity_hint,
            self.metric_id,
            self.value,
            self.unit,
            self.raw_value,
            self.raw_unit,
            self.year,
            self.year_qualifier,
            self.scope_qualifier,
            self.confidence,
            self.evidence_text,
            self.extractor_version,
            self.taxonomy_version,
        )


_INSERT_SQL = """
INSERT OR REPLACE INTO esg_metrics (
    document_id, chunk_id, entity_id, entity_hint, metric_id,
    value, unit, raw_value, raw_unit, year, year_qualifier,
    scope_qualifier, confidence, evidence_text,
    extractor_version, taxonomy_version
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class MetricStore:
    """Thin SQLite wrapper. Connections are per-thread; writes are serialized."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._local = threading.local()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _conn(self) -> sqlite3.Connection:
        existing = getattr(self._local, "conn", None)
        if existing is None:
            existing = self._connect()
            self._local.conn = existing
        return existing

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self._conn()
        try:
            yield conn.cursor()
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def insert_many(self, rows: Iterable[MetricRow]) -> int:
        rows_list = list(rows)
        if not rows_list:
            return 0
        with self._lock, self.cursor() as cur:
            cur.executemany(_INSERT_SQL, [r.as_tuple() for r in rows_list])
            return cur.rowcount

    def query(
        self,
        *,
        metric_id: Optional[str] = None,
        entity_hint: Optional[str] = None,
        document_id: Optional[str] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        min_confidence: float = 0.0,
        scope_qualifier: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = ["confidence >= ?"]
        params: List[Any] = [min_confidence]
        if metric_id:
            clauses.append("metric_id = ?")
            params.append(metric_id)
        if entity_hint:
            clauses.append("LOWER(entity_hint) LIKE ?")
            params.append(f"%{entity_hint.lower()}%")
        if document_id:
            clauses.append("document_id = ?")
            params.append(document_id)
        if year_min is not None:
            clauses.append("year >= ?")
            params.append(year_min)
        if year_max is not None:
            clauses.append("year <= ?")
            params.append(year_max)
        if scope_qualifier:
            clauses.append("scope_qualifier = ?")
            params.append(scope_qualifier)

        sql = (
            "SELECT * FROM esg_metrics WHERE "
            + " AND ".join(clauses)
            + " ORDER BY year DESC, confidence DESC LIMIT ?"
        )
        params.append(int(limit))
        with self.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def delete_document(self, document_id: str) -> int:
        with self._lock, self.cursor() as cur:
            cur.execute("DELETE FROM esg_metrics WHERE document_id = ?", (document_id,))
            return cur.rowcount

    def count(self) -> int:
        with self.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM esg_metrics")
            return int(cur.fetchone()["n"])


_GLOBAL_STORE: Optional[MetricStore] = None
_GLOBAL_STORE_LOCK = threading.Lock()


def init_metric_store(path: Path | str) -> MetricStore:
    """Idempotent store initializer. Safe to call from multiple threads."""
    global _GLOBAL_STORE
    with _GLOBAL_STORE_LOCK:
        if _GLOBAL_STORE is None or str(_GLOBAL_STORE.path) != str(path):
            _GLOBAL_STORE = MetricStore(path)
        return _GLOBAL_STORE
