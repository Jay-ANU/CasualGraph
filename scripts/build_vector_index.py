"""Build a local vector index from chunk JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.vector_store import build_vector_store


def build_index(chunks_path: str, output_path: str) -> str:
    src = Path(chunks_path)
    with src.open("r", encoding="utf-8") as handle:
        chunks = [json.loads(line) for line in handle if line.strip()]

    build_vector_store(chunks, output_path)
    print(f"Vector store saved to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FAISS vector index from chunk JSONL")
    parser.add_argument("--chunks", required=True, help="Chunk JSONL path")
    parser.add_argument("--output", required=True, help="Vector store output directory")
    args = parser.parse_args()
    build_index(args.chunks, args.output)


if __name__ == "__main__":
    main()
