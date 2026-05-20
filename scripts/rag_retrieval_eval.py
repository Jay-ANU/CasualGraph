"""Smoke runner for comparing RAG retrieval modes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time


QUESTIONS = [
    "hi",
    "thanks",
    "你能做什么",
    "really? why?",
    "What renewable electricity target did NVIDIA report?",
    "What about Apple?",
    "GHG Protocol Scope 3 2023",
    "Compare 2022 and 2023 Scope 1, 2, 3 and explain the trend",
    "How might renewable electricity affect cost of capital?",
]

CONFIGS = {
    "vanilla": {
        "RAG_MULTI_QUERY_ENABLED": "false",
        "RAG_HYBRID_ENABLED": "false",
        "RAG_DECOMPOSE_ENABLED": "false",
    },
    "multi-query": {
        "RAG_MULTI_QUERY_ENABLED": "true",
        "RAG_HYBRID_ENABLED": "false",
        "RAG_DECOMPOSE_ENABLED": "false",
    },
    "hybrid": {
        "RAG_MULTI_QUERY_ENABLED": "false",
        "RAG_HYBRID_ENABLED": "true",
        "RAG_DECOMPOSE_ENABLED": "false",
    },
    "full": {
        "RAG_MULTI_QUERY_ENABLED": "true",
        "RAG_HYBRID_ENABLED": "true",
        "RAG_DECOMPOSE_ENABLED": "true",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--question", default="")
    parser.add_argument("--mode", default="ask")
    args = parser.parse_args()

    if args.run_once:
        _run_once(args.question, args.mode)
        return

    for config_name, env_overrides in CONFIGS.items():
        print(f"\n== {config_name} ==")
        for question in QUESTIONS:
            env = {**os.environ, **env_overrides}
            mode = "predict" if "might" in question.lower() or "compare" in question.lower() else "ask"
            started = time.time()
            proc = subprocess.run(
                [sys.executable, __file__, "--run-once", "--question", question, "--mode", mode],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            latency = time.time() - started
            print(f"{question} [{mode}] {latency:.2f}s")
            print(proc.stdout.strip() or proc.stderr.strip())


def _run_once(question: str, mode: str) -> None:
    from rag.rag_pipeline import answer_question

    result = answer_question(question, top_k=5, mode=mode)
    sources = result.get("sources") or []
    payload = {
        "backend": result.get("backend"),
        "routing": result.get("routing"),
        "retrieval_strategy": result.get("retrieval_strategy"),
        "fusion_method": result.get("fusion_method"),
        "sub_queries": result.get("sub_queries"),
        "chunk_ids": [item.get("chunk_id") for item in sources],
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
