"""LLM-based metric extractor.

Single-chunk contract:
    extract_metrics_for_chunk(chunk_text, taxonomy, llm_callable) -> List[MetricRow]

The LLM call is injected so the same module is testable offline. The default
LLM client uses the OpenAI-compatible API with DeepSeek/OpenAI base URLs as
configured in `configs.settings`.

Design notes:
- JSON mode is required; non-JSON output is treated as a parse failure rather
  than retried — observability over silent retry.
- The prompt deliberately requests *both* the raw substring (`evidence_span`)
  and the parsed value, so we can later verify the LLM didn't fabricate the
  number by checking the substring is in the chunk.
- Confidence is reported by the model AND attenuated by post-checks
  (out-of-range value, evidence not found in chunk, unit not normalizable).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from metric_extraction.normalizer import normalize
from metric_extraction.store import MetricRow
from metric_extraction.taxonomy import MetricSpec, Taxonomy

EXTRACTOR_VERSION = "esg-metric-extractor-v1.0.0"

LLMCallable = Callable[[str, str], str]
"""(system_prompt, user_prompt) -> raw model output (expected JSON)."""


_SYSTEM_PROMPT = """You are an ESG metric extractor. Read the excerpt and extract ONLY values that match the provided taxonomy. Output strict JSON only — no commentary.

Rules:
1. Extract a value ONLY if it is explicitly stated in the excerpt with a unit and (where applicable) a year.
2. NEVER invent or infer values that are not directly stated.
3. The `evidence_span` MUST be an exact substring of the excerpt that supports the value (verbatim, including punctuation).
4. If the same metric is reported with multiple scopes (e.g. operational vs equity), output one row per scope.
5. If you are uncertain, set confidence below 0.6 and let downstream review handle it. Do not guess.
6. Output `{"metrics": []}` if nothing matches.
"""


_USER_TEMPLATE = """TAXONOMY (only extract these metric_ids; ignore everything else):
{taxonomy_block}

EXCERPT:
\"\"\"
{chunk_text}
\"\"\"

