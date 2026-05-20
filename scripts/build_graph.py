"""Build graph JSON from extraction JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.graph_builder import build_graph_from_extractions
from graph.graph_store import save_graph


def build_graph_file(input_path: str, output_path: str) -> str:
    src = Path(input_path)
    with src.open("r", encoding="utf-8") as handle:
        extractions = [json.loads(line) for line in handle if line.strip()]

    graph = build_graph_from_extractions(extractions)
    save_graph(graph, output_path)
    print(f"Graph saved to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build knowledge graph JSON from extractions")
    parser.add_argument("--input", required=True, help="Input extraction JSONL path")
    parser.add_argument("--output", required=True, help="Output graph JSON path")
    args = parser.parse_args()
    build_graph_file(args.input, args.output)


if __name__ == "__main__":
    main()
