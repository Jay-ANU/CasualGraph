"""Structured ESG scenario prediction backed by OpenAI JSON output.

Deprecated: replaced by the Deep tier (``rag.claude_answering``) which returns
free-form markdown instead of a constrained JSON schema. Nothing in the live
RAG pipeline imports this module anymore; left in place for one release in
case external scripts still reference it. Slated for removal.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from configs.settings import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_TIMEOUT,
    RAG_PREDICTION_ENABLED,
    RAG_PREDICTION_MAX_TOKENS,
    RAG_PREDICTION_MODEL,
    RAG_PREDICTION_TEMPERATURE,
    openai_configured,
)
from rag.openai_client import get_openai_client
from rag.openai_compat import chat_token_kwargs


SYSTEM_PROMPT = """You are an ESG analyst providing scenario reasoning. You answer hypothetical or
predictive questions about ESG strategies and their potential downstream effects
(financial, reputational, regulatory).

You MUST output a single JSON object with exactly these fields:
{
  "prediction": "<one to three sentence summary of the most likely outcome>",
  "confidence": "low" | "medium" | "high",
  "causal_chain": [
    {
      "step": "<one sentence describing this link in the chain>",
      "source_type": "report_evidence" | "graph_inference" | "general_knowledge" | "speculation",
      "evidence_refs": ["chunk_0", "G3", ...]
    }
  ],
  "key_assumptions": ["<assumption 1>", "<assumption 2>"],
  "counter_evidence": ["<reason this prediction could be wrong>"],
  "disclaimer": "This is scenario reasoning, not investment advice."
}

