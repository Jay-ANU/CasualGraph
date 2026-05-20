"""Lightweight ESG entity and relation extraction for the MVP."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import json
import os
import re

import yaml


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


class ESGExtractionService:
    def __init__(self) -> None:
        self.ontology_terms = self._load_ontology_terms()
        self.policy_keywords = (
            "policy",
            "framework",
            "standard",
            "code of conduct",
            "governance policy",
        )
        self.risk_keywords = ("risk", "climate risk", "transition risk", "physical risk")
        self.target_keywords = ("target", "goal", "commitment", "aim", "net zero", "reduce by")
        self.event_keywords = ("launched", "announced", "opened", "introduced", "expanded", "incident")

    def extract_entities(self, chunk: Dict, company: str | None = None) -> List[Dict]:
        content = chunk["content"]
        sentences = self._split_sentences(content)
        entities: Dict[Tuple[str, str], Dict] = {}

        if company:
            entities[("COMPANY", _slugify(company))] = self._entity(
                name=company,
                entity_type="COMPANY",
                description=f"Company in scope for document {chunk['document_id']}",
                chunk_id=chunk["id"],
                confidence=0.99,
                metadata={"source": "ingest_context"},
            )

        for sentence in sentences:
            lower = sentence.lower()
            for year in re.findall(r"\b(?:19|20)\d{2}\b", sentence):
                entities[("YEAR", year)] = self._entity(
                    name=year,
                    entity_type="YEAR",
                    description=sentence[:220],
                    chunk_id=chunk["id"],
                    confidence=0.9,
                    metadata={"source": "regex"},
                )

            for value in re.findall(r"\b\d+(?:\.\d+)?\s?(?:%|percent|tco2e|tons|tonnes|mwh|kwh|employees|hours|usd|million|billion)\b", lower):
                entities[("VALUE", _slugify(value))] = self._entity(
                    name=value,
                    entity_type="VALUE",
                    description=sentence[:220],
                    chunk_id=chunk["id"],
                    confidence=0.82,
                    metadata={"source": "regex"},
                )

            for keyword in self.policy_keywords:
                if keyword in lower:
                    name = self._best_phrase(sentence, keyword)
                    entities[("POLICY", _slugify(name))] = self._entity(
                        name=name,
                        entity_type="POLICY",
                        description=sentence[:220],
                        chunk_id=chunk["id"],
                        confidence=0.78,
                        metadata={"source": "keyword"},
                    )

            for keyword in self.risk_keywords:
                if keyword in lower:
                    name = self._best_phrase(sentence, keyword)
                    entities[("RISK", _slugify(name))] = self._entity(
                        name=name,
                        entity_type="RISK",
                        description=sentence[:220],
                        chunk_id=chunk["id"],
                        confidence=0.8,
                        metadata={"source": "keyword"},
                    )

            for keyword in self.target_keywords:
                if keyword in lower:
                    name = self._best_phrase(sentence, keyword)
                    entities[("TARGET", _slugify(name))] = self._entity(
                        name=name,
                        entity_type="TARGET",
                        description=sentence[:220],
                        chunk_id=chunk["id"],
                        confidence=0.76,
                        metadata={"source": "keyword"},
                    )

            for keyword in self.event_keywords:
                if keyword in lower:
                    name = self._best_phrase(sentence, keyword)
                    entities[("EVENT", _slugify(name))] = self._entity(
                        name=name,
                        entity_type="EVENT",
                        description=sentence[:220],
                        chunk_id=chunk["id"],
                        confidence=0.72,
                        metadata={"source": "keyword"},
                    )

            for term in self.ontology_terms:
                if term["match"] in lower:
                    entity_type = term["entity_type"]
                    key = (entity_type, term["normalized_name"])
                    entities[key] = self._entity(
                        name=term["name"],
                        entity_type=entity_type,
                        description=sentence[:220],
                        chunk_id=chunk["id"],
                        confidence=0.88,
                        metadata={
                            "source": "ontology",
                            "esg_domain": term["esg_domain"],
                            "ontology_path": term["path"],
                        },
                    )

        return list(entities.values())

    def extract_relations(self, chunk: Dict, entities: List[Dict], company: str | None = None) -> List[Dict]:
        by_type: Dict[str, List[Dict]] = {}
        for entity in entities:
            by_type.setdefault(entity["type"], []).append(entity)

        relations: Dict[Tuple[str, str, str], Dict] = {}

        if company and by_type.get("COMPANY"):
            company_entity = by_type["COMPANY"][0]
            for metric in by_type.get("ESG_METRIC", []):
                relations[(company_entity["entity_key"], metric["entity_key"], "HAS_METRIC")] = self._relation(
                    company_entity, metric, "HAS_METRIC", chunk["content"][:240], chunk["id"], 0.87
                )
            for target in by_type.get("TARGET", []):
                relations[(company_entity["entity_key"], target["entity_key"], "HAS_TARGET")] = self._relation(
                    company_entity, target, "HAS_TARGET", target["description"], chunk["id"], 0.84
                )
            for risk in by_type.get("RISK", []):
                relations[(company_entity["entity_key"], risk["entity_key"], "FACES_RISK")] = self._relation(
                    company_entity, risk, "FACES_RISK", risk["description"], chunk["id"], 0.82
                )
            for event in by_type.get("EVENT", []):
                relations[(event["entity_key"], company_entity["entity_key"], "IMPACTS")] = self._relation(
                    event, company_entity, "IMPACTS", event["description"], chunk["id"], 0.7
                )

        category_entities = self._category_entities(chunk["id"])
        for metric in by_type.get("ESG_METRIC", []):
            domain = metric.get("metadata", {}).get("esg_domain")
            category = category_entities.get(domain)
            if category:
                relations[(metric["entity_key"], category["entity_key"], "BELONGS_TO")] = self._relation(
                    metric, category, "BELONGS_TO", metric["description"], chunk["id"], 0.8
                )

        for policy in by_type.get("POLICY", []):
            for metric in by_type.get("ESG_METRIC", []):
                relations[(policy["entity_key"], metric["entity_key"], "AFFECTS")] = self._relation(
                    policy, metric, "AFFECTS", policy["description"], chunk["id"], 0.68
                )

        return list(category_entities.values()) + list(relations.values())

    def _category_entities(self, chunk_id: str) -> Dict[str, Dict]:
        categories = {
            "environmental": self._entity("Environmental", "CATEGORY", "ESG environmental category", chunk_id, 1.0, {"esg_domain": "environmental"}),
            "social": self._entity("Social", "CATEGORY", "ESG social category", chunk_id, 1.0, {"esg_domain": "social"}),
            "governance": self._entity("Governance", "CATEGORY", "ESG governance category", chunk_id, 1.0, {"esg_domain": "governance"}),
            "ai": self._entity("AI", "CATEGORY", "AI-specific ESG category", chunk_id, 1.0, {"esg_domain": "ai"}),
        }
        return categories

    @staticmethod
    def _relation(source: Dict, target: Dict, relation_type: str, evidence: str, chunk_id: str, confidence: float) -> Dict:
        return {
            "source_key": source["entity_key"],
            "target_key": target["entity_key"],
            "relation_type": relation_type,
            "evidence": evidence[:400],
            "chunk_id": chunk_id,
            "confidence": confidence,
            "metadata": {"source_chunk_id": chunk_id},
        }

    @staticmethod
    def _entity(name: str, entity_type: str, description: str, chunk_id: str, confidence: float, metadata: Dict) -> Dict:
        normalized_name = _slugify(name)
        return {
            "name": name.strip(),
            "type": entity_type,
            "normalized_name": normalized_name,
            "description": description.strip(),
            "source_chunk_id": chunk_id,
            "confidence": confidence,
            "metadata": metadata,
            "entity_key": f"{entity_type}:{normalized_name}",
        }

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " ").strip())
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    @staticmethod
    def _best_phrase(sentence: str, keyword: str) -> str:
        pieces = re.split(r"[;,:()]", sentence)
        for piece in pieces:
            if keyword in piece.lower():
                return piece.strip()[:120]
        return sentence.strip()[:120]

    def _load_ontology_terms(self) -> List[Dict]:
        configured_path = os.getenv("ESG_LEGACY_ONTOLOGY_PATH", "").strip()
        if not configured_path:
            return []
        ontology_path = Path(configured_path)
        if not ontology_path.exists():
            return []

        with open(ontology_path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}

        results: List[Dict] = []

        def walk(node: Dict, prefix: str = "") -> None:
            for key, value in node.items():
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict) and "synonyms" in value:
                    domain = path.split(".")[0]
                    results.append(
                        {
                            "name": key.replace("_", " "),
                            "normalized_name": _slugify(key),
                            "match": key.replace("_", " ").lower(),
                            "entity_type": self._map_ontology_type(domain, value.get("canonical_type", "")),
                            "esg_domain": domain,
                            "path": path,
                        }
                    )
                    for synonym in value.get("synonyms", []):
                        results.append(
                            {
                                "name": synonym.replace("_", " "),
                                "normalized_name": _slugify(synonym),
                                "match": synonym.replace("_", " ").lower(),
                                "entity_type": self._map_ontology_type(domain, value.get("canonical_type", "")),
                                "esg_domain": domain,
                                "path": path,
                            }
                        )
                elif isinstance(value, dict):
                    walk(value, path)

        walk(raw)
        unique = {}
        for item in results:
            unique[(item["entity_type"], item["match"])] = item
        return list(unique.values())

    @staticmethod
    def _map_ontology_type(domain: str, canonical_type: str) -> str:
        if canonical_type == "ESG_METRIC":
            return "ESG_METRIC"
        if canonical_type == "RISK_FACTOR":
            return "RISK"
        if "policy" in canonical_type.lower():
            return "POLICY"
        if domain == "environmental":
            return "ENVIRONMENTAL_ITEM"
        if domain == "social":
            return "SOCIAL_ITEM"
        if domain == "governance":
            return "GOVERNANCE_ITEM"
        return "EVENT"


esg_extraction_service = ESGExtractionService()
