"""QLoRA-backed ESG entity and relation extraction with a demo-safe fallback."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ai_service.remote_extractor import extract_esg_with_deepseek
from ai_service.utils import normalize_result, parse_json_safely
from configs.settings import ESG_EXTRACTION_BACKEND


PROMPT_TEMPLATE = """You are an ESG knowledge extraction expert. Your goal is to be COMPREHENSIVE -- extract every entity and relation that appears in the text.

Entity types to extract (use these exact strings):
- Organization: companies, subsidiaries, regulators, NGOs, certifiers
- Person: named individuals (executives, authors, officials)
- Metric: ESG indicators (Scope 1/2/3 emissions, water usage, diversity ratio, governance score, etc.)
- Value: a quantitative number with its unit (e.g., "14% reduction", "23 million tCO2e")
- Target: a stated commitment, goal, or pledge (e.g., "net-zero by 2040")
- Initiative: a named program, policy, or project (e.g., "Climate Roadmap", "Renewable Energy Program")
- Location: countries, regions, facilities, supply chain origins
- TimePeriod: fiscal years, dates, reporting periods (e.g., "FY25", "2030")
- Standard: frameworks or certifications (e.g., "GRI", "SASB", "TCFD", "ISO 14001")
- ESGTopic: thematic categories (e.g., "carbon emissions", "diversity & inclusion", "board independence")

Relation predicates to use (use exact strings):
- reports / discloses (Organization -> Metric/Value/Target)
- reduces / increases / mitigates / prevents / contributes_to / leads_to / causes / drives (causal links between any entity types)
- targets / commits_to (Organization -> Target)
- complies_with / certified_by (Organization -> Standard)
- located_in / operates_in (Organization -> Location)
- measured_in (Metric -> Value)
- part_of / subsidiary_of (Organization -> Organization)
- affects / impacts (any -> any)

Output a single JSON object. No prose, no explanation, no markdown fences.

Schema:
{{
  "entities": [
    {{"name": "<surface form>", "type": "<one of the types above>", "description": "<one short sentence of context from the text, optional>"}}
  ],
  "relations": [
    {{"subject": "<entity name>", "predicate": "<one of the predicates above>", "object": "<entity name>", "evidence": "<short verbatim phrase from text supporting this>"}}
  ]
}}

Rules:
1. Extract EVERY entity that is explicitly named or numerically stated. Do not skip duplicates within the same chunk -- but if the same entity appears 3 times, list it once.
2. Every relation MUST have its subject and object also appear in the entities array.
3. If a number appears with a unit, create BOTH a Metric entity AND a Value entity, and link them via "measured_in".
4. Do NOT invent facts not present in the text. But DO extract everything that IS present, even mundane facts.
5. Aim for at least 8-15 entities and 5-10 relations per non-trivial chunk. Headers / table-of-contents / bibliography chunks may yield fewer.

Example output for "NVIDIA achieved 100% renewable electricity in FY25, reducing Scope 2 emissions by 14%.":
{{
  "entities": [
    {{"name": "NVIDIA", "type": "Organization"}},
    {{"name": "Renewable electricity", "type": "Initiative"}},
    {{"name": "100%", "type": "Value"}},
    {{"name": "FY25", "type": "TimePeriod"}},
    {{"name": "Scope 2 emissions", "type": "Metric"}},
    {{"name": "14% reduction", "type": "Value"}}
  ],
  "relations": [
    {{"subject": "NVIDIA", "predicate": "reports", "object": "Renewable electricity", "evidence": "NVIDIA achieved 100% renewable electricity"}},
    {{"subject": "Renewable electricity", "predicate": "measured_in", "object": "100%", "evidence": "100% renewable electricity"}},
    {{"subject": "NVIDIA", "predicate": "reduces", "object": "Scope 2 emissions", "evidence": "reducing Scope 2 emissions by 14%"}},
    {{"subject": "Scope 2 emissions", "predicate": "measured_in", "object": "14% reduction", "evidence": "reducing Scope 2 emissions by 14%"}},
    {{"subject": "Renewable electricity", "predicate": "leads_to", "object": "Scope 2 emissions", "evidence": "100% renewable electricity ... reducing Scope 2 emissions"}}
  ]
}}

