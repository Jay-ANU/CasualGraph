from rag.source_relevance import filter_sources_by_relevance, source_relevance_score


def test_low_relevance_source_is_filtered():
    sources = [
        {
            "chunk_id": "weak",
            "text": "Across all scopes, carbon footprint was reduced by 40 percent.",
        },
        {
            "chunk_id": "strong",
            "text": "Climate transition risk includes supply-chain regulation and emissions exposure.",
        },
    ]
    filtered = filter_sources_by_relevance(
        "Compare climate transition risks across all reports with evidence.",
        sources,
        min_score=0.35,
    )
    assert [item["chunk_id"] for item in filtered] == ["strong"]
    assert filtered[0]["relevance_score"] >= 0.35


def test_source_relevance_ignores_generic_report_words():
    score = source_relevance_score(
        "Compare climate transition risks across all reports with evidence.",
        "Across all scopes, carbon footprint was reduced by 40 percent.",
    )
    assert score is not None
    assert score < 0.35
