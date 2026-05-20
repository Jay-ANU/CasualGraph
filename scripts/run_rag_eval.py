"""Run a small RAG smoke-eval set and emit JSONL results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.rag_pipeline import answer_question


DEFAULT_CASES = Path("evals/cases/rag_baseline.yaml")


def load_cases(path: Path) -> List[Dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"Invalid eval file: {path}")
    return [case for case in payload["cases"] if isinstance(case, dict)]


def evaluate_response(case: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
    answer = str(response.get("answer") or "")
    answer_lower = answer.lower()
    sources = response.get("sources") or []
    failures: List[str] = []

    for term in _terms(case.get("required_answer_terms")):
        if term.lower() not in answer_lower:
            failures.append(f"missing_required_term:{term}")

    for term in _terms(case.get("forbidden_answer_terms")):
        if term.lower() in answer_lower:
            failures.append(f"contains_forbidden_term:{term}")

    min_sources = int(case.get("min_sources") or 0)
    if len(sources) < min_sources:
        failures.append(f"source_count:{len(sources)}<{min_sources}")

    return {
        "id": case.get("id"),
        "passed": not failures,
        "failures": failures,
        "answer_chars": len(answer),
        "source_count": len(sources),
        "reasoning_mode": response.get("reasoning_mode"),
        "retrieval_strategy": response.get("retrieval_strategy"),
        "timings_ms": response.get("timings_ms") or {},
    }


def run_cases(cases: Iterable[Dict[str, Any]], *, top_k: int) -> List[Dict[str, Any]]:
    results = []
    for case in cases:
        response = answer_question(
            str(case["question"]),
            top_k=top_k,
            history=[],
            reasoning_mode=str(case.get("reasoning_mode") or "flash"),
        )
        results.append(evaluate_response(case, response))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG smoke eval cases.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="YAML file containing eval cases.")
    parser.add_argument("--output", default="", help="Optional JSONL output path.")
    parser.add_argument("--top-k", type=int, default=5, help="RAG top_k for each case.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and list cases without calling the RAG pipeline.")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    cases = load_cases(cases_path)
    if args.dry_run:
        print(f"Loaded {len(cases)} cases from {cases_path}")
        for case in cases:
            print(f"- {case.get('id')}: {case.get('question')}")
        return 0

    results = run_cases(cases, top_k=max(1, int(args.top_k)))
    for result in results:
        print(json.dumps(result, ensure_ascii=False))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "\n".join(json.dumps(result, ensure_ascii=False) for result in results) + "\n",
            encoding="utf-8",
        )

    failures = [item for item in results if not item["passed"]]
    print(f"RAG eval summary: passed={len(results) - len(failures)} failed={len(failures)} total={len(results)}")
    return 1 if failures else 0


def _terms(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


if __name__ == "__main__":
    raise SystemExit(main())
