"""Per-request retrieval scope for /rag/ask: document scoping, routing hints and entity terms."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chat_memory_service import RedisUnavailableError, chat_memory_service
from configs.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    RAG_ANSWER_INTENT_ROUTER_MODEL,
    RAG_ANSWER_INTENT_ROUTER_TIMEOUT,
    deepseek_configured,
)
from rag import deepseek_resilience
from services.auth import _is_admin_user
from services.document_access import (
    _can_retrieve_entry,
    _collect_document_entries,
    _is_global_entry,
    _retrievable_registry_entries,
)


_ENTITY_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9&.-]*")
_ENTITY_OF_PATTERN = re.compile(
    r"\b(?:of|for|about|by|from|at|on)\s+([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3})"
)
_ENTITY_POSSESSIVE_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3})['’]s\b")
_ENTITY_ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,8}\b")
_ENTITY_TITLE_PHRASE_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){1,4})\b")
_ENTITY_SPLIT_PATTERN = re.compile(r"[^A-Za-z0-9&]+")
_COMPARISON_REQUEST_PATTERN = re.compile(
    r"\b(compare|contrast|versus|vs\.?|between|across|difference|different|differ|main difference|which|better|worse)\b|"
    r"比较|对比|差异|区别|哪个",
    re.I,
)
_COMPARISON_BETWEEN_PATTERN = re.compile(
    r"\bbetween\s+(.+?)\s+and\s+(.+?)(?=,|\?|\.|\b(?:what|why|how|which|who|where|when|would|will|can|should|is|are)\b|$)",
    re.I,
)
_COMPARISON_VERUS_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,4})\s+(?:vs\.?|versus)\s+([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,4})\b",
    re.I,
)
_COMPARISON_COMPARE_PATTERN = re.compile(
    r"\b(?:compare|contrast)\s+(?:between\s+)?(.+?)\s+(?:and|with|against|to|versus|vs\.?)\s+(.+?)(?=,|\?|\.|\b(?:on|by|for|in|about|what|why|how|which|who|where|when)\b|$)",
    re.I,
)
_SINGLE_ENTITY_TITLE_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,4}\b")
_ENTITY_ALIAS_MAP: Dict[str, Tuple[str, ...]] = {}
_DOCUMENT_ENTITY_TERMS_CACHE: Dict[str, Tuple[float, set[str]]] = {}
_ENTITY_STOP_WORDS = {
    "a",
    "about",
    "and",
    "annual",
    "be",
    "can",
    "company",
    "across",
    "compare",
    "could",
    "document",
    "esg",
    "effects",
    "explain",
    "for",
    "from",
    "give",
    "governance",
    "i",
    "in",
    "inc",
    "is",
    "its",
    "know",
    "limited",
    "llc",
    "ltd",
    "me",
    "of",
    "on",
    "please",
    "price",
    "report",
    "reports",
    "responsibility",
    "share",
    "show",
    "something",
    "strategy",
    "summarise",
    "summarize",
    "sustainability",
    "tell",
    "that",
    "these",
    "this",
    "those",
    "the",
    "to",
    "want",
    "what",
    "would",
    "year",
}


class RagAskRequest(BaseModel):
    question: str
    top_k: int = 5
    history: List[Dict[str, Any]] = []
    session_id: Optional[str] = None
    document_ids: List[str] = []
    preferred_document_id: Optional[str] = None
    document_group: Optional[str] = None
    source_type: Optional[str] = None
    domain: Optional[str] = None
    # Deprecated: legacy intent selector (ask | predict | graph). The pipeline
    # now drives behavior entirely off `reasoning_mode` (flash | deep). Kept on
    # the schema so older clients don't fail validation; the value is ignored.
    mode: Optional[str] = "ask"
    reasoning_mode: Optional[str] = "flash"


def _parse_json_object_text(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object")
    return parsed


def _normalize_entity_token(value: str) -> str:
    return str(value or "").strip(" .,!?:;()[]{}\"'’").lower()


def _filtered_entity_tokens(value: str) -> List[str]:
    normalized = _ENTITY_SPLIT_PATTERN.sub(" ", str(value or ""))
    tokens = [_normalize_entity_token(match.group(0)) for match in _ENTITY_TOKEN_PATTERN.finditer(normalized)]
    return [token for token in tokens if len(token) >= 2 and token not in _ENTITY_STOP_WORDS]


def _append_entity_term(terms: List[str], value: str) -> None:
    normalized = " ".join(_filtered_entity_tokens(value))
    if normalized and normalized not in terms:
        terms.append(normalized)


def _alias_terms_for_entity(tokens: List[str], joined: str) -> List[str]:
    keys = {joined, *tokens}
    if 1 < len(tokens) <= 6:
        acronym = "".join(token[0] for token in tokens if token)
        if len(acronym) >= 2:
            keys.add(acronym)
    if "american" in tokens and any(token in {"flight", "flights", "airline", "airlines"} for token in tokens):
        keys.add("american flight")
    aliases: List[str] = []
    for key in keys:
        aliases.extend(_ENTITY_ALIAS_MAP.get(key, ()))
    return aliases


def _terms_from_document_value(value: str) -> set[str]:
    tokens = _filtered_entity_tokens(value)
    terms = set(tokens)
    if 1 < len(tokens) <= 16:
        max_size = min(4, len(tokens))
        for size in range(2, max_size + 1):
            for index in range(0, len(tokens) - size + 1):
                terms.add(" ".join(tokens[index:index + size]))
    return terms


def _graph_entity_terms(graph_path: str) -> set[str]:
    if not graph_path:
        return set()
    path = Path(graph_path)
    if not path.exists() or not path.is_file():
        return set()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return set()

    cache_key = str(path.resolve())
    cached = _DOCUMENT_ENTITY_TERMS_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return set(cached[1])

    terms: set[str] = set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _DOCUMENT_ENTITY_TERMS_CACHE[cache_key] = (mtime, terms)
        return terms

    nodes = payload.get("nodes") if isinstance(payload, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    for node in nodes[:500]:
        if not isinstance(node, dict):
            continue
        for key in ("id", "name", "label", "title"):
            terms.update(_terms_from_document_value(str(node.get(key) or "")))
        properties = node.get("properties") or node.get("metadata") or {}
        if isinstance(properties, dict):
            for key in ("name", "display_name", "label", "title"):
                terms.update(_terms_from_document_value(str(properties.get(key) or "")))

    _DOCUMENT_ENTITY_TERMS_CACHE[cache_key] = (mtime, terms)
    return set(terms)


def _extract_query_entity_terms(question: str) -> List[str]:
    text = str(question or "")
    terms: List[str] = []

    def add_phrase(phrase: str) -> None:
        tokens = _filtered_entity_tokens(phrase)
        if not tokens:
            return
        # Keep both phrase-level and token-level keys so "Apple Inc." can match
        # either "apple inc" or an uploaded file named "apple-report.pdf".
        joined = " ".join(tokens)
        candidates = [joined, *tokens, *_alias_terms_for_entity(tokens, joined)]
        for value in candidates:
            if value and value not in terms:
                _append_entity_term(terms, value)

    for pattern in (_ENTITY_OF_PATTERN, _ENTITY_POSSESSIVE_PATTERN, _ENTITY_TITLE_PHRASE_PATTERN):
        for match in pattern.finditer(text):
            add_phrase(match.group(1))

    lowered = text.lower()
    for alias in _ENTITY_ALIAS_MAP:
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            add_phrase(alias)

    for match in _ENTITY_ACRONYM_PATTERN.finditer(text):
        token = _normalize_entity_token(match.group(0))
        if token and token not in _ENTITY_STOP_WORDS and token not in terms:
            terms.append(token)

    return terms


def _document_entity_terms(entry: Dict[str, Any]) -> set[str]:
    values = [
        entry.get("document_id", ""),
        entry.get("title", ""),
        entry.get("source", ""),
    ]
    paths = entry.get("paths") or {}
    values.extend([paths.get("processed_text", ""), paths.get("chunks", ""), paths.get("graph", ""), paths.get("vector_store", "")])

    terms: set[str] = set()
    for value in values:
        terms.update(_terms_from_document_value(str(value or "")))
    terms.update(_graph_entity_terms(str(paths.get("graph") or "")))
    return terms


def _document_identity_terms(entry: Dict[str, Any]) -> set[str]:
    values = [
        entry.get("document_id", ""),
        entry.get("title", ""),
        entry.get("source", ""),
    ]
    paths = entry.get("paths") or {}
    values.extend([paths.get("processed_text", ""), paths.get("chunks", ""), paths.get("vector_store", "")])
    terms: set[str] = set()
    for value in values:
        terms.update(_terms_from_document_value(str(value or "")))
    return terms


def _document_scope_candidates(
    query_terms: List[str],
    entries: List[Dict[str, Any]],
    *,
    limit: int = 12,
    include_zero: bool = False,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for entry in entries:
        document_id = str(entry.get("document_id") or "").strip()
        if not document_id:
            continue
        document_terms = _document_entity_terms(entry)
        score, matched_terms = _document_scope_score(query_terms, document_terms)
        identity_score, identity_matched_terms = _document_scope_score(query_terms, _document_identity_terms(entry))
        if score <= 0 and not include_zero:
            continue
        candidates.append({
            "document_id": document_id,
            "title": str(entry.get("title") or "").strip(),
            "source": str(entry.get("source") or "").strip(),
            "document_group": str(entry.get("document_group") or "").strip(),
            "score": round(score, 4),
            "matched_terms": matched_terms,
            "identity_score": round(identity_score, 4),
            "matched_identity_terms": identity_matched_terms,
            "terms": _display_document_terms(document_terms),
        })
    candidates.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -float(item.get("identity_score") or 0.0),
            str(item.get("title") or ""),
            str(item.get("document_id") or ""),
        )
    )
    return candidates[: max(1, limit)]


def _document_scope_score(query_terms: List[str], document_terms: set[str]) -> Tuple[float, List[str]]:
    if not query_terms or not document_terms:
        return 0.0, []

    score = 0.0
    matched: List[str] = []
    document_phrases = [term for term in document_terms if " " in term]
    for term in query_terms:
        term_tokens = term.split()
        if term in document_terms:
            score += 12.0 if " " in term else 5.0
            matched.append(term)
            continue
        if len(term_tokens) > 1:
            overlap = len(set(term_tokens) & document_terms) / max(1, len(set(term_tokens)))
            if overlap >= 0.75:
                score += 8.0 * overlap
                matched.append(term)
                continue
            if overlap >= 0.5:
                score += 3.0 * overlap
                matched.append(term)
                continue
            fuzzy = _best_term_similarity(term, document_phrases)
            if fuzzy >= 0.78:
                score += 6.0 * fuzzy
                matched.append(term)
            elif fuzzy >= 0.58:
                score += 2.0 * fuzzy
                matched.append(term)
        else:
            if len(term) <= 2:
                continue
            fuzzy = _best_term_similarity(term, list(document_terms))
            if fuzzy >= 0.78:
                score += 4.0 * fuzzy
                matched.append(term)
            elif fuzzy >= 0.5:
                score += 1.5 * fuzzy
                matched.append(term)
    return score, _dedupe_entity_terms(matched)


def _best_term_similarity(term: str, candidates: List[str]) -> float:
    best = 0.0
    for candidate in candidates[:250]:
        ratio = SequenceMatcher(None, term, candidate).ratio()
        if ratio > best:
            best = ratio
    return best


def _display_document_terms(document_terms: set[str], limit: int = 18) -> List[str]:
    ordered = sorted(
        (term for term in document_terms if len(term) >= 2),
        key=lambda value: (0 if " " in value else 1, len(value), value),
    )
    return ordered[:limit]


def _dedupe_entity_terms(values: List[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        key = str(value or "").strip().lower()
        if not key or key in seen:
            continue
        output.append(key)
        seen.add(key)
    return output


def _confident_document_ids_from_candidates(candidates: List[Dict[str, Any]]) -> List[str]:
    if not candidates:
        return []
    top_score = float(candidates[0].get("score") or 0.0)
    if top_score < 5.0:
        return []
    tied = [item for item in candidates if abs(float(item.get("score") or 0.0) - top_score) < 0.001]
    next_score = 0.0
    for item in candidates:
        score = float(item.get("score") or 0.0)
        if score < top_score:
            next_score = score
            break
    if len(tied) == 1 and (top_score >= 10.0 or top_score - next_score >= 2.0):
        return [str(tied[0].get("document_id") or "")]
    if 1 < len(tied) <= 3 and top_score >= 10.0:
        return [str(item.get("document_id") or "") for item in tied if str(item.get("document_id") or "").strip()]
    return []


def _positive_document_ids_from_candidates(
    candidates: List[Dict[str, Any]],
    limit: int = 8,
    *,
    require_identity: bool = False,
) -> List[str]:
    if not candidates:
        return []
    top_score = float(candidates[0].get("score") or 0.0)
    if top_score < 5.0:
        return []
    top_candidates = [
        item
        for item in candidates
        if abs(float(item.get("score") or 0.0) - top_score) < 0.001
    ]
    identity_matches = [item for item in top_candidates if float(item.get("identity_score") or 0.0) > 0]
    strong_identity_matches = [item for item in identity_matches if float(item.get("identity_score") or 0.0) >= min(5.0, top_score)]
    if require_identity and not identity_matches:
        return []
    selected_candidates = strong_identity_matches or identity_matches or top_candidates
    output: List[str] = []
    for item in selected_candidates:
        document_id = str(item.get("document_id") or "").strip()
        if document_id and document_id not in output:
            output.append(document_id)
        if len(output) >= limit:
            break
    return output


def _resolve_document_ids_with_deepseek(
    question: str,
    candidates: List[Dict[str, Any]],
    query_terms: List[str],
) -> List[str]:
    if not candidates:
        return []
    cache_payload = {
        "question": str(question or "").strip(),
        "query_terms": list(query_terms or []),
        "candidates": [
            {
                "document_id": item.get("document_id"),
                "score": item.get("score"),
                "identity_score": item.get("identity_score"),
                "matched_terms": item.get("matched_terms") or [],
            }
            for item in candidates[:12]
        ],
        "model": RAG_ANSWER_INTENT_ROUTER_MODEL,
    }
    cache_hit, cached_value = deepseek_resilience.cache_lookup("document_resolver", cache_payload)
    if cache_hit:
        return [str(item).strip() for item in (cached_value or []) if str(item).strip()][:3]
    if deepseek_resilience.circuit_is_open("document_resolver") or not deepseek_configured():
        return []
    try:
        import openai
    except Exception:
        return []

    candidate_payload = [
        {
            "document_id": item.get("document_id"),
            "title": item.get("title"),
            "source": item.get("source"),
            "matched_terms": item.get("matched_terms") or [],
            "terms": item.get("terms") or [],
        }
        for item in candidates[:12]
    ]
    prompt = {
        "task": "Choose which uploaded document(s) the user is referring to. Return an empty list if none fit.",
        "rules": [
            "Use company names, abbreviations, file names, report titles, and graph/entity terms.",
            "Handle informal references and likely misspellings, but do not guess when candidates are unrelated.",
            "Return only document_id values from the candidate list.",
        ],
        "question": question,
        "extracted_query_terms": query_terms,
        "candidates": candidate_payload,
        "schema": {"document_ids": ["candidate_document_id"], "confidence": 0.0, "reason": "short reason"},
    }
    messages = [
        {"role": "system", "content": "You are a document entity resolver. Return JSON only."},
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]
    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(
                max_retries=0,
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=min(float(RAG_ANSWER_INTENT_ROUTER_TIMEOUT), 8.0),
            )
            response = client.chat.completions.create(
                extra_body={"thinking": {"type": "disabled"}},
                model=RAG_ANSWER_INTENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=220,
            )
            raw = response.choices[0].message.content or ""
        else:
            openai.api_key = DEEPSEEK_API_KEY
            openai.api_base = DEEPSEEK_BASE_URL
            response = openai.ChatCompletion.create(
                model=RAG_ANSWER_INTENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                request_timeout=min(float(RAG_ANSWER_INTENT_ROUTER_TIMEOUT), 8.0),
                max_tokens=220,
            )
            raw = response["choices"][0]["message"]["content"] or ""
        parsed = _parse_json_object_text(str(raw))
    except Exception as exc:
        deepseek_resilience.cache_failure("document_resolver", cache_payload)
        deepseek_resilience.record_failure("document_resolver")
        print(f"[rag.document_resolver] DeepSeek resolver skipped: {type(exc).__name__}: {exc}")
        return []

    allowed_ids = {str(item.get("document_id") or "").strip() for item in candidates}
    confidence = 0.0
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.45:
        deepseek_resilience.cache_store("document_resolver", cache_payload, [])
        deepseek_resilience.record_success("document_resolver")
        return []
    resolved: List[str] = []
    for value in parsed.get("document_ids") or []:
        document_id = str(value or "").strip()
        if document_id and document_id in allowed_ids and document_id not in resolved:
            resolved.append(document_id)
    resolved = resolved[:3]
    deepseek_resilience.cache_store("document_resolver", cache_payload, resolved)
    deepseek_resilience.record_success("document_resolver")
    return resolved


def _scope_document_ids_for_query(question: str, entries: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    query_terms = _extract_query_entity_terms(question)
    if not query_terms:
        return [], []

    candidates = _document_scope_candidates(query_terms, entries, include_zero=False)
    confident_ids = _confident_document_ids_from_candidates(candidates)
    if confident_ids:
        return confident_ids, query_terms
    identity_positive_ids = _positive_document_ids_from_candidates(candidates, require_identity=True)
    if identity_positive_ids:
        return identity_positive_ids, query_terms

    resolver_candidates = candidates or _document_scope_candidates(query_terms, entries, include_zero=True)
    resolved_ids = _resolve_document_ids_with_deepseek(question, resolver_candidates, query_terms)
    if resolved_ids:
        return resolved_ids, query_terms

    positive_ids = _positive_document_ids_from_candidates(candidates)
    if positive_ids:
        return positive_ids, query_terms

    return [], query_terms


def _maybe_narrow_requested_document_scope(
    *,
    scope_question: str,
    entries: List[Dict[str, Any]],
    allowed_ids: set[str],
    effective_document_ids: List[str],
    preferred_document_id: Optional[str],
) -> Tuple[List[str], Optional[str], List[str], bool]:
    """Narrow a broad selected-document set when the query resolves to specific entities."""
    requested_ids = {str(item).strip() for item in effective_document_ids if str(item).strip()}
    if preferred_document_id:
        requested_ids.add(preferred_document_id)
    if not requested_ids:
        return effective_document_ids, preferred_document_id, [], False

    scoped_ids, scoped_terms = _scope_document_ids_for_query(scope_question, entries)
    scoped_allowed_ids = sorted(set(scoped_ids) & allowed_ids)
    if not scoped_allowed_ids:
        return effective_document_ids, preferred_document_id, scoped_terms, False

    scoped_set = set(scoped_allowed_ids)
    should_replace = requested_ids.isdisjoint(scoped_set) or (
        len(requested_ids) > 1 and scoped_set < requested_ids
    )
    if not should_replace:
        return effective_document_ids, preferred_document_id, scoped_terms, False

    next_preferred = preferred_document_id if preferred_document_id in scoped_set else None
    return scoped_allowed_ids, next_preferred, scoped_terms, True


def _terms_for_entity_phrase(phrase: str) -> List[str]:
    tokens = _filtered_entity_tokens(phrase)
    if not tokens:
        return []
    terms: List[str] = []
    joined = " ".join(tokens)
    acronym = "".join(token[0] for token in tokens if token) if 1 < len(tokens) <= 6 else ""
    for value in (joined, *tokens, acronym, *_alias_terms_for_entity(tokens, joined)):
        if value:
            _append_entity_term(terms, value)
    return terms


def _entity_label_from_terms(terms: List[str]) -> str:
    for term in terms:
        if " " in term:
            return term
    return terms[0] if terms else ""


def _append_entity_group(groups: List[List[str]], phrase: str) -> None:
    terms = _terms_for_entity_phrase(phrase)
    if not terms:
        return
    primary = _entity_label_from_terms(terms)
    if not primary or primary in _ENTITY_STOP_WORDS:
        return
    term_set = set(terms)
    for existing in groups:
        existing_set = set(existing)
        if term_set == existing_set:
            return
        if primary in existing_set or _entity_label_from_terms(existing) in term_set:
            return
    groups.append(terms)


def _clean_comparison_entity_phrase(value: str) -> str:
    text = str(value or "").strip(" \t\r\n,.;:!?()[]{}\"'’")
    text = re.sub(
        r"\b(?:what|why|how|which|who|where|when|would|will|can|should|is|are|the|main|difference|carbon|emission|emissions).*$",
        "",
        text,
        flags=re.I,
    ).strip(" \t\r\n,.;:!?()[]{}\"'’")
    return text


def _extract_query_entity_term_groups(question: str) -> List[List[str]]:
    text = str(question or "")
    groups: List[List[str]] = []

    if _COMPARISON_REQUEST_PATTERN.search(text):
        for pattern in (_COMPARISON_BETWEEN_PATTERN, _COMPARISON_COMPARE_PATTERN, _COMPARISON_VERUS_PATTERN):
            for match in pattern.finditer(text):
                _append_entity_group(groups, _clean_comparison_entity_phrase(match.group(1)))
                _append_entity_group(groups, _clean_comparison_entity_phrase(match.group(2)))

        for match in _SINGLE_ENTITY_TITLE_PATTERN.finditer(text):
            phrase = _clean_comparison_entity_phrase(match.group(0))
            tokens = _filtered_entity_tokens(phrase)
            if not tokens:
                continue
            if len(tokens) == 1 and tokens[0] in _ENTITY_STOP_WORDS:
                continue
            _append_entity_group(groups, phrase)

    if not groups:
        terms = _extract_query_entity_terms(text)
        if terms:
            groups.append(terms)
    return groups


def _scope_document_ids_for_terms(query_terms: List[str], entries: List[Dict[str, Any]], *, use_llm: bool = True) -> List[str]:
    if not query_terms:
        return []
    candidates = _document_scope_candidates(query_terms, entries, include_zero=False)
    for resolver in (
        _confident_document_ids_from_candidates,
        lambda items: _positive_document_ids_from_candidates(items, require_identity=True),
    ):
        ids = resolver(candidates)
        if ids:
            return ids
    if not use_llm:
        return _positive_document_ids_from_candidates(candidates)
    resolver_candidates = candidates or _document_scope_candidates(query_terms, entries, include_zero=True)
    resolved_ids = _resolve_document_ids_with_deepseek(" ".join(query_terms), resolver_candidates, query_terms)
    if resolved_ids:
        return resolved_ids
    return _positive_document_ids_from_candidates(candidates)


def _dedupe_document_ids(document_ids: List[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in document_ids:
        document_id = str(value or "").strip()
        if not document_id or document_id in seen:
            continue
        output.append(document_id)
        seen.add(document_id)
    return output


def _build_sub_questions(question: str, entity_labels: List[str]) -> List[str]:
    base = str(question or "").strip()
    if len(entity_labels) < 2:
        return [base] if base else []
    focus = "carbon emission" if re.search(r"\bcarbon emissions?\b|碳排|碳排放", base, re.I) else "relevant evidence"
    sub_questions = [f"Find {focus} evidence for {label}." for label in entity_labels]
    sub_questions.append(base)
    return sub_questions


def _request_router_candidates(entries: List[Dict[str, Any]], limit: int = 40) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for entry in entries[:limit]:
        document_id = str(entry.get("document_id") or "").strip()
        if not document_id:
            continue
        candidates.append({
            "document_id": document_id,
            "title": str(entry.get("title") or "").strip(),
            "source": str(entry.get("source") or "").strip(),
            "document_group": str(entry.get("document_group") or "").strip(),
        })
    return candidates


def _route_request_with_deepseek(question: str, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = _request_router_candidates(entries)
    if not candidates:
        return None
    cache_payload = {
        "question": str(question or "").strip(),
        "candidates": candidates,
        "model": RAG_ANSWER_INTENT_ROUTER_MODEL,
    }
    cache_hit, cached_value = deepseek_resilience.cache_lookup("request_router", cache_payload)
    if cache_hit:
        return dict(cached_value) if isinstance(cached_value, dict) else None
    if deepseek_resilience.circuit_is_open("request_router") or not deepseek_configured():
        return None
    try:
        import openai
    except Exception:
        return None

    prompt = {
        "task": "Route an ESG/report assistant request. Identify entities, target uploaded documents, sub-questions, answer mode, and whether an agent should be used.",
        "rules": [
            "Return only document_id values from candidates.",
            "Use agent for multi-entity comparisons, multi-question requests, why/explain comparisons, uncertainty analysis, or cross-document synthesis.",
            "Use evidence or hybrid for company/report questions; use general only when no report evidence is needed.",
            "If unsure about documents, leave target_document_ids empty but still list entities and sub_questions.",
        ],
        "question": question,
        "candidates": candidates,
        "schema": {
            "mode": "evidence|general|hybrid|chitchat",
            "entities": ["entity name"],
            "target_document_ids": ["candidate_document_id"],
            "sub_questions": ["short retrieval question"],
            "needs_agent": True,
            "confidence": 0.0,
            "reason": "short reason",
        },
    }
    messages = [
        {"role": "system", "content": "You are a structured routing controller. Return JSON only."},
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]
    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(
                max_retries=0,
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=min(float(RAG_ANSWER_INTENT_ROUTER_TIMEOUT), 8.0),
            )
            response = client.chat.completions.create(
                extra_body={"thinking": {"type": "disabled"}},
                model=RAG_ANSWER_INTENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=420,
            )
            raw = response.choices[0].message.content or ""
        else:
            openai.api_key = DEEPSEEK_API_KEY
            openai.api_base = DEEPSEEK_BASE_URL
            response = openai.ChatCompletion.create(
                model=RAG_ANSWER_INTENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                request_timeout=min(float(RAG_ANSWER_INTENT_ROUTER_TIMEOUT), 8.0),
                max_tokens=420,
            )
            raw = response["choices"][0]["message"]["content"] or ""
        parsed = _parse_json_object_text(str(raw))
    except Exception as exc:
        deepseek_resilience.cache_failure("request_router", cache_payload)
        deepseek_resilience.record_failure("request_router")
        print(f"[rag.request_router] DeepSeek request router fell back: {type(exc).__name__}: {exc}")
        return None

    allowed_ids = {item["document_id"] for item in candidates}
    target_ids = _dedupe_document_ids([str(value or "") for value in parsed.get("target_document_ids") or [] if str(value or "").strip() in allowed_ids])
    mode = str(parsed.get("mode") or "evidence").strip().lower()
    if mode not in {"evidence", "general", "hybrid", "chitchat"}:
        mode = "evidence"
    try:
        confidence = max(0.0, min(float(parsed.get("confidence") or 0.0), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    result = {
        "mode": mode,
        "entities": _dedupe_entity_terms([str(item or "") for item in parsed.get("entities") or []]),
        "target_document_ids": target_ids,
        "sub_questions": [str(item).strip() for item in parsed.get("sub_questions") or [] if str(item).strip()][:6],
        "needs_agent": bool(parsed.get("needs_agent")),
        "confidence": confidence,
        "reason": f"deepseek:{str(parsed.get('reason') or 'request_route')}",
    }
    deepseek_resilience.cache_store("request_router", cache_payload, result)
    deepseek_resilience.record_success("request_router")
    return result


def _merge_routing_hints(local_hint: Dict[str, Any], llm_hint: Optional[Dict[str, Any]], question: str) -> Dict[str, Any]:
    if not llm_hint:
        return local_hint
    merged = dict(local_hint)
    merged["mode"] = str(llm_hint.get("mode") or merged.get("mode") or "evidence")
    merged["entities"] = _dedupe_entity_terms([*list(merged.get("entities") or []), *list(llm_hint.get("entities") or [])])
    merged["target_document_ids"] = _dedupe_document_ids([*list(merged.get("target_document_ids") or []), *list(llm_hint.get("target_document_ids") or [])])
    sub_questions = [*list(llm_hint.get("sub_questions") or []), *list(merged.get("sub_questions") or [])]
    merged["sub_questions"] = [item for index, item in enumerate(sub_questions) if item and item not in sub_questions[:index]][:6]
    merged["needs_agent"] = bool(merged.get("needs_agent") or llm_hint.get("needs_agent"))
    merged["confidence"] = max(float(merged.get("confidence") or 0.0), float(llm_hint.get("confidence") or 0.0))
    merged["reason"] = str(llm_hint.get("reason") or merged.get("reason") or "entity_scope")
    if not merged.get("sub_questions"):
        merged["sub_questions"] = _build_sub_questions(question, list(merged.get("entities") or []))
    return merged


def _build_request_routing_hint(question: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups = _extract_query_entity_term_groups(question)
    entity_labels = [_entity_label_from_terms(group) for group in groups if _entity_label_from_terms(group)]
    target_ids: List[str] = []
    for group in groups:
        target_ids.extend(_scope_document_ids_for_terms(group, entries, use_llm=False))
    target_ids = _dedupe_document_ids(target_ids)
    comparison_request = bool(_COMPARISON_REQUEST_PATTERN.search(str(question or "")))
    needs_agent = (comparison_request and len(entity_labels) >= 2) or len(target_ids) >= 2
    mode = "hybrid" if needs_agent else "evidence"
    confidence = 0.82 if needs_agent and target_ids else 0.62 if target_ids else 0.45
    local_hint = {
        "mode": mode,
        "entities": entity_labels,
        "target_document_ids": target_ids,
        "sub_questions": _build_sub_questions(question, entity_labels),
        "needs_agent": needs_agent,
        "confidence": confidence,
        "reason": "comparison_entity_scope" if needs_agent else "entity_scope",
    }
    if (comparison_request and len(target_ids) < 2) or not target_ids:
        return _merge_routing_hints(local_hint, _route_request_with_deepseek(question, entries), question)
    return local_hint


def _routing_hint_with_document_ids(routing_hint: Optional[Dict[str, Any]], document_ids: List[str]) -> Optional[Dict[str, Any]]:
    if not routing_hint:
        return None
    hint = dict(routing_hint)
    hint["target_document_ids"] = _dedupe_document_ids(document_ids or list(hint.get("target_document_ids") or []))
    return hint


def _question_with_recent_user_context(question: str, history: Optional[List[Dict[str, Any]]]) -> str:
    recent_user_turns: List[str] = []
    for item in reversed(history or []):
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        recent_user_turns.append(content)
        if len(recent_user_turns) >= 2:
            break
    parts = [*reversed(recent_user_turns), str(question or "").strip()]
    return "\n".join(part for part in parts if part)


def _no_accessible_documents_response() -> Dict[str, Any]:
    return {"error_response": JSONResponse(
        status_code=403,
        content={"answer": "", "sources": [], "error": "no_accessible_documents", "message": "No accessible documents for this account."},
    )}


def _resolve_rag_request_context(request: RagAskRequest, current_user: Optional[dict]) -> Dict[str, Any]:
    effective_document_ids = [str(item).strip() for item in (request.document_ids or []) if str(item).strip()]
    preferred_document_id = str(request.preferred_document_id or "").strip() or None
    entity_scope_miss = False
    entity_scope_terms: List[str] = []
    document_scope_source: Optional[str] = None
    routing_hint: Optional[Dict[str, Any]] = None
    history = request.history
    memory_backend = "disabled"
    if request.session_id and current_user:
        try:
            history = chat_memory_service.get_recent_history(
                user_id=str(current_user["id"]),
                session_id=str(request.session_id),
            )
            memory_backend = "redis"
        except RedisUnavailableError:
            memory_backend = "disabled"
    scope_question = _question_with_recent_user_context(request.question, history)
    if current_user and not _is_admin_user(current_user):
        retrievable_entries = _retrievable_registry_entries(current_user)
        allowed_ids = {str(entry.get("document_id") or "").strip() for entry in retrievable_entries if str(entry.get("document_id") or "").strip()}
        routing_hint = _build_request_routing_hint(scope_question, retrievable_entries)
        routing_document_ids = sorted(set(routing_hint.get("target_document_ids") or []) & allowed_ids)
        broad_retrievable_scope = False
        if effective_document_ids or preferred_document_id:
            (
                effective_document_ids,
                preferred_document_id,
                scoped_terms,
                scope_was_narrowed,
            ) = _maybe_narrow_requested_document_scope(
                scope_question=scope_question,
                entries=retrievable_entries,
                allowed_ids=allowed_ids,
                effective_document_ids=effective_document_ids,
                preferred_document_id=preferred_document_id,
            )
            if scope_was_narrowed:
                entity_scope_terms = scoped_terms
                document_scope_source = "entity_resolver"
        if preferred_document_id:
            if preferred_document_id not in allowed_ids:
                return _no_accessible_documents_response()
            if not effective_document_ids:
                effective_document_ids = [preferred_document_id]
        if effective_document_ids:
            effective_document_ids = [doc_id for doc_id in effective_document_ids if doc_id in allowed_ids]
        else:
            scoped_ids, entity_scope_terms = (routing_document_ids, list(routing_hint.get("entities") or [])) if routing_document_ids else _scope_document_ids_for_query(scope_question, retrievable_entries)
            if scoped_ids:
                effective_document_ids = sorted(set(scoped_ids) & allowed_ids)
                document_scope_source = "entity_resolver"
            elif entity_scope_terms and not preferred_document_id:
                global_ids = {
                    str(entry.get("document_id") or "").strip()
                    for entry in retrievable_entries
                    if _is_global_entry(entry) and str(entry.get("document_id") or "").strip()
                }
                if global_ids:
                    # Global KB should remain searchable even when the target entity
                    # is not encoded in the document title/source metadata.
                    effective_document_ids = sorted(global_ids & allowed_ids)
                else:
                    entity_scope_miss = True
                    effective_document_ids = []
            else:
                # Broad user search is already safely constrained by owner/global
                # metadata filters in the vector store. Do not enumerate every
                # accessible document ID here; large $in filters can make Pinecone
                # slow or exceed request limits.
                broad_retrievable_scope = bool(allowed_ids)
                effective_document_ids = []
        if not effective_document_ids:
            if not entity_scope_miss and not broad_retrievable_scope:
                return _no_accessible_documents_response()
    elif current_user and _is_admin_user(current_user):
        retrievable_entries = _retrievable_registry_entries(current_user)
        allowed_ids = {str(entry.get("document_id") or "").strip() for entry in retrievable_entries if str(entry.get("document_id") or "").strip()}
        routing_hint = _build_request_routing_hint(scope_question, retrievable_entries)
        if effective_document_ids or preferred_document_id:
            effective_document_ids = [doc_id for doc_id in effective_document_ids if doc_id in allowed_ids]
            (
                effective_document_ids,
                preferred_document_id,
                scoped_terms,
                scope_was_narrowed,
            ) = _maybe_narrow_requested_document_scope(
                scope_question=scope_question,
                entries=retrievable_entries,
                allowed_ids=allowed_ids,
                effective_document_ids=effective_document_ids,
                preferred_document_id=preferred_document_id,
            )
            if scope_was_narrowed:
                entity_scope_terms = scoped_terms
                document_scope_source = "entity_resolver"
        else:
            scoped_ids = list(routing_hint.get("target_document_ids") or [])
            entity_scope_terms = list(routing_hint.get("entities") or [])
            if not scoped_ids:
                scoped_ids, entity_scope_terms = _scope_document_ids_for_query(scope_question, retrievable_entries)
            if scoped_ids:
                effective_document_ids = scoped_ids
                document_scope_source = "entity_resolver"
            elif entity_scope_terms:
                entity_scope_miss = True
    elif not current_user:
        public_entries = [entry for entry in _collect_document_entries() if _can_retrieve_entry(None, entry)]
        public_ids = {str(entry.get("document_id") or "").strip() for entry in public_entries if str(entry.get("document_id") or "").strip()}
        routing_hint = _build_request_routing_hint(scope_question, public_entries)
        routing_document_ids = sorted(set(routing_hint.get("target_document_ids") or []) & public_ids)
        if preferred_document_id:
            if preferred_document_id not in public_ids:
                return _no_accessible_documents_response()
            effective_document_ids = [preferred_document_id]
        elif effective_document_ids:
            effective_document_ids = [doc_id for doc_id in effective_document_ids if doc_id in public_ids]
            if not effective_document_ids:
                return _no_accessible_documents_response()
        else:
            scoped_ids, entity_scope_terms = (routing_document_ids, list(routing_hint.get("entities") or [])) if routing_document_ids else _scope_document_ids_for_query(scope_question, public_entries)
            if scoped_ids:
                effective_document_ids = scoped_ids
                document_scope_source = "entity_resolver"
            elif entity_scope_terms:
                entity_scope_miss = True
            else:
                # Anonymous requests do not carry owner_user_id, so public/global
                # access must be enforced by explicit document IDs.
                effective_document_ids = sorted(public_ids)
        if not effective_document_ids and not entity_scope_miss:
            return _no_accessible_documents_response()

    filters = {
        "document_ids": effective_document_ids,
        "preferred_document_id": preferred_document_id,
        "document_group": request.document_group,
        "source_type": request.source_type,
        "domain": request.domain,
    }
    if current_user and not _is_admin_user(current_user):
        # Always scope non-admin retrieval to the caller's own and global documents, even when
        # document_ids were resolved: Deep's priors/regulatory layers search without document_ids.
        filters["owner_user_id"] = str(current_user.get("id") or "")
    filters["preferred_document_id"] = preferred_document_id
    if document_scope_source:
        filters["document_scope_source"] = document_scope_source
    scoped_routing_hint = _routing_hint_with_document_ids(routing_hint, effective_document_ids)
    if scoped_routing_hint:
        filters["routing_hint"] = scoped_routing_hint
    if entity_scope_miss:
        filters["entity_scope_miss"] = True
        filters["entity_scope_terms"] = entity_scope_terms

    return {
        "filters": filters,
        "history": history,
        "memory_backend": memory_backend,
        "user_id": str(current_user["id"]) if current_user else None,
        "error_response": None,
    }


def _load_request_history_for_rag(request: RagAskRequest, current_user: Optional[dict]) -> Tuple[List[Dict[str, Any]], str]:
    history = list(request.history or [])
    memory_backend = "disabled"
    if request.session_id and current_user:
        try:
            history = chat_memory_service.get_recent_history(
                user_id=str(current_user["id"]),
                session_id=str(request.session_id),
            )
            memory_backend = "redis"
        except RedisUnavailableError:
            memory_backend = "disabled"
    return history, memory_backend


def _resolve_general_rag_request_context(
    request: RagAskRequest,
    current_user: Optional[dict],
    history: List[Dict[str, Any]],
    memory_backend: str,
) -> Dict[str, Any]:
    effective_document_ids = [str(item).strip() for item in (request.document_ids or []) if str(item).strip()]
    preferred_document_id = str(request.preferred_document_id or "").strip() or None
    if preferred_document_id and preferred_document_id not in effective_document_ids:
        effective_document_ids.append(preferred_document_id)
    scope_question = _question_with_recent_user_context(request.question, history)
    document_scope_source: Optional[str] = None
    routing_hint: Optional[Dict[str, Any]] = None
    filters: Dict[str, Any] = {
        "document_ids": [],
        "preferred_document_id": preferred_document_id,
        "document_group": request.document_group,
        "source_type": request.source_type,
        "domain": request.domain,
        "answer_mode": "general",
    }
    if current_user and not _is_admin_user(current_user):
        retrievable_entries = _retrievable_registry_entries(current_user)
        allowed_ids = {
            str(entry.get("document_id") or "").strip()
            for entry in retrievable_entries
            if str(entry.get("document_id") or "").strip()
        }
        routing_hint = _build_request_routing_hint(scope_question, retrievable_entries)
        routing_document_ids = sorted(set(routing_hint.get("target_document_ids") or []) & allowed_ids)
        if effective_document_ids:
            effective_document_ids = [doc_id for doc_id in effective_document_ids if doc_id in allowed_ids]
            (
                effective_document_ids,
                preferred_document_id,
                _scoped_terms,
                scope_was_narrowed,
            ) = _maybe_narrow_requested_document_scope(
                scope_question=scope_question,
                entries=retrievable_entries,
                allowed_ids=allowed_ids,
                effective_document_ids=effective_document_ids,
                preferred_document_id=preferred_document_id,
            )
            if scope_was_narrowed:
                document_scope_source = "entity_resolver"
        else:
            scoped_ids = routing_document_ids
            if not scoped_ids:
                scoped_ids, _ = _scope_document_ids_for_query(scope_question, retrievable_entries)
            effective_document_ids = sorted(set(scoped_ids) & allowed_ids)
            if effective_document_ids:
                document_scope_source = "entity_resolver"
        if effective_document_ids:
            filters["document_ids"] = effective_document_ids
        # Same rule as _resolve_rag_request_context: the owner scope survives layers that drop document_ids.
        filters["owner_user_id"] = str(current_user.get("id") or "")
    elif current_user and _is_admin_user(current_user):
        retrievable_entries = _retrievable_registry_entries(current_user)
        allowed_ids = {
            str(entry.get("document_id") or "").strip()
            for entry in retrievable_entries
            if str(entry.get("document_id") or "").strip()
        }
        if effective_document_ids:
            effective_document_ids = [doc_id for doc_id in effective_document_ids if doc_id in allowed_ids]
            (
                effective_document_ids,
                preferred_document_id,
                _scoped_terms,
                scope_was_narrowed,
            ) = _maybe_narrow_requested_document_scope(
                scope_question=scope_question,
                entries=retrievable_entries,
                allowed_ids=allowed_ids,
                effective_document_ids=effective_document_ids,
                preferred_document_id=preferred_document_id,
            )
            if scope_was_narrowed:
                document_scope_source = "entity_resolver"
            filters["document_ids"] = effective_document_ids
        else:
            routing_hint = _build_request_routing_hint(scope_question, retrievable_entries)
            scoped_ids = list(routing_hint.get("target_document_ids") or [])
            if not scoped_ids:
                scoped_ids, _ = _scope_document_ids_for_query(scope_question, retrievable_entries)
            if scoped_ids:
                filters["document_ids"] = scoped_ids
                document_scope_source = "entity_resolver"
    elif not current_user:
        public_entries = [entry for entry in _collect_document_entries() if _can_retrieve_entry(None, entry)]
        public_ids = {
            str(entry.get("document_id") or "").strip()
            for entry in public_entries
            if str(entry.get("document_id") or "").strip()
        }
        routing_hint = _build_request_routing_hint(scope_question, public_entries)
        routing_document_ids = sorted(set(routing_hint.get("target_document_ids") or []) & public_ids)
        if effective_document_ids:
            filters["document_ids"] = [doc_id for doc_id in effective_document_ids if doc_id in public_ids]
        else:
            scoped_ids = routing_document_ids
            if not scoped_ids:
                scoped_ids, _ = _scope_document_ids_for_query(scope_question, public_entries)
            if scoped_ids:
                filters["document_ids"] = sorted(set(scoped_ids) & public_ids)
                if filters["document_ids"]:
                    document_scope_source = "entity_resolver"
    filters["preferred_document_id"] = preferred_document_id
    if document_scope_source:
        filters["document_scope_source"] = document_scope_source
    scoped_routing_hint = _routing_hint_with_document_ids(routing_hint, list(filters.get("document_ids") or []))
    if scoped_routing_hint:
        filters["routing_hint"] = scoped_routing_hint
    return {
        "filters": filters,
        "history": history,
        "memory_backend": memory_backend,
        "user_id": str(current_user["id"]) if current_user else None,
        "error_response": None,
    }
