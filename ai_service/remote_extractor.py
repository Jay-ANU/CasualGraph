"""Remote ESG extraction fallback using DeepSeek's OpenAI-compatible API."""

from __future__ import annotations

from typing import Optional

from ai_service.utils import normalize_result, parse_json_safely
from configs.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_EXTRACTION_MODEL,
    DEEPSEEK_EXTRACTION_MAX_TOKENS,
    DEEPSEEK_TIMEOUT,
    deepseek_configured,
)


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


def deepseek_extraction_available() -> bool:
    """Return whether a DeepSeek extraction backend is configured."""
    return deepseek_configured()


def extract_esg_with_deepseek(text: str) -> Optional[dict]:
    """Call DeepSeek's OpenAI-compatible API and normalize the JSON output."""
    if not deepseek_extraction_available():
        return None

    try:
        import openai
    except Exception:
        return None

    prompt = PROMPT_TEMPLATE.format(text=text.strip())
    messages = [{"role": "user", "content": prompt}]

    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=DEEPSEEK_TIMEOUT,
            )
            response = client.chat.completions.create(
                model=DEEPSEEK_EXTRACTION_MODEL,
                temperature=0,
                max_tokens=DEEPSEEK_EXTRACTION_MAX_TOKENS,
                response_format={"type": "json_object"},
                messages=messages,
            )
            generated_text = (response.choices[0].message.content or "").strip()
        else:
            openai.api_key = DEEPSEEK_API_KEY
            openai.api_base = DEEPSEEK_BASE_URL
            response = openai.ChatCompletion.create(
                model=DEEPSEEK_EXTRACTION_MODEL,
                temperature=0,
                max_tokens=DEEPSEEK_EXTRACTION_MAX_TOKENS,
                messages=messages,
                request_timeout=DEEPSEEK_TIMEOUT,
            )
            generated_text = (response["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        print(f"[extractor] DeepSeek extraction failed: {type(exc).__name__}: {exc}")
        return None

    if "JSON:" in generated_text:
        generated_text = generated_text.rsplit("JSON:", 1)[-1].strip()

    if not generated_text:
        finish_reason = getattr(response.choices[0], "finish_reason", None) if hasattr(response, "choices") else None
        message = response.choices[0].message if hasattr(response, "choices") else None
        reasoning = getattr(message, "reasoning_content", "") if message is not None else ""
        print(
            "[extractor] DeepSeek extraction returned empty output "
            f"(finish_reason={finish_reason}, reasoning_len={len(reasoning or '')})"
        )
        return None

    parsed = parse_json_safely(generated_text)
    normalized = normalize_result(parsed)
    if "raw" not in normalized and not normalized["entities"] and not normalized["relations"]:
        normalized["raw"] = generated_text
    normalized["backend"] = "deepseek_api"
    return normalized