Rules:
- Every step in causal_chain MUST have a source_type. Never blur sources.
- Use "report_evidence" only when you cite an explicit chunk id from the excerpts.
- Use "graph_inference" only when you cite a Gn id from the graph context.
- Use "general_knowledge" for widely accepted domain facts (e.g. "renewable
  electricity reduces Scope 2 emissions").
- If a step claims a financial outcome (stock price, valuation, returns,
  cost of capital, margin) WITHOUT a chunk_n or prior_n citation, it MUST
  be marked "speculation", not "general_knowledge".
- "general_knowledge" is reserved for non-controversial domain facts, not for
  contested causal links between ESG actions and financial market outcomes.
- Use "speculation" for any leap that is neither evidenced nor general knowledge.
- confidence should reflect overall evidence quality. Do NOT automatically mark
  confidence low just because one speculative step exists.
- If the question is purely factual and not predictive, still produce the JSON
  but mark confidence="high" and use only "report_evidence" / "graph_inference"
  steps.
- Never output investment recommendations. Phrase financial impact in terms of
  directionality and rough magnitude only.
- If a pre-computed causal chain is provided, use it as the backbone of your
  causal_chain output and mark those steps as graph_inference.
- For "general_knowledge" steps, prefer citing prior_n or reg_n ids when available.
- If a prior_n directly supports a quantitative claim, you may cite a rough
  magnitude and mark the source as "report_evidence" pointing to the prior_n.
- Output ONLY the JSON object. No prose before or after."""

DISCLAIMER = "This is scenario reasoning, not investment advice."
STEP_SOURCE_WEIGHTS = {
    "report_evidence": 1.0,
    "graph_inference": 0.85,
    "general_knowledge": 0.6,
    "speculation": 0.25,
}


def prediction_available() -> bool:
    return bool(RAG_PREDICTION_ENABLED and openai_configured())


def generate_prediction(
    question: str,
    sources: List[Dict],
    graph_context: Optional[str],
    history_block: str = "",
    priors: Optional[List[Dict]] = None,
    regulatory: Optional[List[Dict]] = None,
    sub_questions: Optional[List[str]] = None,
) -> Dict:
    """Return a structured prediction dict without falling back to local models."""
    if not prediction_available():
        return _fallback_prediction("Prediction mode requires OpenAI; not configured.")

    try:
        import openai
    except Exception as exc:
        return _fallback_prediction(f"Prediction mode requires OpenAI; import failed: {type(exc).__name__}.")

    context_from_sources = _format_sources(sources)
    priors_block = _format_prefixed_sources(priors or [], prefix="prior")
    regulatory_block = _format_prefixed_sources(regulatory or [], prefix="reg")
    precomputed_chain = _build_precomputed_causal_chain(openai, question)
    user_prompt = f"""{history_block}

Graph context (Gn):
{graph_context or "No graph context retrieved."}

{precomputed_chain}

Report excerpts (chunk_n):
{context_from_sources or "No retrieved excerpts."}

Academic priors (prior_n):
{priors_block or "No academic priors retrieved."}

Regulatory context (reg_n):
{regulatory_block or "No regulatory context retrieved."}

Sub-questions covered:
{_format_sub_questions(sub_questions)}

Question:
{question}"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = _call_openai_json(openai, messages)
    except Exception as exc:
        return _fallback_prediction(f"Prediction generation failed: {type(exc).__name__}: {exc}")

    try:
        parsed = json.loads(raw)
    except Exception as exc:
        fallback = _fallback_prediction("Prediction JSON parsing failed.")
        fallback["raw"] = raw
        fallback["parse_error"] = f"{type(exc).__name__}: {exc}"
        return fallback

    normalized = _normalize_prediction(parsed)
    _ensure_precomputed_chain_step(normalized, precomputed_chain)
    normalized["raw"] = raw
    normalized["parse_error"] = None
    return normalized


def _call_openai_json(openai, messages: List[Dict[str, str]]) -> str:
    if hasattr(openai, "OpenAI"):
        client = get_openai_client()
        if client is None:
            raise RuntimeError("OpenAI client unavailable")
        response = client.chat.completions.create(
            model=RAG_PREDICTION_MODEL,
            temperature=RAG_PREDICTION_TEMPERATURE,
            messages=messages,
            response_format={"type": "json_object"},
            **chat_token_kwargs(RAG_PREDICTION_MODEL, RAG_PREDICTION_MAX_TOKENS),
        )
        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            print(
                f"[prediction] JSON output truncated by max_tokens "
                f"(RAG_PREDICTION_MAX_TOKENS={RAG_PREDICTION_MAX_TOKENS}); JSON parsing will likely fail. "
                f"Raise RAG_PREDICTION_MAX_TOKENS in .env."
            )
        return (choice.message.content or "").strip()

    openai.api_key = OPENAI_API_KEY
    if OPENAI_BASE_URL:
        openai.api_base = OPENAI_BASE_URL
    response = openai.ChatCompletion.create(
        model=RAG_PREDICTION_MODEL,
        temperature=RAG_PREDICTION_TEMPERATURE,
        messages=messages,
        response_format={"type": "json_object"},
        request_timeout=OPENAI_TIMEOUT,
        **chat_token_kwargs(RAG_PREDICTION_MODEL, RAG_PREDICTION_MAX_TOKENS),
    )
    choice = response["choices"][0]
    if choice.get("finish_reason") == "length":
        print(
            f"[prediction] JSON output truncated by max_tokens "
            f"(RAG_PREDICTION_MAX_TOKENS={RAG_PREDICTION_MAX_TOKENS}); JSON parsing will likely fail. "
            f"Raise RAG_PREDICTION_MAX_TOKENS in .env."
        )
    return (choice["message"]["content"] or "").strip()


def _build_precomputed_causal_chain(openai, question: str) -> str:
    endpoints = _extract_causal_endpoints(openai, question)
    source = endpoints.get("source")
    target = endpoints.get("target")
    if not source or not target:
        return "Pre-computed causal chain (from knowledge graph):\nNo causal path pre-computed."

    try:
        from graph.causal_reasoning import CausalReasoner
        from graph.neo4j_store import get_neo4j_store

        store = get_neo4j_store()
        if store is None:
            return "Pre-computed causal chain (from knowledge graph):\nNo causal path pre-computed."
        source = _resolve_graph_entity(store, source) or source
        target = _resolve_graph_entity(store, target) or target
        result = CausalReasoner(store).shortest_path(source, target, max_depth=5)
    except Exception:
        return "Pre-computed causal chain (from knowledge graph):\nNo causal path pre-computed."

    paths = result.get("paths") or []
    if not paths:
        return "Pre-computed causal chain (from knowledge graph):\nNo causal path pre-computed."

    path = paths[0]
    nodes = path.get("nodes") or []
    edges = path.get("edges") or []
    node_name = {node.get("id"): node.get("name") or node.get("id") for node in nodes}
    if not edges:
        return "Pre-computed causal chain (from knowledge graph):\nNo causal path pre-computed."

    segments = [node_name.get(edges[0].get("source"), edges[0].get("source"))]
    for edge in edges:
        segments.append(f"--{edge.get('causal_type') or 'causes'}-->")
        segments.append(node_name.get(edge.get("target"), edge.get("target")))
    chain = " ".join(str(item) for item in segments if item)
    return (
        "Pre-computed causal chain (from knowledge graph):\n"
        f"[G_PATH_1] {chain}\n"
        f"path_score={path.get('path_score')}, net_polarity={path.get('net_polarity')}"
    )


def _extract_causal_endpoints(openai, question: str) -> Dict[str, str]:
    messages = [
        {
            "role": "system",
            "content": (
                "Extract the likely source and target entities for a causal ESG question. "
                "Return JSON only: {\"source\": \"...\", \"target\": \"...\"}. "
                "Use empty strings if unclear."
            ),
        },
        {"role": "user", "content": question},
    ]
    try:
        if hasattr(openai, "OpenAI"):
            client = get_openai_client()
            if client is None:
                return {"source": "", "target": ""}
            response = client.chat.completions.create(
                model=RAG_PREDICTION_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                **chat_token_kwargs(RAG_PREDICTION_MODEL, 80),
            )
            raw = (response.choices[0].message.content or "").strip()
        else:
            openai.api_key = OPENAI_API_KEY
            if OPENAI_BASE_URL:
                openai.api_base = OPENAI_BASE_URL
            response = openai.ChatCompletion.create(
                model=RAG_PREDICTION_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                request_timeout=OPENAI_TIMEOUT,
                **chat_token_kwargs(RAG_PREDICTION_MODEL, 80),
            )
            raw = (response["choices"][0]["message"]["content"] or "").strip()
        parsed = json.loads(raw)
        return {"source": str(parsed.get("source") or "").strip(), "target": str(parsed.get("target") or "").strip()}
    except Exception:
        return {"source": "", "target": ""}


def _resolve_graph_entity(store, value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    terms = _entity_terms(value)
    if not terms:
        return value

    def operation():
        with store._session() as session:
            rows = session.run(
                """
                UNWIND $terms AS term
                MATCH (e:Entity)
                WHERE toLower(e.id) CONTAINS term
                   OR toLower(e.name) CONTAINS term
                   OR toLower(e.normalized_name) CONTAINS term
                WITH e, count(DISTINCT term) AS matched_terms
                RETURN e.id AS id, e.name AS name, matched_terms
                ORDER BY matched_terms DESC, size(coalesce(e.name, e.id)) ASC
                LIMIT 1
                """,
                terms=terms,
            ).single()
            return dict(rows) if rows else None

    try:
        row = store._run_with_reconnect(operation)
    except Exception:
        return value
    return str(row.get("id") or row.get("name") or value) if row else value


def _entity_terms(value: str) -> List[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "effect",
        "effects",
        "impact",
        "impacts",
        "its",
        "of",
        "on",
        "strategy",
        "the",
        "to",
    }
    normalized = value.replace("_", " ").lower()
    return [token for token in normalized.split() if len(token) >= 3 and token not in stopwords][:8]


def _format_sources(sources: List[Dict]) -> str:
    return "\n\n".join(
        f"[{item.get('chunk_id')}] {item.get('text', '')}"
        for item in sources
        if item.get("chunk_id") and item.get("text")
    )


def _format_prefixed_sources(sources: List[Dict], prefix: str) -> str:
    lines = []
    for index, item in enumerate(sources):
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{prefix}_{index}] {text}")
    return "\n\n".join(lines)


def _format_sub_questions(sub_questions: Optional[List[str]]) -> str:
    values = [str(item).strip() for item in (sub_questions or []) if str(item).strip()]
    if not values:
        return "No decomposition was applied."
    return "\n".join(f"- {item}" for item in values)


def _normalize_prediction(value: Dict) -> Dict:
    confidence = str(value.get("confidence") or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    causal_chain = value.get("causal_chain")
    if not isinstance(causal_chain, list):
        causal_chain = []
    normalized_chain = []
    for item in causal_chain:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("source_type") or "speculation").strip()
        if source_type not in {"report_evidence", "graph_inference", "general_knowledge", "speculation"}:
            source_type = "speculation"
        refs = item.get("evidence_refs")
        evidence_refs = [str(ref) for ref in refs] if isinstance(refs, list) else []
        if source_type == "general_knowledge" and _is_uncited_financial_claim(str(item.get("step") or ""), evidence_refs):
            source_type = "speculation"
        normalized_chain.append(
            {
                "step": str(item.get("step") or "").strip(),
                "source_type": source_type,
                "evidence_refs": evidence_refs,
            }
        )
    key_assumptions = _string_list(value.get("key_assumptions"))
    counter_evidence = _string_list(value.get("counter_evidence"))
    scoring = _compute_confidence_scoring(
        chain=normalized_chain,
        key_assumptions=key_assumptions,
        counter_evidence=counter_evidence,
        llm_confidence=confidence,
    )
    confidence = scoring["confidence"]

    return {
        "prediction": str(value.get("prediction") or "").strip() or "Prediction could not be generated from the available context.",
        "confidence": confidence,
        "confidence_score": scoring["confidence_score"],
        "confidence_breakdown": scoring["confidence_breakdown"],
        "confidence_rationale": scoring["confidence_rationale"],
        "causal_chain": normalized_chain,
        "key_assumptions": key_assumptions,
        "counter_evidence": counter_evidence,
        "disclaimer": str(value.get("disclaimer") or DISCLAIMER).strip() or DISCLAIMER,
        "raw": "",
        "parse_error": None,
    }


def _compute_confidence_scoring(
    chain: List[Dict],
    key_assumptions: List[str],
    counter_evidence: List[str],
    llm_confidence: str,
) -> Dict[str, object]:
    total_steps = max(len(chain), 1)
    grounded_steps = sum(1 for item in chain if item.get("source_type") in {"report_evidence", "graph_inference"})
    speculative_steps = sum(1 for item in chain if item.get("source_type") == "speculation")
    referenced_steps = sum(1 for item in chain if len(item.get("evidence_refs") or []) > 0)
    weighted_quality = 0.0
    for item in chain:
        source_type = str(item.get("source_type") or "speculation")
        weighted_quality += STEP_SOURCE_WEIGHTS.get(source_type, STEP_SOURCE_WEIGHTS["speculation"])

    evidence_coverage = (grounded_steps / total_steps) * 100
    source_quality = (weighted_quality / total_steps) * 100
    citation_density = (referenced_steps / total_steps) * 100
    speculation_load = (speculative_steps / total_steps) * 100
    counter_pressure = min(len(counter_evidence) * 20, 60)
    assumption_pressure = min(len(key_assumptions) * 5, 25)
    consistency = max(20.0, 100.0 - counter_pressure - (speculation_load * 0.25))

    raw_score = (
        18.0
        + (0.32 * evidence_coverage)
        + (0.24 * source_quality)
        + (0.16 * consistency)
        + (0.14 * citation_density)
        - (0.16 * speculation_load)
        - (0.08 * counter_pressure)
        - (0.04 * assumption_pressure)
    )

    if not chain:
        raw_score = min(raw_score, 22.0)
    if speculative_steps >= max(2, total_steps // 2 + 1):
        raw_score -= 12.0
    if grounded_steps >= max(2, total_steps - 1) and speculative_steps == 0:
        raw_score += 6.0

    llm_bias = {"low": -4.0, "medium": 0.0, "high": 4.0}.get(llm_confidence, 0.0)
    score = int(max(0, min(100, round(raw_score + llm_bias))))

    if score >= 76:
        confidence = "high"
    elif score >= 46:
        confidence = "medium"
    else:
        confidence = "low"

    if not chain and confidence != "low":
        confidence = "low"
    if speculative_steps >= max(3, int(total_steps * 0.7)) and confidence == "high":
        confidence = "medium"

    rationale_parts = []
    if evidence_coverage >= 70:
        rationale_parts.append("strong report/graph grounding")
    elif evidence_coverage >= 40:
        rationale_parts.append("partial grounding")
    else:
        rationale_parts.append("limited direct grounding")

    if speculation_load >= 45:
        rationale_parts.append("high speculative load")
    elif speculation_load >= 20:
        rationale_parts.append("some speculative links")
    else:
        rationale_parts.append("low speculative load")

    if counter_pressure >= 40:
        rationale_parts.append("notable counter-evidence")
    elif counter_pressure > 0:
        rationale_parts.append("some counter-evidence")
    else:
        rationale_parts.append("little counter-evidence")

    rationale = ", ".join(rationale_parts)

    return {
        "confidence": confidence,
        "confidence_score": score,
        "confidence_breakdown": {
            "evidence_coverage": int(round(evidence_coverage)),
            "source_quality": int(round(source_quality)),
            "citation_density": int(round(citation_density)),
            "speculation_load": int(round(speculation_load)),
            "counter_pressure": int(round(counter_pressure)),
            "assumption_pressure": int(round(assumption_pressure)),
        },
        "confidence_rationale": rationale,
    }


def _is_uncited_financial_claim(step: str, refs: List[str]) -> bool:
    text = step.lower()
    financial_terms = (
        "stock price",
        "share price",
        "valuation",
        "valuation premium",
        "returns",
        "investment return",
        "cost of capital",
        "margin",
        "margins",
        "multiple",
        "risk premium",
    )
    if not any(term in text for term in financial_terms):
        return False
    return not any(ref.startswith(("chunk_", "prior_")) for ref in refs)


def _ensure_precomputed_chain_step(prediction: Dict, precomputed_chain: str) -> None:
    if "[G_PATH_1]" not in precomputed_chain:
        return
    chain = prediction.get("causal_chain")
    if not isinstance(chain, list):
        prediction["causal_chain"] = []
        chain = prediction["causal_chain"]
    if any(isinstance(item, dict) and item.get("source_type") == "graph_inference" for item in chain):
        return

    step_text = next(
        (line.replace("[G_PATH_1]", "").strip() for line in precomputed_chain.splitlines() if "[G_PATH_1]" in line),
        "The knowledge graph contains a pre-computed causal path relevant to this prediction.",
    )
    chain.insert(
        0,
        {
            "step": step_text,
            "source_type": "graph_inference",
            "evidence_refs": ["G_PATH_1"],
        },
    )


def _string_list(value) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _fallback_prediction(message: str) -> Dict:
    return {
        "prediction": message,
        "confidence": "low",
        "confidence_score": 15,
        "confidence_breakdown": {
            "evidence_coverage": 0,
            "source_quality": 0,
            "citation_density": 0,
            "speculation_load": 100,
            "counter_pressure": 0,
            "assumption_pressure": 0,
        },
        "confidence_rationale": "fallback response without grounded prediction evidence",
        "causal_chain": [],
        "key_assumptions": [],
        "counter_evidence": [],
        "disclaimer": DISCLAIMER,
        "raw": "",
        "parse_error": None,
    }
