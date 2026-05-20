"""Adapt ESG extraction JSON into the backend graph entity/relation format."""

from __future__ import annotations

from typing import Dict, List, Tuple
import re


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


class ESGResultAdapter:
    """Convert model JSON into graph entities and relations expected by graph_service."""

    TYPE_MAP = {
        "company": "COMPANY",
        "organization": "COMPANY",
        "esg metric": "ESG_METRIC",
        "metric": "ESG_METRIC",
        "environmental item": "ENVIRONMENTAL_ITEM",
        "social item": "SOCIAL_ITEM",
        "governance item": "GOVERNANCE_ITEM",
        "policy": "POLICY",
        "risk": "RISK",
        "target": "TARGET",
        "year": "YEAR",
        "value": "VALUE",
        "event": "EVENT",
        "category": "CATEGORY",
    }

    def adapt(
        self,
        result: Dict,
        chunk_id: str,
        document_id: str,
        company: str | None = None,
        include_relations: bool = True,
    ) -> Tuple[List[Dict], List[Dict]]:
        entities: Dict[str, Dict] = {}
        relations: Dict[Tuple[str, str, str], Dict] = {}

        if company:
            company_entity = self._entity(
                name=company,
                entity_type="COMPANY",
                description=f"Company in scope for document {document_id}",
                chunk_id=chunk_id,
                confidence=0.99,
                metadata={"source": "ingest_context"},
            )
            entities[company_entity["entity_key"]] = company_entity

        for item in result.get("entities", []) or []:
            entity = self._normalize_entity(item, chunk_id)
            if entity:
                entities[entity["entity_key"]] = entity

        if include_relations:
            for item in result.get("relations", []) or []:
                relation, source_entity, target_entity = self._normalize_relation(item, chunk_id)
                if source_entity:
                    entities[source_entity["entity_key"]] = source_entity
                if target_entity:
                    entities[target_entity["entity_key"]] = target_entity
                if relation:
                    relations[(relation["source_key"], relation["target_key"], relation["relation_type"])] = relation

        return list(entities.values()), list(relations.values())

    def _normalize_entity(self, item, chunk_id: str) -> Dict | None:
        if isinstance(item, str):
            name = item.strip()
            if not name:
                return None
            return self._entity(name, "EVENT", "", chunk_id, 0.6, {"source": "local_ai_service"})

        if not isinstance(item, dict):
            return None

        name = (
            item.get("name")
            or item.get("entity")
            or item.get("text")
            or item.get("label")
        )
        if not isinstance(name, str) or not name.strip():
            return None

        raw_type = (
            item.get("type")
            or item.get("entity_type")
            or item.get("category")
            or "EVENT"
        )
        entity_type = self._map_type(raw_type)
        description = item.get("description") or item.get("evidence") or item.get("context") or ""
        confidence = self._safe_confidence(item.get("confidence"), default=0.75)

        metadata = {"source": "local_ai_service", "raw_type": raw_type}
        for key in ("esg_domain", "domain", "category", "value", "year"):
            if item.get(key) is not None:
                metadata[key] = item.get(key)

        return self._entity(name, entity_type, description, chunk_id, confidence, metadata)

    def _normalize_relation(self, item, chunk_id: str) -> Tuple[Dict | None, Dict | None, Dict | None]:
        if not isinstance(item, dict):
            return None, None, None

        source_name = (
            item.get("source_entity")
            or item.get("source")
            or item.get("entity_1")
            or item.get("from")
        )
        target_name = (
            item.get("target_entity")
            or item.get("target")
            or item.get("entity_2")
            or item.get("to")
        )
        relation_type = (
            item.get("relation_type")
            or item.get("type")
            or item.get("predicate")
            or item.get("relation")
        )

        if not source_name or not target_name or not relation_type:
            return None, None, None

        source_type = self._map_type(item.get("source_type") or item.get("source_entity_type") or "EVENT")
        target_type = self._map_type(item.get("target_type") or item.get("target_entity_type") or "EVENT")
        source_entity = self._entity(
            str(source_name),
            source_type,
            item.get("source_description") or "",
            chunk_id,
            self._safe_confidence(item.get("confidence"), default=0.7),
            {"source": "local_ai_service", "from_relation_stub": True},
        )
        target_entity = self._entity(
            str(target_name),
            target_type,
            item.get("target_description") or "",
            chunk_id,
            self._safe_confidence(item.get("confidence"), default=0.7),
            {"source": "local_ai_service", "from_relation_stub": True},
        )

        relation = {
            "source_key": source_entity["entity_key"],
            "target_key": target_entity["entity_key"],
            "relation_type": self._normalize_relation_type(str(relation_type)),
            "evidence": str(item.get("evidence") or item.get("context") or "")[:400],
            "chunk_id": chunk_id,
            "confidence": self._safe_confidence(item.get("confidence"), default=0.7),
            "metadata": {"source_chunk_id": chunk_id, "source": "local_ai_service"},
        }
        return relation, source_entity, target_entity

    def _entity(
        self,
        name: str,
        entity_type: str,
        description: str,
        chunk_id: str,
        confidence: float,
        metadata: Dict,
    ) -> Dict:
        normalized_name = _slugify(name)
        return {
            "name": name.strip(),
            "type": entity_type,
            "normalized_name": normalized_name,
            "description": str(description).strip(),
            "source_chunk_id": chunk_id,
            "confidence": confidence,
            "metadata": metadata,
            "entity_key": f"{entity_type}:{normalized_name}",
        }

    def _map_type(self, raw_type) -> str:
        normalized = str(raw_type or "EVENT").replace("_", " ").strip().lower()
        if normalized in self.TYPE_MAP:
            return self.TYPE_MAP[normalized]
        fallback = normalized.upper().replace(" ", "_")
        return fallback if fallback else "EVENT"

    @staticmethod
    def _normalize_relation_type(value: str) -> str:
        return value.strip().upper().replace(" ", "_")

    @staticmethod
    def _safe_confidence(value, default: float = 0.7) -> float:
        try:
            number = float(value)
        except Exception:
            return default
        return max(0.0, min(1.0, number))


esg_result_adapter = ESGResultAdapter()
