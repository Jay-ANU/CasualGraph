from rag.hybrid_agent_router import decide_hybrid_path


def test_small_talk_uses_fast_path():
    decision = decide_hybrid_path(
        question="hello",
        reasoning_mode="deep",
        document_ids=[],
        preferred_document_id=None,
        answer_intent={"mode": "chitchat", "confidence": 0.92},
    )
    assert decision.path == "fast"
    assert decision.budget.max_steps == 0
    assert decision.budget.deadline_seconds <= 5


def test_current_document_fact_uses_rag_path():
    decision = decide_hybrid_path(
        question="What is Apple's Scope 1 emissions target in this report?",
        reasoning_mode="flash",
        document_ids=["doc_apple"],
        preferred_document_id="doc_apple",
        answer_intent={"mode": "evidence", "confidence": 0.78},
    )
    assert decision.path == "rag"
    assert decision.budget.max_steps == 0


def test_cross_company_comparison_uses_agent_path():
    decision = decide_hybrid_path(
        question="Compare Apple and Microsoft climate transition risks across the uploaded reports and judge which is better supported by evidence.",
        reasoning_mode="deep",
        document_ids=["doc_apple", "doc_msft"],
        preferred_document_id=None,
        answer_intent={"mode": "hybrid", "confidence": 0.86},
    )
    assert decision.path == "agent"
    assert decision.budget.max_steps == 8
    assert decision.budget.deadline_seconds == 90
    assert decision.confidence >= 0.65


def test_unrestricted_all_reports_comparison_uses_agent_path():
    decision = decide_hybrid_path(
        question="Compare the climate transition risks across all reports and explain uncertainty with evidence.",
        reasoning_mode="deep",
        document_ids=[],
        preferred_document_id=None,
        answer_intent={"mode": "hybrid", "confidence": 0.8},
    )
    assert decision.path == "agent"
    assert decision.reason == "complex_multi_document_evidence_task"


def test_explicit_all_reports_comparison_with_one_accessible_doc_uses_agent_path():
    decision = decide_hybrid_path(
        question="Compare the climate transition risks across all reports and explain uncertainty with evidence.",
        reasoning_mode="deep",
        document_ids=["doc_costco"],
        preferred_document_id=None,
        answer_intent={"mode": "hybrid", "confidence": 0.8},
    )
    assert decision.path == "agent"


def test_current_report_comparison_stays_rag_path():
    decision = decide_hybrid_path(
        question="Compare the climate risks and governance evidence in this report.",
        reasoning_mode="deep",
        document_ids=["doc_costco"],
        preferred_document_id="doc_costco",
        answer_intent={"mode": "evidence", "confidence": 0.8},
    )
    assert decision.path == "rag"


def test_fast_complex_question_gets_smaller_agent_budget():
    decision = decide_hybrid_path(
        question="Compare these three ESG reports and identify governance risks with supporting evidence.",
        reasoning_mode="flash",
        document_ids=["a", "b", "c"],
        preferred_document_id=None,
        answer_intent={"mode": "hybrid", "confidence": 0.8},
    )
    assert decision.path == "agent"
    assert decision.budget.max_steps == 3
    assert 15 <= decision.budget.deadline_seconds <= 25
