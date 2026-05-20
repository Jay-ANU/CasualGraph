"""Batch ESG extraction from JSONL using the local QLoRA model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_service.extractor import extract_esg


def process_file(input_path: Path, output_path: Path, progress_every: int = 10) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed = 0

    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as dst:
        for index, line in enumerate(src, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                row = {"id": f"row_{index}", "text": "", "error": "invalid_jsonl"}

            record_id = row.get("id") or f"row_{index}"
            text = row.get("text")

            if not text:
                result = {
                    "id": record_id,
                    "entities": [],
                    "relations": [],
                    "error": "missing_text",
                }
            else:
                extracted = extract_esg(text)
                result = {"id": record_id, **extracted}

            dst.write(json.dumps(result, ensure_ascii=False) + "\n")
            processed += 1
            if processed % progress_every == 0:
                print(f"Processed {processed} rows...")

    print(f"Done. Wrote {processed} rows to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ESG extraction with local QLoRA model")
    parser.add_argument("--input", required=True, help="Input JSONL file with text rows")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--progress-every", type=int, default=10, help="Progress log interval")
    args = parser.parse_args()

    process_file(Path(args.input), Path(args.output), progress_every=args.progress_every)


if __name__ == "__main__":
    main()