Now extract from the following text. Be comprehensive.

Text:
{text}

JSON:
"""

_VALUE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|percent|tco2e|tons|tonnes|mwh|kwh|employees|hours|usd|million|billion)\b", re.I)
_YEAR_PATTERN = re.compile(r"\b(?:FY\d{2,4}|19\d{2}|20\d{2})\b")
_COMPANY_PATTERN = re.compile(r"\b([A-Z]{2,}(?:\s+[A-Z]{2,})*)\b")
_TITLE_COMPANY_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3})'s\b")


def extract_esg(text: str) -> Dict:
    """Run inference on input text and return normalized ESG extraction JSON."""
    remote = extract_esg_with_deepseek(text)
    if remote is not None:
        return remote

    if ESG_EXTRACTION_BACKEND == "remote":
        fallback = _heuristic_extract_esg(text)
        fallback["raw"] = "heuristic_fallback_after_remote_unavailable"
        fallback["backend"] = "heuristic"
        return fallback

    try:
        import torch
        from ai_service.model_loader import get_model_and_tokenizer

        model, tokenizer = get_model_and_tokenizer()
        prompt = PROMPT_TEMPLATE.format(text=text.strip())

        inputs = tokenizer(prompt, return_tensors="pt")
        model_device = next(model.parameters()).device
        inputs = {key: value.to(model_device) for key, value in inputs.items()}

        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=1800,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated_tokens = output[0][inputs["input_ids"].shape[1]:]
        generated_text = tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

        if "JSON:" in generated_text:
            generated_text = generated_text.rsplit("JSON:", 1)[-1].strip()

        if not generated_text:
            raise RuntimeError("local extractor generated empty output")

        parsed = parse_json_safely(generated_text)
        normalized = normalize_result(parsed)
        if "raw" not in normalized and not normalized["entities"] and not normalized["relations"]:
            normalized["raw"] = generated_text
        normalized["backend"] = "local_qlora"
        return normalized
    except Exception as local_exc:
        fallback = _heuristic_extract_esg(text)
        fallback["raw"] = f"heuristic_fallback_after_local_error: {local_exc}"
        fallback["backend"] = "heuristic"
        return fallback


def _heuristic_extract_esg(text: str) -> Dict:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if sentence.strip()]
    entities: Dict[Tuple[str, str], Dict] = {}
    relations: Dict[Tuple[str, str, str], Dict] = {}
    company_name = _find_company_name(text)

    if company_name:
        company = _entity(company_name, "Company", f"Company referenced in the input text: {company_name}", 0.98)
        entities[(company["name"], company["type"])] = company

    for sentence in sentences:
        lower = sentence.lower()

        for year in _YEAR_PATTERN.findall(sentence):
            entity = _entity(year, "Year", sentence[:220], 0.9)
            entities[(entity["name"], entity["type"])] = entity

        for value in _VALUE_PATTERN.findall(sentence):
            entity = _entity(value, "Value", sentence[:220], 0.88)
            entities[(entity["name"], entity["type"])] = entity

        for metric in _match_metrics(sentence):
            entity = _entity(metric, "ESG Metric", sentence[:220], 0.84)
            entities[(entity["name"], entity["type"])] = entity
            if company_name:
                relation = _relation(company_name, metric, "HAS_METRIC", sentence[:300], 0.82)
                relations[(relation["source_entity"], relation["target_entity"], relation["relation_type"])] = relation

        for policy in _match_policy(sentence):
            entity = _entity(policy, "Policy", sentence[:220], 0.8)
            entities[(entity["name"], entity["type"])] = entity

        for risk in _match_risks(sentence):
            entity = _entity(risk, "Risk", sentence[:220], 0.8)
            entities[(entity["name"], entity["type"])] = entity
            if company_name:
                relation = _relation(company_name, risk, "FACES_RISK", sentence[:300], 0.79)
                relations[(relation["source_entity"], relation["target_entity"], relation["relation_type"])] = relation

        for target in _match_targets(sentence):
            entity = _entity(target, "Target", sentence[:220], 0.78)
            entities[(entity["name"], entity["type"])] = entity
            if company_name:
                relation = _relation(company_name, target, "HAS_TARGET", sentence[:300], 0.78)
                relations[(relation["source_entity"], relation["target_entity"], relation["relation_type"])] = relation

        for event in _match_events(sentence):
            entity = _entity(event, "Event", sentence[:220], 0.72)
            entities[(entity["name"], entity["type"])] = entity
            if company_name:
                relation = _relation(event, company_name, "IMPACTS", sentence[:300], 0.68)
                relations[(relation["source_entity"], relation["target_entity"], relation["relation_type"])] = relation

    for policy in [item for item in entities.values() if item["type"] == "Policy"]:
        for metric in [item for item in entities.values() if item["type"] == "ESG Metric"]:
            relation = _relation(policy["name"], metric["name"], "AFFECTS", policy["description"][:300], 0.67)
            relations[(relation["source_entity"], relation["target_entity"], relation["relation_type"])] = relation

    return {
        "entities": list(entities.values()),
        "relations": list(relations.values()),
    }


def _find_company_name(text: str) -> str | None:
    for pattern in (_TITLE_COMPANY_PATTERN, _COMPANY_PATTERN):
        for match in pattern.findall(text):
            name = str(match).strip()
            if name.lower() in {"the", "in", "this", "that"}:
                continue
            return name
    return None


def _match_metrics(sentence: str) -> List[str]:
    keywords = [
        "scope 1 emissions",
        "scope 2 emissions",
        "scope 3 emissions",
        "market-based emissions",
        "renewable electricity",
        "renewable energy procurement",
        "greenhouse gas emissions",
        "freshwater use",
        "water management initiative",
        "climate risk",
        "ai safety",
    ]
    return [keyword for keyword in keywords if keyword in sentence.lower()]


def _match_policy(sentence: str) -> List[str]:
    lower = sentence.lower()
    if "policy" in lower or "oversight" in lower:
        return [sentence[:120]]
    return []


def _match_risks(sentence: str) -> List[str]:
    matches = []
    lower = sentence.lower()
    for keyword in ("transition risk", "physical risk", "climate risk", "risk"):
        if keyword in lower:
            matches.append(keyword if keyword != "risk" else sentence[:120])
    return list(dict.fromkeys(matches))


def _match_targets(sentence: str) -> List[str]:
    lower = sentence.lower()
    if any(keyword in lower for keyword in ("target", "goal", "aim", "commitment")):
        patterns = [
            r"(target to [^.,;]+)",
            r"(goal to [^.,;]+)",
            r"(aims? to [^.,;]+)",
            r"(commit(?:ment)? to [^.,;]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, sentence, flags=re.I)
            if match:
                return [match.group(1).strip()[:120]]
        return [sentence[:120]]
    return []


def _match_events(sentence: str) -> List[str]:
    lower = sentence.lower()
    if any(keyword in lower for keyword in ("announced", "expanded", "launched", "introduced")):
        return [sentence[:120]]
    return []


def _entity(name: str, entity_type: str, description: str, confidence: float) -> Dict:
    return {
        "name": name.strip(),
        "type": entity_type,
        "description": description.strip(),
        "source_chunk_id": "input_text",
        "confidence": confidence,
    }


def _relation(source: str, target: str, relation_type: str, evidence: str, confidence: float) -> Dict:
    return {
        "source_entity": source.strip(),
        "target_entity": target.strip(),
        "relation_type": relation_type,
        "evidence": evidence.strip(),
        "source_chunk_id": "input_text",
        "confidence": confidence,
    }
