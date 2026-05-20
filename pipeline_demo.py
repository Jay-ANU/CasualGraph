"""Minimal demo pipeline: parse text, chunk, extract ESG JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.chunk_service import chunk_service  # type: ignore  # noqa: E402
from services.parser_service import parser_service  # type: ignore  # noqa: E402

from ai_service.extractor import extract_esg  # noqa: E402


def run_demo(input_path: Path, output_path: Path) -> None:
    parsed = parser_service.parse_bytes(input_path.name, input_path.read_bytes())
    chunks = chunk_service.create_chunks(
        parsed_document=parsed,
        document_id=input_path.stem,
        source=str(input_path),
        category="esg-report",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            extraction = extract_esg(chunk["content"])
            row = {
                "id": chunk["id"],
                "document_id": chunk["document_id"],
                "chunk_metadata": chunk["metadata"],
                **extraction,
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Processed {len(chunks)} chunks -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo ESG extraction pipeline")
    parser.add_argument("--input", required=True, help="Input TXT/MD/PDF file")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    args = parser.parse_args()
    run_demo(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
