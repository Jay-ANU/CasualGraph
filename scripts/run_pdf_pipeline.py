"""Run the end-to-end ESG report processing pipeline from PDF to graph JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_service.extractor import extract_esg
from configs.settings import CHUNK_DIR, EXTRACTION_DIR, GRAPH_DIR, PROCESSED_DIR, VECTOR_DIR, ensure_directories
from document_processing.chunker import chunk_text
from document_processing.pdf_parser import parse_pdf
from document_processing.text_cleaner import clean_text
from graph.graph_builder import build_graph_from_extractions
from graph.neo4j_store import maybe_sync_to_neo4j
from graph.graph_store import save_graph
from rag.vector_store import build_vector_store


def run_pdf_pipeline(pdf_path: str, name: str) -> Dict[str, str]:
    """Execute the full ESG PDF pipeline and return output paths."""
    ensure_directories()

    processed_text_path = PROCESSED_DIR / f"{name}.txt"
    chunks_path = CHUNK_DIR / f"{name}_chunks.jsonl"
    extractions_path = EXTRACTION_DIR / f"{name}_extractions.jsonl"
    graph_path = GRAPH_DIR / f"{name}_graph.json"
    vector_store_path = VECTOR_DIR / name

    print(f"[1/7] Parsing PDF: {pdf_path}")
    text = parse_pdf(pdf_path)

    print("[2/7] Cleaning text")
    cleaned = clean_text(text)
    processed_text_path.write_text(cleaned, encoding="utf-8")

    print("[3/7] Chunking text")
    chunks = chunk_text(cleaned)
    chunks = [
        {
            **chunk,
            "document_id": name,
            "document_title": name,
            "document_group": "base_corpus",
            "source_type": "pdf_corpus",
            "domain": "general",
            "source": pdf_path,
        }
        for chunk in chunks
    ]
    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"Saved {len(chunks)} chunks -> {chunks_path}")

    print("[4/7] Building vector index")
    build_vector_store(chunks, str(vector_store_path))

    print("[5/7] Running ESG extraction on chunks")
    extractions: List[Dict] = []
    with extractions_path.open("w", encoding="utf-8") as handle:
        for index, chunk in enumerate(chunks, start=1):
            try:
                extraction = extract_esg(chunk["text"])
                row = {"chunk_id": chunk["chunk_id"], **extraction}
            except Exception as exc:
                row = {"chunk_id": chunk["chunk_id"], "entities": [], "relations": [], "error": str(exc)}
            extractions.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if index % 10 == 0 or index == len(chunks):
                print(f"  Extracted {index}/{len(chunks)} chunks")

    print("[6/7] Building graph")
    graph = build_graph_from_extractions(extractions)
    save_graph(graph, str(graph_path))
    neo4j_sync = maybe_sync_to_neo4j(
        document={
            "id": name,
            "title": name,
            "domain": "general",
            "source": pdf_path,
            "document_group": "base_corpus",
            "source_type": "pdf_corpus",
            "processed_text_path": str(processed_text_path),
            "chunks_path": str(chunks_path),
            "extractions_path": str(extractions_path),
            "graph_path": str(graph_path),
            "vector_store_path": str(vector_store_path),
        },
        chunks=chunks,
        extractions=extractions,
        graph=graph,
    )
    if neo4j_sync.get("synced"):
        print(
            "[6.5/7] Neo4j sync complete "
            f"(chunks={neo4j_sync.get('chunks_synced', 0)}, "
            f"entities={neo4j_sync.get('entities_synced', 0)}, "
            f"relations={neo4j_sync.get('relations_synced', 0)})"
        )
    else:
        print(f"[6.5/7] Neo4j sync skipped: {neo4j_sync.get('reason', 'unknown')}")

    print("[7/7] Pipeline finished")
    return {
        "status": "finished",
        "processed_text": str(processed_text_path),
        "chunks": str(chunks_path),
        "extractions": str(extractions_path),
        "graph": str(graph_path),
        "vector_store": str(vector_store_path),
        "neo4j": neo4j_sync,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full ESG PDF pipeline")
    parser.add_argument("--pdf", required=True, help="Input PDF path")
    parser.add_argument("--name", required=True, help="Output name prefix")
    args = parser.parse_args()
    result = run_pdf_pipeline(args.pdf, args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
