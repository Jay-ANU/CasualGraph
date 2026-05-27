"""Optional Neo4j persistence for the root ESG graph pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
import json
import re
import socket
from urllib.parse import urlparse

from configs.settings import (
    NEO4J_AUTO_SYNC,
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    neo4j_configured,
)
from graph.causal_taxonomy import canonicalize_relation
from graph.graph_utils import normalize_entity_name

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ClientError, ServiceUnavailable, SessionExpired
except Exception:
    GraphDatabase = None
    ClientError = ServiceUnavailable = SessionExpired = Exception


_NEO4J_STORE = None


class Neo4jConnectionError(RuntimeError):
    """Raised when Neo4j is required but the configured instance is unreachable."""


def _neo4j_host_from_uri(uri: str) -> str:
    parsed = urlparse(uri)
    return parsed.hostname or ""


def assert_neo4j_ready() -> None:
    """Fail fast when the configured Neo4j instance cannot be reached."""
    if not neo4j_sdk_available():
        raise Neo4jConnectionError("Neo4j Python SDK is not installed.")
    if not neo4j_configured():
        raise Neo4jConnectionError("Neo4j is not configured. Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD.")

    host = _neo4j_host_from_uri(NEO4J_URI)
    if not host:
        raise Neo4jConnectionError(
            f"Invalid NEO4J_URI: {NEO4J_URI!r}. Use the full Aura connection URI, for example neo4j+s://<id>.databases.neo4j.io."
        )

    try:
        socket.getaddrinfo(host, 7687)
    except socket.gaierror as exc:
        raise Neo4jConnectionError(
            f"Cannot resolve Neo4j host {host}:7687. Update NEO4J_URI to the current Aura connection URI for the ESG instance, then restart the backend."
        ) from exc

    store = get_neo4j_store()
    if store is None:
        raise Neo4jConnectionError("Neo4j is unavailable with the current configuration.")
    try:
        status = store.ping()
    except Exception as exc:
        raise Neo4jConnectionError(f"Neo4j connectivity check failed for database {NEO4J_DATABASE}: {exc}") from exc
    if not status.get("connected"):
        raise Neo4jConnectionError(f"Neo4j connectivity check failed for database {NEO4J_DATABASE}.")


def neo4j_sdk_available() -> bool:
    return GraphDatabase is not None


def neo4j_enabled() -> bool:
    return neo4j_sdk_available() and neo4j_configured()


def get_neo4j_store():
    global _NEO4J_STORE
    if _NEO4J_STORE is not None:
        return _NEO4J_STORE
    if not neo4j_enabled():
        return None
    _NEO4J_STORE = Neo4jGraphStore(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
    )
    return _NEO4J_STORE


def maybe_sync_to_neo4j(
    document: Dict[str, Any],
    chunks: List[Dict[str, Any]],
    extractions: List[Dict[str, Any]],
    graph: Dict[str, Any],
) -> Dict[str, Any]:
    """Sync into Neo4j when configured, otherwise return a structured skip status."""
    if not NEO4J_AUTO_SYNC:
        return {"enabled": False, "synced": False, "reason": "auto_sync_disabled"}
    try:
        store = get_neo4j_store()
    except Exception as exc:
        return {"enabled": True, "synced": False, "reason": f"{type(exc).__name__}: {exc}"}
    if store is None:
        if not neo4j_sdk_available():
            return {"enabled": False, "synced": False, "reason": "neo4j_sdk_missing"}
        if not neo4j_configured():
            return {"enabled": False, "synced": False, "reason": "neo4j_not_configured"}
        return {"enabled": False, "synced": False, "reason": "neo4j_unavailable"}
    try:
        return store.sync_document(document=document, chunks=chunks, extractions=extractions, graph=graph)
    except Exception as exc:
        return {"enabled": True, "synced": False, "reason": f"{type(exc).__name__}: {exc}"}


class Neo4jGraphStore:
    """Small Neo4j store for document, chunk, entity, and relation persistence."""

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver = self._create_driver()

    def _create_driver(self):
        driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            keep_alive=True,
            max_connection_lifetime=1800,
            liveness_check_timeout=30,
        )
        driver.verify_connectivity()
        return driver

    def _reset_driver(self) -> None:
        try:
            self.driver.close()
        except Exception:
            pass
        self.driver = self._create_driver()

    def _session(self):
        return self.driver.session(database=self.database)

    def _run_with_reconnect(self, operation):
        try:
            return operation()
        except (ServiceUnavailable, SessionExpired) as exc:
            message = str(exc).lower()
            if "defunct connection" not in message and "failed to read from defunct connection" not in message:
                raise
            self._reset_driver()
            return operation()

    def close(self) -> None:
        self.driver.close()

    def ping(self) -> Dict[str, Any]:
        def operation():
            with self._session() as session:
                return session.run("RETURN 1 AS ok").single()

        record = self._run_with_reconnect(operation)
        return {"enabled": True, "connected": bool(record and record["ok"] == 1), "database": self.database}

    def setup_schema(self) -> None:
        def _ensure_fulltext_index(session) -> None:
            try:
                session.run(
                    """
                    CREATE FULLTEXT INDEX entity_name_fulltext IF NOT EXISTS
                    FOR (e:Entity) ON EACH [e.name, e.normalized_name, e.description]
                    """
                )
            except ClientError:
                session.run(
                    """
                    CALL db.index.fulltext.createNodeIndex(
                      "entity_name_fulltext",
                      ["Entity"],
                      ["name", "normalized_name", "description"]
                    )
                    """
                )

        def operation():
            with self._session() as session:
                session.run("CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
                session.run("CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE")
                session.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
                session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)")
                session.run("CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)")
                session.run("CREATE INDEX chunk_section IF NOT EXISTS FOR (c:Chunk) ON (c.section)")
                session.run("CREATE INDEX document_title IF NOT EXISTS FOR (d:Document) ON (d.title)")
                session.run("CREATE INDEX causal_type IF NOT EXISTS FOR ()-[c:CAUSAL_LINK]-() ON (c.causal_type)")
                _ensure_fulltext_index(session)

        try:
            self._run_with_reconnect(operation)
        except Exception as exc:
            print(f"[neo4j.schema] setup skipped: {type(exc).__name__}: {exc}")

    def sync_document(
        self,
        document: Dict[str, Any],
        chunks: List[Dict[str, Any]],
        extractions: List[Dict[str, Any]],
        graph: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.setup_schema()

        document_row = self._document_row(document)
        chunk_rows = [self._chunk_row(document_row["id"], chunk) for chunk in chunks]
        entity_rows, mention_rows = self._entity_rows(document_row["id"], chunks, extractions)
        relation_rows = self._relation_rows(document_row["id"], extractions)

        def operation():
            with self._session() as session:
                session.execute_write(self._upsert_document, document_row)
                session.execute_write(self._clear_document_scope, document_row["id"])
                if chunk_rows:
                    session.execute_write(self._upsert_chunks, document_row["id"], chunk_rows)
                if entity_rows:
                    session.execute_write(self._upsert_entities, document_row["id"], entity_rows)
                if mention_rows:
                    session.execute_write(self._upsert_mentions, mention_rows)
                if relation_rows:
                    session.execute_write(self._upsert_relations, relation_rows)

        self._run_with_reconnect(operation)

        return {
            "enabled": True,
            "synced": True,
            "document_id": document_row["id"],
            "chunks_synced": len(chunk_rows),
            "entities_synced": len(entity_rows),
            "relations_synced": len(relation_rows),
            "database": self.database,
            "graph_node_count": len(graph.get("nodes", []) or []),
            "graph_edge_count": len(graph.get("edges", []) or []),
        }

    def delete_document(self, document_id: str) -> Dict[str, Any]:
        document_id = str(document_id or "").strip()
        if not document_id:
            return {"enabled": True, "deleted": False, "reason": "missing_document_id"}

        def operation():
            with self._session() as session:
                session.execute_write(self._clear_document_scope, document_id)
                result = session.run(
                    """
                    MATCH (d:Document {id: $document_id})
                    DETACH DELETE d
                    RETURN count(d) AS deleted
                    """,
                    document_id=document_id,
                )
                record = result.single()
                return int(record["deleted"] or 0) if record else 0

        deleted = self._run_with_reconnect(operation)
        return {"enabled": True, "deleted": deleted > 0, "document_id": document_id, "database": self.database}

    def get_stats(self) -> Dict[str, Any]:
        def operation():
            with self._session() as session:
                counts = {
                    "document_count": session.run("MATCH (d:Document) RETURN count(d) AS count").single()["count"],
                    "chunk_count": session.run("MATCH (c:Chunk) RETURN count(c) AS count").single()["count"],
                    "entity_count": session.run("MATCH (e:Entity) RETURN count(e) AS count").single()["count"],
                    "relation_count": session.run("MATCH ()-[r:RELATIONSHIP]->() RETURN count(r) AS count").single()["count"],
                    "mention_count": session.run("MATCH ()-[m:MENTIONED_IN]->() RETURN count(m) AS count").single()["count"],
                }
                top_relation_types = session.run(
                    """
                    MATCH ()-[r:RELATIONSHIP]->()
                    RETURN r.relation_type AS relation_type, count(*) AS count
                    ORDER BY count DESC
                    LIMIT 10
                    """
                ).data()
                return counts, top_relation_types

        counts, top_relation_types = self._run_with_reconnect(operation)
        return {
            "enabled": True,
            "database": self.database,
            "counts": counts,
            "top_relation_types": top_relation_types,
        }

    def get_entity(self, entity: str, limit: int = 20) -> Dict[str, Any]:
        def operation():
            with self._session() as session:
                record = session.run(
                    """
                    MATCH (e:Entity)
                    WHERE e.id = $entity OR toLower(e.name) = toLower($entity) OR toLower(e.normalized_name) = toLower($entity)
                    RETURN e
                    LIMIT 1
                    """,
                    entity=normalize_entity_name(entity),
                ).single()
                if not record:
                    return None, []

                node = dict(record["e"])
                neighbors = session.run(
                    """
                    MATCH (e:Entity)
                    WHERE e.id = $entity OR toLower(e.name) = toLower($entity) OR toLower(e.normalized_name) = toLower($entity)
                    MATCH (e)-[r:RELATIONSHIP]-(n:Entity)
                    RETURN DISTINCT n{.*} AS neighbor,
                           r.relation_type AS relation_type,
                           r.evidence AS evidence,
                           r.confidence AS confidence,
                           startNode(r).id AS source,
                           endNode(r).id AS target
                    LIMIT $limit
                    """,
                    entity=normalize_entity_name(entity),
                    limit=limit,
                ).data()
                return node, neighbors

        node, neighbors = self._run_with_reconnect(operation)
        if not node:
            return {"entity": None, "neighbors": []}
        return {"entity": node, "neighbors": neighbors}

    def get_subgraph(
        self,
        entity: str,
        hops: int = 2,
        limit: int = 50,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        hops = max(1, min(hops, 3))
        graph_filters = _normalize_graph_filters(filters)
        document_conditions = _document_filter_conditions(graph_filters, "d")
        node_document_match = "MATCH (d:Document)-[:HAS_ENTITY]->(node)" if document_conditions else ""
        node_document_where = f"WHERE {' AND '.join(document_conditions)}" if document_conditions else ""
        edge_document_match = "MATCH (d:Document {id: r.document_id})" if document_conditions else ""
        edge_document_where = f"WHERE {' AND '.join(document_conditions)}" if document_conditions else ""
        params = {"entity": normalize_entity_name(entity), "limit": limit, **graph_filters}

        def operation():
            with self._session() as session:
                node_records = session.run(
                    f"""
                    MATCH (start:Entity)
                    WHERE start.id = $entity OR toLower(start.name) = toLower($entity) OR toLower(start.normalized_name) = toLower($entity)
                    OPTIONAL MATCH p=(start)-[:RELATIONSHIP*1..{hops}]-(other:Entity)
                    WITH collect(DISTINCT start) + collect(DISTINCT other) AS raw_nodes
                    UNWIND raw_nodes AS node
                    WITH DISTINCT node
                    {node_document_match}
                    {node_document_where}
                    RETURN node{{.*}} AS node
                    LIMIT $limit
                    """,
                    **params,
                ).data()

                edge_records = session.run(
                    f"""
                    MATCH (start:Entity)
                    WHERE start.id = $entity OR toLower(start.name) = toLower($entity) OR toLower(start.normalized_name) = toLower($entity)
                    MATCH p=(start)-[rels:RELATIONSHIP*1..{hops}]-(other:Entity)
                    UNWIND rels AS r
                    {edge_document_match}
                    {edge_document_where}
                    RETURN DISTINCT {{
                      source: startNode(r).id,
                      target: endNode(r).id,
                      relation_type: r.relation_type,
                      evidence: r.evidence,
                      confidence: r.confidence,
                      document_id: r.document_id,
                      chunk_id: r.chunk_id
                    }} AS edge
                    LIMIT $limit
                    """,
                    **params,
                ).data()
                return node_records, edge_records

        node_records, edge_records = self._run_with_reconnect(operation)
        return {
            "entity": normalize_entity_name(entity),
            "hops": hops,
            "nodes": [row["node"] for row in node_records],
            "edges": [row["edge"] for row in edge_records],
        }

    def find_relevant_subgraph(
        self,
        question: str,
        limit: int = 10,
        hops: int = 2,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        candidates = _question_terms(question)
        if not candidates:
            return {"question": question, "matched_entities": [], "nodes": [], "edges": []}

        graph_filters = _normalize_graph_filters(filters)
        document_conditions = _document_filter_conditions(graph_filters, "d")
        document_match = "MATCH (d:Document)-[:HAS_ENTITY]->(e)" if document_conditions else ""
        document_where = f" AND {' AND '.join(document_conditions)}" if document_conditions else ""
        edge_document_match = "MATCH (d:Document {id: r.document_id})" if document_conditions else ""
        edge_document_where = f" AND {' AND '.join(document_conditions)}" if document_conditions else ""
        chunk_document_match = "MATCH (d:Document)-[:HAS_CHUNK]->(c)" if document_conditions else ""
        chunk_document_where = f" AND {' AND '.join(document_conditions)}" if document_conditions else ""
        search_string = _build_fulltext_query(candidates)
        params = {"terms": candidates, "search_string": search_string, "limit": limit, **graph_filters}

        def fulltext_operation():
            with self._session() as session:
                return session.run(
                    """
                    CALL db.index.fulltext.queryNodes("entity_name_fulltext", $search_string)
                    YIELD node AS e, score
                    __DOCUMENT_MATCH__
                    WHERE 1 = 1 __DOCUMENT_WHERE__
                    RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type, score
                    ORDER BY score DESC
                    LIMIT $limit
                    """.replace("__DOCUMENT_MATCH__", document_match).replace("__DOCUMENT_WHERE__", document_where),
                    **params,
                ).data()

        def contains_operation():
            with self._session() as session:
                return session.run(
                    """
                    UNWIND $terms AS term
                    MATCH (e:Entity)
                    __DOCUMENT_MATCH__
                    WHERE (
                      toLower(e.name) CONTAINS toLower(term)
                      OR toLower(e.normalized_name) CONTAINS toLower(term)
                      OR toLower(coalesce(e.description, '')) CONTAINS toLower(term)
                    )
                    __DOCUMENT_WHERE__
                    RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type, 0.0 AS score
                    LIMIT $limit
                    """.replace("__DOCUMENT_MATCH__", document_match).replace("__DOCUMENT_WHERE__", document_where),
                    **params,
                ).data()

        def content_operation():
            with self._session() as session:
                return session.run(
                    """
                    UNWIND $terms AS term
                    MATCH (source:Entity)-[r:RELATIONSHIP]->(target:Entity)
                    __EDGE_DOCUMENT_MATCH__
                    WHERE (
                      toLower(coalesce(r.evidence, '')) CONTAINS toLower(term)
                      OR toLower(coalesce(r.context, '')) CONTAINS toLower(term)
                      OR toLower(coalesce(r.relation_type, '')) CONTAINS toLower(term)
                    ) __EDGE_DOCUMENT_WHERE__
                    WITH source, target, collect(DISTINCT term) AS matched_terms
                    WITH [source, target] AS entities, size(matched_terms) AS score
                    UNWIND entities AS e
                    RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type, score

                    UNION

                    UNWIND $terms AS term
                    MATCH (e:Entity)-[m:MENTIONED_IN]->(c:Chunk)
                    __CHUNK_DOCUMENT_MATCH__
                    WHERE (
                      toLower(coalesce(c.text, '')) CONTAINS toLower(term)
                      OR toLower(coalesce(c.section, '')) CONTAINS toLower(term)
                      OR toLower(coalesce(c.category, '')) CONTAINS toLower(term)
                    ) __CHUNK_DOCUMENT_WHERE__
                    WITH e, collect(DISTINCT term) AS matched_terms
                    RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type, size(matched_terms) AS score
                    ORDER BY score DESC
                    LIMIT $limit
                    """
                    .replace("__EDGE_DOCUMENT_MATCH__", edge_document_match)
                    .replace("__EDGE_DOCUMENT_WHERE__", edge_document_where)
                    .replace("__CHUNK_DOCUMENT_MATCH__", chunk_document_match)
                    .replace("__CHUNK_DOCUMENT_WHERE__", chunk_document_where),
                    **params,
                ).data()

        try:
            matches = self._run_with_reconnect(fulltext_operation)
        except ClientError as exc:
            if not _fulltext_index_missing(exc):
                raise
            print("[rag.graph] fulltext index missing, falling back to CONTAINS (slow)")
            matches = self._run_with_reconnect(contains_operation)
        try:
            content_matches = self._run_with_reconnect(content_operation)
            matches = _merge_entity_match_rows(matches, content_matches, limit=limit)
        except Exception as exc:
            print(f"[rag.graph] content seed lookup skipped: {type(exc).__name__}: {exc}")

        matched_entities = [row["id"] for row in matches]
        if not matched_entities:
            return {"question": question, "matched_entities": [], "nodes": [], "edges": []}

        batch_limit = max(limit * 10, 200)
        node_rows, edge_rows = self._batch_subgraph(
            entity_ids=matched_entities,
            hops=hops,
            limit=batch_limit,
            filters=graph_filters,
        )
        nodes = [row["node"] for row in node_rows]
        edges = [row["edge"] for row in edge_rows]

        return {"question": question, "matched_entities": matches, "nodes": nodes, "edges": edges}

    def _batch_subgraph(
        self,
        entity_ids: List[str],
        hops: int,
        limit: int,
        filters: Dict[str, Any],
    ):
        if not entity_ids:
            return [], []
        hops = max(1, min(hops, 3))
        graph_filters = _normalize_graph_filters(filters)
        document_conditions = _document_filter_conditions(graph_filters, "d")
        node_document_match = "MATCH (d:Document)-[:HAS_ENTITY]->(node)" if document_conditions else ""
        node_document_where = f"WHERE {' AND '.join(document_conditions)}" if document_conditions else ""
        edge_document_match = "MATCH (d:Document {id: r.document_id})" if document_conditions else ""
        edge_document_where = f"WHERE {' AND '.join(document_conditions)}" if document_conditions else ""
        params = {"entity_ids": entity_ids, "limit": limit, **graph_filters}

        def operation():
            with self._session() as session:
                node_records = session.run(
                    f"""
                    MATCH (start:Entity) WHERE start.id IN $entity_ids
                    OPTIONAL MATCH p=(start)-[:RELATIONSHIP*1..{hops}]-(other:Entity)
                    WITH collect(DISTINCT start) + collect(DISTINCT other) AS raw_nodes
                    UNWIND raw_nodes AS node
                    WITH DISTINCT node
                    {node_document_match}
                    {node_document_where}
                    RETURN node{{.*}} AS node
                    LIMIT $limit
                    """,
                    **params,
                ).data()

                edge_records = session.run(
                    f"""
                    MATCH (start:Entity) WHERE start.id IN $entity_ids
                    MATCH p=(start)-[rels:RELATIONSHIP*1..{hops}]-(other:Entity)
                    UNWIND rels AS r
                    {edge_document_match}
                    {edge_document_where}
                    RETURN DISTINCT {{
                      source: startNode(r).id,
                      target: endNode(r).id,
                      relation_type: r.relation_type,
                      evidence: r.evidence,
                      confidence: r.confidence,
                      document_id: r.document_id,
                      chunk_id: r.chunk_id
                    }} AS edge
                    LIMIT $limit
                    """,
                    **params,
                ).data()
                return node_records, edge_records

        return self._run_with_reconnect(operation)

    def get_visualization_filters(self, document_id: Optional[str] = None) -> Dict[str, Any]:
        document_clause = (
            "WHERE EXISTS { MATCH (:Document {id: $document_id})-[:HAS_ENTITY]->(e) }"
            if document_id
            else ""
        )

        def operation():
            with self._session() as session:
                records = session.run(
                    f"""
                    MATCH (e:Entity)
                    {document_clause}
                    RETURN DISTINCT
                      coalesce(toString(e.year), '') AS year,
                      coalesce(e.company, '') AS company,
                      coalesce(e.esg_domain, 'general') AS esg_domain
                    """,
                    document_id=document_id,
                ).data()
                return records

        records = self._run_with_reconnect(operation)
        years = sorted({row["year"] for row in records if row.get("year")})
        companies = sorted({row["company"] for row in records if row.get("company")})
        esg_domains = sorted({row["esg_domain"] for row in records if row.get("esg_domain")})
        return {
            "years": years,
            "companies": companies,
            "esg_domains": esg_domains or ["general"],
        }

    def get_visualization_graph(
        self,
        years: Optional[List[str]] = None,
        companies: Optional[List[str]] = None,
        esg_domains: Optional[List[str]] = None,
        limit: int = 1000,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        filters: List[str] = []
        params: Dict[str, Any] = {"limit": max(100, min(int(limit or 1000), 30000))}
        node_match = "MATCH (e:Entity)"
        if document_id:
            node_match = "MATCH (:Document {id: $document_id})-[:HAS_ENTITY]->(e:Entity)"
            params["document_id"] = document_id
        elif document_ids:
            node_match = "MATCH (d:Document)-[:HAS_ENTITY]->(e:Entity)"
            filters.append("d.id IN $document_ids")
            params["document_ids"] = document_ids
        if years:
            filters.append("toString(e.year) IN $years")
            params["years"] = years
        if companies:
            filters.append("e.company IN $companies")
            params["companies"] = companies
        if esg_domains:
            filters.append("coalesce(e.esg_domain, 'general') IN $esg_domains")
            params["esg_domains"] = esg_domains

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        def operation():
            with self._session() as session:
                nodes = session.run(
                    f"""
                    {node_match}
                    {where_clause}
                    WITH DISTINCT e
                    OPTIONAL MATCH (e)-[m:MENTIONED_IN]->(:Chunk)
                    WITH e, properties(e) AS props, count(m) AS frequency
                    RETURN
                      e.id AS id,
                      coalesce(e.name, props.canonical_name, e.normalized_name, e.id) AS label,
                      coalesce(e.type, 'Entity') AS type,
                      coalesce(props.esg_domain, 'general') AS esg_domain,
                      coalesce(props.esg_domain, 'general') AS domain,
                      coalesce(toString(props.year), '') AS year,
                      coalesce(props.company, '') AS company,
                      coalesce(e.description, '') AS description,
                      coalesce(e.confidence, 0.75) AS confidence,
                      frequency AS frequency
                    ORDER BY frequency DESC, confidence DESC, label ASC
                    LIMIT $limit
                    """,
                    **params,
                ).data()

                node_ids = [row["id"] for row in nodes]
                if not node_ids:
                    return {"nodes": [], "edges": []}

                edge_document_filter = ""
                edge_params: Dict[str, Any] = {"node_ids": node_ids, "limit": params["limit"]}
                if document_ids:
                    edge_document_filter = "AND r.document_id IN $document_ids"
                    edge_params["document_ids"] = params["document_ids"]
                elif document_id:
                    edge_document_filter = "AND r.document_id = $document_id"
                    edge_params["document_id"] = params["document_id"]

                edge_query = """
                    MATCH (source:Entity)-[r:RELATIONSHIP]->(target:Entity)
                    WHERE source.id IN $node_ids AND target.id IN $node_ids
                      __DOCUMENT_EDGE_FILTER__
                    WITH source, target, r, properties(r) AS props
                    RETURN
                      source.id AS source,
                      target.id AS target,
                      coalesce(r.relation_type, r.type, 'RELATED_TO') AS relationship_type,
                      coalesce(r.type, r.relation_type, 'RELATED_TO') AS type,
                      coalesce(props.action, '') AS relationship_action,
                      coalesce(props.nature, '') AS relationship_nature,
                      coalesce(props.category, '') AS category,
                      coalesce(props.domain, props.esg_domain, props.category, 'general') AS domain,
                      coalesce(r.evidence, '') AS evidence,
                      coalesce(r.confidence, 0.75) AS confidence,
                      coalesce(r.document_id, '') AS document_id,
                      coalesce(r.chunk_id, '') AS chunk_id
                    LIMIT $limit
                """.replace(
                    "__DOCUMENT_EDGE_FILTER__",
                    edge_document_filter,
                )
                edges = session.run(edge_query, **edge_params).data()
                return {"nodes": nodes, "edges": edges}

        return self._run_with_reconnect(operation)

    def get_visualization_stats(self, document_id: Optional[str] = None) -> Dict[str, Any]:
        document_clause = (
            "WHERE EXISTS { MATCH (:Document {id: $document_id})-[:HAS_ENTITY]->(e) }"
            if document_id
            else ""
        )

        def operation():
            with self._session() as session:
                nodes_by_domain = session.run(
                    f"""
                    MATCH (e:Entity)
                    {document_clause}
                    RETURN coalesce(e.esg_domain, 'general') AS label, count(*) AS count
                    ORDER BY count DESC
                    """,
                    document_id=document_id,
                ).data()
                nodes_by_type = session.run(
                    f"""
                    MATCH (e:Entity)
                    {document_clause}
                    RETURN coalesce(e.type, 'Entity') AS label, count(*) AS count
                    ORDER BY count DESC
                    """,
                    document_id=document_id,
                ).data()
                edge_document_clause = (
                    "WHERE r.document_id = $document_id"
                    if document_id
                    else ""
                )
                edges_by_type = session.run(
                    f"""
                    MATCH ()-[r:RELATIONSHIP]->()
                    {edge_document_clause}
                    RETURN coalesce(r.relation_type, r.type, 'RELATED_TO') AS label, count(*) AS count
                    ORDER BY count DESC
                    """,
                    document_id=document_id,
                ).data()
                return {
                    "nodes_by_domain": {row["label"]: row["count"] for row in nodes_by_domain},
                    "nodes_by_type": {row["label"]: row["count"] for row in nodes_by_type},
                    "edges_by_type": {row["label"]: row["count"] for row in edges_by_type},
                }

        return self._run_with_reconnect(operation)

    @staticmethod
    def _upsert_document(tx, row: Dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (d:Document {id: $id})
            SET d += $props
            """,
            id=row["id"],
            props=row,
        )

    @staticmethod
    def _upsert_chunks(tx, document_id: str, rows: List[Dict[str, Any]]) -> None:
        tx.run(
            """
            MATCH (d:Document {id: $document_id})
            UNWIND $rows AS row
            MERGE (c:Chunk {id: row.id})
            SET c += row
            MERGE (d)-[:HAS_CHUNK]->(c)
            """,
            document_id=document_id,
            rows=rows,
        )

    @staticmethod
    def _clear_document_scope(tx, document_id: str) -> None:
        tx.run(
            """
            MATCH (d:Document {id: $document_id})
            OPTIONAL MATCH ()-[r:RELATIONSHIP {document_id: $document_id}]->()
            DELETE r
            WITH d
            OPTIONAL MATCH ()-[c:CAUSAL_LINK {document_id: $document_id}]->()
            DELETE c
            WITH d
            OPTIONAL MATCH ()-[m:MENTIONED_IN {document_id: $document_id}]->()
            DELETE m
            WITH d
            OPTIONAL MATCH (d)-[hc:HAS_CHUNK]->(c:Chunk)
            DELETE hc
            WITH d, collect(DISTINCT c) AS chunks
            FOREACH (chunk IN chunks | DETACH DELETE chunk)
            WITH d
            OPTIONAL MATCH (d)-[he:HAS_ENTITY]->(:Entity)
            DELETE he
            """,
            document_id=document_id,
        )

    @staticmethod
    def _upsert_entities(tx, document_id: str, rows: List[Dict[str, Any]]) -> None:
        tx.run(
            """
            MATCH (d:Document {id: $document_id})
            UNWIND $rows AS row
            MERGE (e:Entity {id: row.id})
            SET e += row
            MERGE (d)-[:HAS_ENTITY]->(e)
            """,
            document_id=document_id,
            rows=rows,
        )

    @staticmethod
    def _upsert_mentions(tx, rows: List[Dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $rows AS row
            MATCH (e:Entity {id: row.entity_id})
            MATCH (c:Chunk {id: row.chunk_node_id})
            MERGE (e)-[m:MENTIONED_IN {document_id: row.document_id, chunk_id: row.chunk_id}]->(c)
            SET m += row.props
            """,
            rows=rows,
        )

    @staticmethod
    def _upsert_relations(tx, rows: List[Dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $rows AS row
            MATCH (source:Entity {id: row.source_id})
            MATCH (target:Entity {id: row.target_id})
            MERGE (source)-[r:RELATIONSHIP {
              document_id: row.document_id,
              chunk_id: row.chunk_id,
              relation_type: row.relation_type,
              source_id: row.source_id,
              target_id: row.target_id
            }]->(target)
            SET r += row.props
            WITH r, row, source, target
            WHERE row.props.is_causal = true
            MERGE (source)-[c:CAUSAL_LINK {
              document_id: row.document_id,
              chunk_id: row.chunk_id,
              source_id: row.source_id,
              target_id: row.target_id,
              causal_type: row.props.causal_type
            }]->(target)
            SET c.polarity = row.props.polarity,
                c.strength = row.props.strength,
                c.confidence = row.props.confidence,
                c.evidence = row.props.evidence,
                c.relation_type = row.relation_type
            """,
            rows=rows,
        )

    def _document_row(self, document: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id": str(document.get("id") or ""),
            "title": str(document.get("title") or ""),
            "domain": str(document.get("domain") or "general"),
            "source": str(document.get("source") or ""),
            "document_group": str(document.get("document_group") or ""),
            "source_type": str(document.get("source_type") or ""),
            "processed_text_path": str(document.get("processed_text_path") or ""),
            "chunks_path": str(document.get("chunks_path") or ""),
            "extractions_path": str(document.get("extractions_path") or ""),
            "graph_path": str(document.get("graph_path") or ""),
            "vector_store_path": str(document.get("vector_store_path") or ""),
            "synced_at": now,
        }

    def _chunk_row(self, document_id: str, chunk: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": f"{document_id}:{chunk.get('chunk_id')}",
            "chunk_id": str(chunk.get("chunk_id") or ""),
            "document_id": document_id,
            "text": str(chunk.get("text") or ""),
            "start": int(chunk.get("start") or 0),
            "end": int(chunk.get("end") or 0),
            "section": str(chunk.get("section") or "Document"),
            "category": str(chunk.get("category") or "narrative"),
            "approx_tokens": int(chunk.get("approx_tokens") or 0),
            "paragraph_count": int(chunk.get("paragraph_count") or 1),
        }

    def _entity_rows(
        self,
        document_id: str,
        chunks: List[Dict[str, Any]],
        extractions: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        chunk_by_id = {str(chunk.get("chunk_id")): chunk for chunk in chunks}
        entity_rows: Dict[str, Dict[str, Any]] = {}
        mention_rows: List[Dict[str, Any]] = []

        for row in extractions:
            chunk_id = str(row.get("chunk_id") or "")
            chunk_node_id = f"{document_id}:{chunk_id}"
            chunk = chunk_by_id.get(chunk_id, {})
            for entity in row.get("entities", []) or []:
                if isinstance(entity, str):
                    entity = {"name": entity}
                if not isinstance(entity, dict):
                    continue

                name = normalize_entity_name(
                    entity.get("name") or entity.get("entity") or entity.get("text") or entity.get("id") or ""
                )
                if not name:
                    continue

                entity_id = name
                entity_rows[entity_id] = self._merge_entity_rows(entity_rows.get(entity_id), entity, entity_id)
                mention_rows.append(
                    {
                        "entity_id": entity_id,
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "chunk_node_id": chunk_node_id,
                        "props": {
                            "confidence": _safe_float(entity.get("confidence"), 0.8),
                            "source_chunk_id": chunk_id,
                            "section": str(chunk.get("section") or "Document"),
                            "category": str(chunk.get("category") or "narrative"),
                            "metadata_json": _json_string(entity.get("metadata")),
                        },
                    }
                )

        return list(entity_rows.values()), mention_rows

    def _merge_entity_rows(
        self,
        existing: Optional[Dict[str, Any]],
        entity: Dict[str, Any],
        entity_id: str,
    ) -> Dict[str, Any]:
        row = dict(existing or {})
        row["id"] = entity_id
        row["name"] = (
            row.get("name")
            or entity.get("name")
            or entity.get("entity")
            or entity.get("text")
            or entity_id
        )
        row["normalized_name"] = entity_id
        row["type"] = str(entity.get("type") or entity.get("entity_type") or row.get("type") or "Entity")
        description = str(entity.get("description") or row.get("description") or "")
        if description:
            row["description"] = description
        row["confidence"] = max(_safe_float(row.get("confidence"), 0.0), _safe_float(entity.get("confidence"), 0.0))
        metadata = entity.get("metadata")
        if isinstance(metadata, dict):
            domain = metadata.get("esg_domain") or metadata.get("domain")
            if domain:
                row["esg_domain"] = str(domain)
            company = metadata.get("company")
            if company:
                row["company"] = str(company)
            year = metadata.get("year")
            if year:
                row["year"] = str(year)
        row["metadata_json"] = _json_string(metadata)
        return row

    def _relation_rows(self, document_id: str, extractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for extraction in extractions:
            chunk_id = str(extraction.get("chunk_id") or "")
            entity_lookup = self._entity_lookup(extraction.get("entities", []) or [])
            for relation in extraction.get("relations", []) or []:
                if not isinstance(relation, dict):
                    continue

                raw_source = (
                    relation.get("subject_id")
                    or relation.get("source_id")
                    or relation.get("from")
                    or relation.get("source_entity")
                    or relation.get("subject")
                    or relation.get("source")
                    or relation.get("entity_1")
                    or ""
                )
                raw_target = (
                    relation.get("object_id")
                    or relation.get("target_id")
                    or relation.get("to")
                    or relation.get("target_entity")
                    or relation.get("object")
                    or relation.get("target")
                    or relation.get("entity_2")
                    or ""
                )
                source = self._resolve_relation_endpoint(raw_source, entity_lookup)
                target = self._resolve_relation_endpoint(raw_target, entity_lookup)
                relation_type = str(
                    relation.get("relation_type")
                    or relation.get("relation")
                    or relation.get("predicate")
                    or relation.get("type")
                    or "related_to"
                )
                if not source or not target:
                    continue
                canonical = canonicalize_relation(relation_type)

                rows.append(
                    {
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "source_id": source,
                        "target_id": target,
                        "relation_type": relation_type,
                        "props": {
                            "relation_type": relation_type,
                            "causal_type": canonical["canonical"],
                            "polarity": canonical["polarity"],
                            "strength": canonical["strength"],
                            "is_causal": canonical["is_causal"],
                            "evidence": str(relation.get("evidence") or relation.get("context") or ""),
                            "confidence": _safe_float(relation.get("confidence"), 0.75),
                            "context": str(relation.get("context") or ""),
                            "source_chunk_id": chunk_id,
                            "metadata_json": _json_string(relation.get("metadata")),
                        },
                    }
                )
        return rows

    @staticmethod
    def _entity_lookup(entities: List[Any]) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        for entity in entities:
            if isinstance(entity, str):
                entity = {"name": entity}
            if not isinstance(entity, dict):
                continue
            name = normalize_entity_name(
                entity.get("name") or entity.get("entity") or entity.get("text") or entity.get("id") or ""
            )
            if not name:
                continue
            for key in (entity.get("id"), entity.get("name"), entity.get("entity"), entity.get("text")):
                normalized_key = normalize_entity_name(str(key or ""))
                if normalized_key:
                    lookup[normalized_key] = name
        return lookup

    @staticmethod
    def _resolve_relation_endpoint(value: Any, entity_lookup: Dict[str, str]) -> str:
        normalized = normalize_entity_name(str(value or ""))
        return entity_lookup.get(normalized, normalized)


_QUESTION_PHRASE_PATTERNS = (
    re.compile(r"\bscope\s+[123]\b", re.I),
    re.compile(r"\bcategory\s+\d+[a-z]?\b", re.I),
    re.compile(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){1,4}\b"),
)


def _question_terms(question: str) -> List[str]:
    text = str(question or "")
    raw_terms: List[str] = []
    for pattern in _QUESTION_PHRASE_PATTERNS:
        raw_terms.extend(match.group(0) for match in pattern.finditer(text))
    raw_terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", text))
    stopwords = {
        "and",
        "are",
        "but",
        "for",
        "has",
        "have",
        "into",
        "not",
        "the",
        "this",
        "that",
        "what",
        "which",
        "when",
        "where",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "is",
        "to",
        "or",
        "in",
        "of",
        "does",
        "did",
        "with",
        "from",
        "into",
        "about",
        "their",
        "there",
        "report",
        "reports",
        "company",
    }
    ordered = []
    for term in raw_terms:
        lowered = re.sub(r"\s+", " ", str(term or "").strip(" \t\r\n,.;:!?()[]{}\"'’")).lower()
        parts = lowered.split()
        while parts and parts[0] in stopwords:
            parts.pop(0)
        while parts and parts[-1] in stopwords:
            parts.pop()
        lowered = " ".join(parts)
        if not lowered:
            continue
        if lowered in stopwords:
            continue
        if lowered not in ordered:
            ordered.append(lowered)
    return ordered[:12]


def _merge_entity_match_rows(*groups: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: Dict[str, int] = {}
    next_order = 0
    for rows in groups:
        for row in rows or []:
            entity_id = str(row.get("id") or "").strip()
            if not entity_id:
                continue
            score = _safe_float(row.get("score"), 0.0)
            if entity_id not in merged:
                merged[entity_id] = dict(row)
                merged[entity_id]["score"] = score
                order[entity_id] = next_order
                next_order += 1
                continue
            existing = merged[entity_id]
            existing["score"] = max(_safe_float(existing.get("score"), 0.0), score)
            for key in ("name", "type"):
                if not existing.get(key) and row.get(key):
                    existing[key] = row.get(key)

    return sorted(
        merged.values(),
        key=lambda row: (-_safe_float(row.get("score"), 0.0), order.get(str(row.get("id") or ""), 0)),
    )[: max(1, int(limit or 1))]


def _build_fulltext_query(terms: List[str]) -> str:
    escaped = []
    for term in terms or []:
        clean = str(term or "").strip()
        if not clean:
            continue
        clean = clean.replace("\\", "\\\\").replace('"', '\\"')
        escaped.append(f'"{clean}"')
    return " OR ".join(escaped)


def _fulltext_index_missing(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return "nosuchindex" in message or ("fulltext" in message and "index" in message and "no such" in message)


def _normalize_graph_filters(filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    filters = filters or {}
    document_ids = [str(item) for item in (filters.get("document_ids") or []) if str(item or "").strip()]
    return {
        "document_ids": document_ids,
        "document_group": str(filters.get("document_group") or "").strip(),
        "source_type": str(filters.get("source_type") or "").strip(),
        "domain": str(filters.get("domain") or "").strip(),
    }


def _document_filter_conditions(filters: Dict[str, Any], alias: str) -> List[str]:
    conditions: List[str] = []
    if filters.get("document_ids"):
        conditions.append(f"{alias}.id IN $document_ids")
    if filters.get("document_group"):
        conditions.append(f"{alias}.document_group = $document_group")
    if filters.get("source_type"):
        conditions.append(f"{alias}.source_type = $source_type")
    if filters.get("domain"):
        conditions.append(f"{alias}.domain = $domain")
    return conditions


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _json_string(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)
