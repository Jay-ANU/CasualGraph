from unittest.mock import patch

from rag.router import route_query


def test_router_disabled_preserves_ask_vector_path():
    with patch("rag.router.RAG_ROUTER_ENABLED", False):
        route = route_query("What did NVIDIA report?", "", "ask", None)

    assert route["strategy"] == "vector_only"
    assert route["backend"] == "disabled"


def test_router_routes_identifier_to_hybrid():
    route = route_query("GHG Protocol Scope 3 2023", "", "ask", None)

    assert route["strategy"] == "hybrid"


def test_router_routes_short_followup_to_multi_query():
    route = route_query("what about Apple?", "", "ask", None)

    assert route["strategy"] == "multi_query"


def test_router_routes_compound_to_decomposition():
    route = route_query("Compare 2022 and 2023 Scope 1, 2, 3 and explain the trend", "", "ask", None)

    assert route["strategy"] == "decomposition"


def test_router_routes_predict_to_layered():
    route = route_query("How might renewable electricity affect stock price?", "", "predict", None)

    assert route["strategy"] == "layered"


def test_router_routes_greeting_to_no_retrieval():
    route = route_query("hi", "", "ask", None)

    assert route["strategy"] == "no_retrieval"


def test_router_routes_meta_to_no_retrieval():
    route = route_query("你能做什么", "", "ask", None)

    assert route["strategy"] == "no_retrieval"


def test_router_keeps_esg_question_retrieval():
    route = route_query("我们公司去年减了多少碳", "", "ask", None)

    assert route["strategy"] != "no_retrieval"


def test_router_does_not_chitchat_after_evidence_followup():
    history = "assistant: NVIDIA reduced Scope 2 emissions by 14% [chunk_0]"
    route = route_query("really? why?", history, "ask", None)

    assert route["strategy"] != "no_retrieval"