Return JSON exactly in this shape:
{{
  "metrics": [
    {{
      "metric_id": "<one of the metric_ids above>",
      "value": <number, the parsed numeric value>,
      "unit_as_reported": "<unit string as it appears in the excerpt>",
      "year": <integer year, or null if not stated>,
      "year_qualifier": "fiscal" | "calendar" | "restated" | null,
      "scope_qualifier": "<one of the metric's scope_qualifiers, or null>",
      "entity_hint": "<the company / org name from the excerpt, or null>",
      "confidence": <0.0–1.0>,
      "evidence_span": "<exact substring of the excerpt that supports this value>"
    }}
  ]
}}
"""


def _format_taxonomy_block(taxonomy: Taxonomy, restrict_to: Optional[Sequence[str]] = None) -> str:
    """Compact human-readable taxonomy listing for the prompt."""
    parts: List[str] = []
    metric_ids = restrict_to if restrict_to is not None else taxonomy.all_metric_ids()
    for metric_id in metric_ids:
        spec = taxonomy.get(metric_id)
        if spec is None:
            continue
        scope_options = (
            "scope_qualifiers: " + ", ".join(spec.scope_qualifiers)
            if spec.scope_qualifiers
            else "scope_qualifiers: null"
        )
        aliases = ", ".join(sorted(spec.aliases)[:8])
        parts.append(
            f"- {metric_id}\n"
            f"    description: {spec.description}\n"
            f"    canonical_unit: {spec.canonical_unit}\n"
            f"    {scope_options}\n"
            f"    common_aliases: {aliases}"
        )
    return "\n".join(parts)


def build_prompt(
    chunk_text: str,
    taxonomy: Taxonomy,
    restrict_to: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """Deterministic prompt builder. No LLM call. Unit-testable."""
    return {
        "system": _SYSTEM_PROMPT,
        "user": _USER_TEMPLATE.format(
            taxonomy_block=_format_taxonomy_block(taxonomy, restrict_to),
            chunk_text=chunk_text.strip(),
        ),
    }


@dataclass
class ParsedCandidate:
    metric_id: str
    raw_value: Optional[float]
    raw_unit: str
    year: Optional[int]
    year_qualifier: Optional[str]
    scope_qualifier: Optional[str]
    entity_hint: Optional[str]
    confidence: float
    evidence_span: str


def parse_response(raw_output: str) -> List[ParsedCandidate]:
    """Parse the LLM's JSON response into typed candidates. Tolerant of minor formatting noise."""
    text = (raw_output or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    metrics = data.get("metrics") if isinstance(data, dict) else data
    if not isinstance(metrics, list):
        return []

    out: List[ParsedCandidate] = []
    for item in metrics:
        if not isinstance(item, dict) or "metric_id" not in item:
            continue
        try:
            raw_value = item.get("value")
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        try:
            year_raw = item.get("year")
            year = int(year_raw) if year_raw is not None else None
        except (TypeError, ValueError):
            year = None
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append(
            ParsedCandidate(
                metric_id=str(item["metric_id"]).strip(),
                raw_value=value,
                raw_unit=str(item.get("unit_as_reported") or "").strip(),
                year=year,
                year_qualifier=item.get("year_qualifier"),
                scope_qualifier=item.get("scope_qualifier"),
                entity_hint=item.get("entity_hint"),
                confidence=max(0.0, min(1.0, confidence)),
                evidence_span=str(item.get("evidence_span") or "").strip(),
            )
        )
    return out


def _attenuate_confidence(
    candidate: ParsedCandidate,
    chunk_text: str,
    spec: MetricSpec,
    normalized_value: float,
    normalized_ok: bool,
) -> tuple[float, List[str]]:
    """Apply deterministic checks; reduce confidence when checks fail."""
    confidence = candidate.confidence
    notes: List[str] = []

    # Evidence span must appear verbatim in the chunk.
    if candidate.evidence_span and candidate.evidence_span not in chunk_text:
        confidence = min(confidence, 0.3)
        notes.append("evidence_span not found in chunk verbatim")

    # Magnitude sanity check (post-normalization).
    if normalized_ok and not (spec.expected_min <= normalized_value <= spec.expected_max):
        confidence = min(confidence, 0.4)
        notes.append(
            f"value {normalized_value} outside expected range "
            f"[{spec.expected_min}, {spec.expected_max}]"
        )

    # Unit failed to normalize.
    if not normalized_ok:
        confidence = min(confidence, 0.35)
        notes.append("unit not normalizable")

    # Scope qualifier outside enum.
    if spec.scope_qualifiers and candidate.scope_qualifier:
        if candidate.scope_qualifier not in spec.scope_qualifiers:
            confidence = min(confidence, 0.45)
            notes.append(f"scope_qualifier '{candidate.scope_qualifier}' not in enum")

    return confidence, notes


def _candidate_to_row(
    candidate: ParsedCandidate,
    *,
    document_id: str,
    chunk_id: Optional[str],
    chunk_text: str,
    taxonomy: Taxonomy,
) -> Optional[MetricRow]:
    spec = taxonomy.get(candidate.metric_id)
    if spec is None or candidate.raw_value is None:
        return None

    norm = normalize(candidate.raw_value, candidate.raw_unit, spec.canonical_unit)
    confidence, _notes = _attenuate_confidence(
        candidate,
        chunk_text=chunk_text,
        spec=spec,
        normalized_value=norm.value,
        normalized_ok=norm.normalized,
    )

    return MetricRow(
        document_id=document_id,
        chunk_id=chunk_id,
        entity_id=None,  # graph linkage is a v2 concern; populate from existing graph extractor later
        entity_hint=candidate.entity_hint,
        metric_id=candidate.metric_id,
        value=norm.value,
        unit=norm.unit,
        raw_value=candidate.raw_value,
        raw_unit=candidate.raw_unit,
        year=candidate.year,
        year_qualifier=candidate.year_qualifier,
        scope_qualifier=candidate.scope_qualifier,
        confidence=confidence,
        evidence_text=candidate.evidence_span or chunk_text[:500],
        extractor_version=EXTRACTOR_VERSION,
        taxonomy_version=taxonomy.version,
    )


def extract_metrics_for_chunk(
    chunk_text: str,
    taxonomy: Taxonomy,
    llm: LLMCallable,
    *,
    document_id: str,
    chunk_id: Optional[str] = None,
    restrict_to: Optional[Sequence[str]] = None,
) -> List[MetricRow]:
    """Run the full extract→parse→normalize→sanity-check pipeline for one chunk."""
    if not chunk_text or not chunk_text.strip():
        return []

    prompt = build_prompt(chunk_text, taxonomy, restrict_to)
    try:
        raw = llm(prompt["system"], prompt["user"])
    except Exception as exc:
        # Caller decides whether to retry; we return empty so the chunk is skipped.
        # Logged via observability layer if traced.
        raw = ""
        del exc

    candidates = parse_response(raw)
    rows: List[MetricRow] = []
    for candidate in candidates:
        row = _candidate_to_row(
            candidate,
            document_id=document_id,
            chunk_id=chunk_id,
            chunk_text=chunk_text,
            taxonomy=taxonomy,
        )
        if row is not None:
            rows.append(row)
    return rows


def default_llm_client() -> LLMCallable:
    """Build the default JSON-mode LLM client from settings.

    Uses DeepSeek when configured, otherwise OpenAI. Requires `openai>=1.0` SDK.
    """
    from openai import OpenAI

    from configs import settings as cfg

    if cfg.deepseek_configured():
        client = OpenAI(api_key=cfg.DEEPSEEK_API_KEY, base_url=cfg.DEEPSEEK_BASE_URL)
        model = cfg.DEEPSEEK_EXTRACTION_MODEL
        timeout = cfg.DEEPSEEK_TIMEOUT
    else:
        client = OpenAI(
            api_key=cfg.OPENAI_API_KEY,
            base_url=cfg.OPENAI_BASE_URL or None,
        )
        model = cfg.OPENAI_MODEL
        timeout = cfg.OPENAI_TIMEOUT

    def _call(system_prompt: str, user_prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=timeout,
        )
        return response.choices[0].message.content or ""

    return _call
