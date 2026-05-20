"""Batch ESG extraction over chunk JSONL files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_service.extractor import extract_esg


def run_batch_extract(input_path: str, output_path: str, progress_every: int = 10) -> str:
    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    with src.open("r", encoding="utf-8") as input_file, dst.open("w", encoding="utf-8") as output_file:
        for index, line in enumerate(input_file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                row = {"chunk_id": f"chunk_{index}", "text": "", "error": "invalid_json"}

            chunk_id = row.get("chunk_id") or row.get("id") or f"chunk_{index}"
            text = row.get("text")

            if not text:
                result = {"chunk_id": chunk_id, "entities": [], "relations": [], "error": "missing_text"}
            else:
                extracted = extract_esg(text)
                result = {"chunk_id": chunk_id, **extracted}

            output_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            processed += 1
            if processed % progress_every == 0:
                print(f"Processed {processed} chunks...")

    print(f"Batch extraction finished: {dst}")
    return str(dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ESG extraction")
    parser.add_argument("--input", required=True, help="Input chunk JSONL path")
    parser.add_argument("--output", required=True, help="Output extraction JSONL path")
    args = parser.parse_args()
    run_batch_extract(args.input, args.output)


if __name__ == "__main__":
    main()
