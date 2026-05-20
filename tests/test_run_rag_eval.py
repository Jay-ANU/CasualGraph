from __future__ import annotations

from scripts.run_rag_eval import evaluate_response, load_cases


def test_load_cases_reads_yaml(tmp_path):
    path = tmp_path / "cases.yaml"
    path.write_text(
        """
version: 1
cases:
  - id: sample
    question: What is ESG?
""",
        encoding="utf-8",
    )

    cases = load_cases(path)

    assert cases == [{"id": "sample", "question": "What is ESG?"}]


def test_evaluate_response_checks_terms_and_sources():
    case = {
        "id": "sample",
        "required_answer_terms": ["climate"],
        "forbidden_answer_terms": ["database"],
        "min_sources": 1,
    }
    response = {
        "answer": "Climate risk is material.",
        "sources": [{"id": "chunk_1"}],
        "reasoning_mode": "flash",
        "retrieval_strategy": "hybrid",
        "timings_ms": {"total": 123},
    }

    result = evaluate_response(case, response)

    assert result["passed"] is True
    assert result["source_count"] == 1
    assert result["timings_ms"]["total"] == 123


def test_evaluate_response_reports_failures():
    case = {
        "id": "sample",
        "required_answer_terms": ["climate"],
        "forbidden_answer_terms": ["database"],
        "min_sources": 2,
    }
    response = {"answer": "This mentions database internals.", "sources": [{}]}

    result = evaluate_response(case, response)

    assert result["passed"] is False
    assert "missing_required_term:climate" in result["failures"]
    assert "contains_forbidden_term:database" in result["failures"]
    assert "source_count:1<2" in result["failures"]
