"""Provider-neutral prompts and citation contracts for grounded research."""

from typing import Dict, List, Optional

# Shared with OpenAI side so callers can detect the same "evidence missing" string.
INSUFFICIENT_CONTEXT_ANSWER = (
    "The provided reports do not contain enough information to answer this question."
)

_TRUNCATION_NOTICE = (
    "\n\n_[Response truncated at the RAG_DEEP_MAX_TOKENS limit. "
    "Ask a follow-up to continue, or raise RAG_DEEP_MAX_TOKENS in your .env.]_"
)


_SYSTEM_PROMPT = (
    "You are an ESG research analyst working from a structured corpus of "
    "company sustainability reports.\n\n"
    "When the question is analytical, comparative, or predictive, organise "
    "your answer with markdown headings such as 'Evidence', 'Reasoning', and "
    "'Conclusion'. When the question is purely factual, give a direct answer "
    "without forcing the structure.\n\n"
    "Always cite sources inline using the markers you see in the context:\n"
    "- `[chunk_N]` for retrieved report passages\n"
    "- `[prior_N]` for historical comparisons\n"
    "- `[reg_N]` for regulatory references\n"
    "- `[G_N]` for graph entities or edges\n\n"
    "Be explicit about uncertainty. Never invent figures, dates, or company "
    "statements. If the evidence is insufficient, answer plainly: "
    f"{INSUFFICIENT_CONTEXT_ANSWER}"
)


def _format_source_block(label: str, sources: List[Dict]) -> str:
    """Wrap a list of retrieved chunks in a provider-neutral XML-like tag.

    Context is separated using ``<sources>...</sources>`` blocks.
    Each source carries its own ``[chunk_N]`` / ``[prior_N]`` / ``[reg_N]``
    label so the model can cite inline.
    """
    if not sources:
        return ""
    lines = []
    for item in sources:
        chunk_id = item.get("chunk_id") or item.get("id") or ""
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{chunk_id}] {text}" if chunk_id else text)
    if not lines:
        return ""
    body = "\n\n".join(lines)
    return f"<{label}>\n{body}\n</{label}>"


def build_grounded_request(
    *,
    question: str,
    sources: List[Dict],
    priors: Optional[List[Dict]],
    regulatory: Optional[List[Dict]],
    graph_context: Optional[str],
    history_block: str,
    answer_intent: str = "evidence",
) -> Dict[str, object]:
    """Build a grounded system/user prompt shared across providers."""
    sections: List[str] = []
    if history_block:
        sections.append(f"<history>\n{history_block.strip()}\n</history>")
    sources_block = _format_source_block("sources", sources)
    if sources_block:
        sections.append(sources_block)
    priors_block = _format_source_block("priors", priors or [])
    if priors_block:
        sections.append(priors_block)
    reg_block = _format_source_block("regulatory", regulatory or [])
    if reg_block:
        sections.append(reg_block)
    if graph_context:
        sections.append(f"<graph>\n{graph_context.strip()}\n</graph>")
    sections.append(f"<question>\n{question.strip()}\n</question>")
    if answer_intent == "general":
        sections.append(
            "<instruction>This is a general guidance question. Answer directly without requiring report evidence, and do not cite uploaded-report markers.</instruction>"
        )
    elif answer_intent == "hybrid":
        sections.append(
            "<instruction>Use report evidence first when available. If evidence is incomplete or missing, clearly separate a General analysis section and do not present it as report-backed. For prediction, rating, scoring, recommendation, or scenario questions, do not answer with only the insufficient-context sentence; state the evidence limit and provide a cautious qualitative analysis or scoring framework.</instruction>"
        )
    elif not sources_block and not priors_block and not reg_block:
        # Tell the model upfront so it follows the INSUFFICIENT_CONTEXT contract.
        sections.append(
            "<note>No relevant report excerpts were retrieved for this question.</note>"
        )
    user_content = "\n\n".join(sections)
    return {
        "system": _system_prompt_for_intent(answer_intent),
        "messages": [{"role": "user", "content": user_content}],
    }


def _system_prompt_for_intent(answer_intent: str) -> str:
    if answer_intent == "general":
        return (
            "You are a practical ESG, business, and academic research assistant. "
            "The user is asking for general guidance, not a report-grounded answer. "
            "Answer directly in concise markdown. Do not claim that your answer comes from uploaded reports, "
            "do not invent company-specific facts, and do not include report citations."
        )
    if answer_intent == "hybrid":
        return (
            _SYSTEM_PROMPT
            + "\n\nFor hybrid questions, use retrieved report evidence first and cite it. "
            "If report evidence is incomplete or missing, clearly separate a 'General analysis' section. "
            "For prediction, rating, scoring, recommendation, or scenario questions, do not answer with only "
            f"'{INSUFFICIENT_CONTEXT_ANSWER}'; state the evidence limit and provide a cautious qualitative analysis or scoring framework. "
            "Do not present general reasoning as report-backed."
        )
    return _SYSTEM_PROMPT
