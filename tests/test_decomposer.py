from unittest.mock import patch

from rag.query_decomposer import decompose_query


def test_decomposer_disabled_without_openai_returns_original_for_simple_question():
    with patch("rag.query_decomposer.openai_configured", return_value=False):
        result = decompose_query("What was the 2023 Scope 1 emissions?")

    assert result["subquestions"] == ["What was the 2023 Scope 1 emissions?"]
    assert result["is_compound"] is False
