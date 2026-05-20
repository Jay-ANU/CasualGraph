"""Runtime helpers for ingesting documents into the root ESG pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import io
import json
import re
import shutil

try:
    import networkx as nx
except Exception:
    nx = None

from docx import Document as DocxDocument
from pypdf import PdfReader

from ai_service.extraction_cache import cached_extract_esg, init_extraction_cache
import document_registry
from configs.settings import (
    ACTIVE_VECTOR_STORE_FILE,
    CHUNK_DIR,
    ESG_METRICS_DB_PATH,
    ESG_METRICS_EXTRACTION_ENABLED,
    ESG_METRICS_MIN_CONFIDENCE,
    ESG_METRICS_TAXONOMY_PATH,
    EXTRACTION_DIR,
    EXTRACTION_MAX_WORKERS,
    GRAPH_DIR,
    PINECONE_NAMESPACE,
    PROCESSED_DIR,
    VECTOR_DIR,
    VECTOR_STORE_PROVIDER,
    ensure_directories,
)
from document_processing.chunker import chunk_text
from document_processing.text_cleaner import clean_text
from graph.graph_builder import build_graph_from_extractions
from graph.graph_utils import normalize_entity_name
from graph.neo4j_store import assert_neo4j_ready, get_neo4j_store, maybe_sync_to_neo4j
from graph.graph_store import load_graph, save_graph
from rag.bm25_index import build_bm25_index
from rag.pinecone_store import delete_vectors_by_document_id, pinecone_available
import rag.vector_store as vector_store_module
from rag.vector_store import build_vector_store


def ingest_uploaded_document(
    title: str,
    domain: str = "general",
    source: str = "",
    content: str = "",
    document_group: str = "user_upload",
    source_type: str = "",
    owner_user_id: str = "",
    visibility_scope: str = "global",
    filename: str | None = None,
    file_bytes: bytes | None = None,
    progress_callback: Optional[Callable[[str, str, int], None]] = None,
) -> Dict:
    """Parse uploaded content, append it to the corpus, and return frontend-friendly data."""
    ensure_directories()
    _report_progress(progress_callback, "neo4j", "Checking Neo4j connection", 2)
    assert_neo4j_ready()
    _report_progress(progress_callback, "reading", "Reading uploaded content", 5)
    owner_value = str(owner_user_id or "").strip()
    scope_value = str(visibility_scope or "global").strip().lower()
    if scope_value not in {"global", "private"}:
        scope_value = "global"

    raw_hash = document_registry.compute_raw_hash(file_bytes, content)
    if raw_hash:
        existing = document_registry.lookup(
            raw_hash=raw_hash,
            text_hash=None,
            document_group=document_group,
            owner_user_id=owner_value,
        )
        if existing:
            return _build_duplicate_response(existing, progress_callback=progress_callback)

    text, detected_source = _resolve_text_input(content=content, filename=filename, file_bytes=file_bytes)
    _report_progress(progress_callback, "cleaning", "Cleaning extracted text", 15)
    cleaned = clean_text(text)
    text_hash = document_registry.compute_text_hash(cleaned)
    existing = document_registry.lookup(
        raw_hash=None,
        text_hash=text_hash,
        document_group=document_group,
        owner_user_id=owner_value,
    )
    if existing:
        return _build_duplicate_response(existing, progress_callback=progress_callback)

    slug = _slugify(title or filename or "document")
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    name = f"{slug}_{timestamp}"
    source_value = source or detected_source
    source_type_value = source_type or ("uploaded_file" if filename else "manual_input")

    _report_progress(progress_callback, "chunking", "Splitting document into chunks", 25)
    chunks = chunk_text(cleaned)
    if not chunks:
        raise ValueError("No usable text chunks were created from the uploaded content.")
    chunks = [
        {
            **chunk,
            "document_id": name,
            "document_title": title or filename or "Untitled document",
            "document_group": document_group,
            "owner_user_id": owner_value,
            "visibility_scope": scope_value,
            "source_type": source_type_value,
            "domain": domain,
            "source": source_value,
        }
        for chunk in chunks
    ]

    processed_text_path = PROCESSED_DIR / f"{name}.txt"
    chunks_path = CHUNK_DIR / f"{name}_chunks.jsonl"
    extractions_path = EXTRACTION_DIR / f"{name}_extractions.jsonl"
    graph_path = GRAPH_DIR / f"{name}_graph.json"
    vector_store_path = VECTOR_DIR / name

    processed_text_path.write_text(cleaned, encoding="utf-8")
    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    _report_progress(progress_callback, "embedding", "Building vector index", 40)
    build_vector_store(chunks, str(vector_store_path))
    build_bm25_index(chunks, str(vector_store_path))

    init_extraction_cache()
    with extractions_path.open("w", encoding="utf-8") as handle:
        extractions = _extract_chunks(chunks, progress_callback)
        for row in extractions:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    if ESG_METRICS_EXTRACTION_ENABLED:
        _report_progress(progress_callback, "metrics", "Extracting structured ESG metrics", 86)
        try:
            _extract_structured_metrics(chunks, document_id=name)
        except Exception as exc:
            print(f"[pipeline] Metric extraction failed for {name}: {type(exc).__name__}: {exc}")

    _report_progress(progress_callback, "graph", "Building knowledge graph structures", 88)
    graph = build_graph_from_extractions(extractions)
    save_graph(graph, str(graph_path))
    _report_progress(progress_callback, "neo4j", "Syncing graph to Neo4j", 94)
    neo4j_sync = maybe_sync_to_neo4j(
        document={
            "id": name,
            "title": title or filename or "Untitled document",
            "domain": domain,
            "source": source_value,
            "document_group": document_group,
            "owner_user_id": owner_value,
            "visibility_scope": scope_value,
            "source_type": source_type_value,
            "processed_text_path": str(processed_text_path),
            "chunks_path": str(chunks_path),
            "extractions_path": str(extractions_path),
            "graph_path": str(graph_path),
            "vector_store_path": str(vector_store_path),
            "content_hash": text_hash,
        },
        chunks=chunks,
        extractions=extractions,
        graph=graph,
    )

    relationships = _to_relationship_rows(extractions, domain=domain)
    graph_display = _to_display_graph(graph)
    _report_progress(progress_callback, "completed", "Document processing complete", 100)

    document_registry.register({
        "document_id": name,
        "title": title or filename or "Untitled document",
        "domain": domain,
        "source": source_value,
        "source_type": source_type_value,
        "document_group": document_group,
        "owner_user_id": owner_value,
        "visibility_scope": scope_value,
        "raw_hash": raw_hash,
        "text_hash": text_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "paths": {
            "processed_text": str(processed_text_path),
            "chunks": str(chunks_path),
            "extractions": str(extractions_path),
            "graph": str(graph_path),
            "vector_store": str(vector_store_path),
        },
    })

    return {
        "document": {
            "id": name,
            "title": title or filename or "Untitled document",
            "domain": domain,
            "source": source_value,
            "document_group": document_group,
            "owner_user_id": owner_value,
            "visibility_scope": scope_value,
            "source_type": source_type_value,
            "graph": graph_display,
            "relationships": relationships,
            "processed_text_path": str(processed_text_path),
            "chunks_path": str(chunks_path),
            "extractions_path": str(extractions_path),
            "graph_path": str(graph_path),
            "vector_store_path": str(vector_store_path),
            "content_hash": text_hash,
            "neo4j_sync": neo4j_sync,
        },
        "stats": {
            "chunk_count": len(chunks),
            "entity_count": len(graph_display["nodes"]),
            "relation_count": len(relationships),
        },
        "neo4j": neo4j_sync,
    }


def delete_uploaded_document(upload: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort cleanup for a locally uploaded document."""
    if str(upload.get("status") or "") == "rejected":
        return {
            "deleted_paths": [],
            "warnings": [],
            "neo4j": {"enabled": False, "deleted": False, "reason": "rejected_upload_has_no_resources"},
        }

    deleted_paths: List[str] = []
    warnings: List[str] = []
    paths = upload.get("paths") or {}
    document_id = str(upload.get("document_id") or "").strip()

    for key in ("processed_text_path", "chunks_path", "extractions_path", "graph_path"):
        value = str(paths.get(key) or "").strip()
        if not value:
            continue
        path = Path(value)
        try:
            if path.exists() and path.is_file():
                path.unlink()
                deleted_paths.append(str(path))
        except Exception as exc:
            warnings.append(f"{key}: {type(exc).__name__}: {exc}")

    vector_path = str(paths.get("vector_store_path") or "").strip()
    if vector_path:
        path = Path(vector_path)
        if VECTOR_STORE_PROVIDER.strip().lower() == "pinecone" and document_id:
            try:
                if pinecone_available():
                    delete_vectors_by_document_id(document_id, namespace=PINECONE_NAMESPACE)
                else:
                    warnings.append("pinecone: SDK unavailable; remote vectors were not deleted")
            except Exception as exc:
                warnings.append(f"pinecone: {type(exc).__name__}: {exc}")
        try:
            if path.exists() and path.is_dir():
                shutil.rmtree(path)
                deleted_paths.append(str(path))
                _repair_active_vector_store_after_delete(path)
        except Exception as exc:
            warnings.append(f"vector_store_path: {type(exc).__name__}: {exc}")

    neo4j_result: Dict[str, Any] = {"enabled": False, "deleted": False, "reason": "not_attempted"}
    if document_id:
        try:
            store = get_neo4j_store()
            if store is None:
                neo4j_result = {"enabled": False, "deleted": False, "reason": "neo4j_unavailable"}
            else:
                neo4j_result = store.delete_document(document_id)
        except Exception as exc:
            neo4j_result = {"enabled": True, "deleted": False, "reason": f"{type(exc).__name__}: {exc}"}

    return {"deleted_paths": deleted_paths, "warnings": warnings, "neo4j": neo4j_result}


def summarize_registered_document(entry: Dict[str, Any], audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    document_id = str(entry.get("document_id") or "").strip()
    domain = str(entry.get("domain") or "general")
    paths = entry.get("paths") or {}
    graph_path = Path(str(paths.get("graph") or ""))

    graph_display = _load_graph_display(graph_path)
    metadata = dict(graph_display.get("metadata") or {})
    stats = (audit or {}).get("stats") or {}

    if not metadata.get("node_count"):
        metadata["node_count"] = int(stats.get("entities") or 0)
    if not metadata.get("edge_count"):
        metadata["edge_count"] = int(stats.get("relations") or 0)
    metadata.setdefault("is_directed", True)
    metadata.setdefault("is_acyclic", False)

    return {
        "id": document_id,
        "title": entry.get("title", ""),
        "domain": domain,
        "source": entry.get("source", ""),
        "document_group": entry.get("document_group", ""),
        "owner_user_id": entry.get("owner_user_id", ""),
        "visibility_scope": entry.get("visibility_scope", "global"),
        "source_type": entry.get("source_type", ""),
        "graph": {"nodes": [], "edges": [], "metadata": metadata},
        "relationship_count": int(stats.get("relations") or metadata.get("edge_count") or 0),
        "chunk_count": int(stats.get("chunks") or 0),
        "processed_text_path": str(paths.get("processed_text") or ""),
        "chunks_path": str(paths.get("chunks") or ""),
        "extractions_path": str(paths.get("extractions") or ""),
        "graph_path": str(paths.get("graph") or ""),
        "vector_store_path": str(paths.get("vector_store") or ""),
        "neo4j_sync": dict(entry.get("neo4j_sync") or {}),
        "ingested_at": entry.get("ingested_at") or "",
    }


def load_registered_document(entry: Dict[str, Any], audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    document_id = str(entry.get("document_id") or "").strip()
    domain = str(entry.get("domain") or "general")
    paths = entry.get("paths") or {}
    chunks_path = Path(str(paths.get("chunks") or ""))
    extractions_path = Path(str(paths.get("extractions") or ""))
    graph_path = Path(str(paths.get("graph") or ""))

    chunks = _load_jsonl_rows(chunks_path) if chunks_path.is_file() else []
    extractions = _load_jsonl_rows(extractions_path) if extractions_path.is_file() else []
    graph = load_graph(str(graph_path)) if graph_path.is_file() else {"nodes": [], "edges": []}
    graph_display = _to_display_graph(graph)
    relationships = _to_relationship_rows(extractions, domain=domain)

    return {
        "id": document_id,
        "title": entry.get("title", ""),
        "domain": domain,
        "source": entry.get("source", ""),
        "document_group": entry.get("document_group", ""),
        "owner_user_id": entry.get("owner_user_id", ""),
        "visibility_scope": entry.get("visibility_scope", "global"),
        "source_type": entry.get("source_type", ""),
        "graph": graph_display,
        "relationships": relationships,
        "relationship_count": len(relationships),
        "chunk_count": len(chunks),
        "processed_text_path": str(paths.get("processed_text") or ""),
        "chunks_path": str(paths.get("chunks") or ""),
        "extractions_path": str(paths.get("extractions") or ""),
        "graph_path": str(paths.get("graph") or ""),
        "vector_store_path": str(paths.get("vector_store") or ""),
        "neo4j_sync": dict(entry.get("neo4j_sync") or {}),
        "ingested_at": entry.get("ingested_at") or "",
    }


def _repair_active_vector_store_after_delete(deleted_path: Path) -> None:
    try:
        if not ACTIVE_VECTOR_STORE_FILE.exists():
            return
        raw = ACTIVE_VECTOR_STORE_FILE.read_text(encoding="utf-8").strip()
        manifest = json.loads(raw) if raw.startswith("{") else {"location": raw}
        active_location = Path(str(manifest.get("location") or "")).resolve()
        if active_location != deleted_path.resolve():
            return

        candidates = [
            path
            for path in VECTOR_DIR.iterdir()
            if path.is_dir() and path.resolve() != deleted_path.resolve() and (path / "metadata.json").exists()
        ]
        candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        if candidates:
            replacement = candidates[0].resolve()
            ACTIVE_VECTOR_STORE_FILE.write_text(
                json.dumps(
                    {
                        "provider": VECTOR_STORE_PROVIDER.strip().lower() or "local",
                        "location": str(replacement),
                        "namespace": PINECONE_NAMESPACE,
                        "document_id": replacement.name,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        else:
            ACTIVE_VECTOR_STORE_FILE.unlink(missing_ok=True)
        vector_store_module._LOADED_STORE = None
        vector_store_module._LOADED_STORE_KEY = None
    except Exception as exc:
        print(f"[ingestion] Active vector store repair failed: {type(exc).__name__}: {exc}")


def _extract_chunks(
    chunks: List[Dict[str, Any]],
    progress_callback: Optional[Callable[[str, str, int], None]],
) -> List[Dict[str, Any]]:
    total_chunks = max(len(chunks), 1)
    workers = min(max(1, EXTRACTION_MAX_WORKERS), total_chunks)

    if workers == 1:
        rows: List[Dict[str, Any]] = []
        for index, chunk in enumerate(chunks, start=1):
            progress = 45 + int((index - 1) / total_chunks * 40)
            _report_progress(
                progress_callback,
                "extracting",
                f"Extracting ESG entities and relations from chunk {index}/{total_chunks}",
                progress,
            )
            rows.append(_extract_one_chunk(chunk))
        return rows

    rows_by_index: Dict[int, Dict[str, Any]] = {}
    completed = 0
    _report_progress(
        progress_callback,
        "extracting",
        f"Extracting ESG entities and relations with {workers} workers",
        45,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_extract_one_chunk, chunk): index
            for index, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            index = futures[future]
            rows_by_index[index] = future.result()
            completed += 1
            progress = 45 + int(completed / total_chunks * 40)
            _report_progress(
                progress_callback,
                "extracting",
                f"Extracted {completed}/{total_chunks} chunks",
                progress,
            )
    return [rows_by_index[index] for index in range(len(chunks))]


def _extract_one_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    extraction = cached_extract_esg(chunk["text"])
    return {"chunk_id": chunk["chunk_id"], **extraction}


def _extract_structured_metrics(chunks: List[Dict[str, Any]], *, document_id: str) -> int:
    """Per-chunk numeric metric extraction.

    Runs in parallel using EXTRACTION_MAX_WORKERS, filters by
    ESG_METRICS_MIN_CONFIDENCE, and writes survivors to the metric store.
    Returns the number of rows persisted. Failures on individual chunks are
    logged and skipped — they do not abort ingestion.
    """
    from metric_extraction import extract_metrics_for_chunk, init_metric_store, load_taxonomy
    from metric_extraction.extractor import default_llm_client

    if not chunks:
        return 0

    taxonomy = load_taxonomy(ESG_METRICS_TAXONOMY_PATH)
    store = init_metric_store(ESG_METRICS_DB_PATH)
    llm = default_llm_client()
    workers = min(max(1, EXTRACTION_MAX_WORKERS), len(chunks))

    def _run(chunk: Dict[str, Any]) -> List[Any]:
        try:
            return extract_metrics_for_chunk(
                chunk_text=str(chunk.get("text") or ""),
                taxonomy=taxonomy,
                llm=llm,
                document_id=document_id,
                chunk_id=str(chunk.get("chunk_id") or ""),
            )
        except Exception as exc:
            print(f"[metrics] chunk {chunk.get('chunk_id')} failed: {type(exc).__name__}: {exc}")
            return []

    all_rows: List[Any] = []
    if workers == 1:
        for chunk in chunks:
            all_rows.extend(_run(chunk))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for rows in executor.map(_run, chunks):
                all_rows.extend(rows)

    survivors = [row for row in all_rows if row.confidence >= ESG_METRICS_MIN_CONFIDENCE]
    return store.insert_many(survivors)


def _build_duplicate_response(
    entry: Dict[str, Any],
    progress_callback: Optional[Callable[[str, str, int], None]] = None,
) -> Dict[str, Any]:
    matched_by = str(entry.get("matched_by") or "text_hash")
    paths = entry.get("paths") or {}
    document_id = str(entry.get("document_id") or "")
    domain = str(entry.get("domain") or "general")

    chunks_path = Path(str(paths.get("chunks") or ""))
    extractions_path = Path(str(paths.get("extractions") or ""))
    graph_path = Path(str(paths.get("graph") or ""))

    chunks = _load_jsonl_rows(chunks_path) if chunks_path.is_file() else []
    extractions = _load_jsonl_rows(extractions_path) if extractions_path.is_file() else []
    graph = load_graph(str(graph_path)) if graph_path.is_file() else {"nodes": [], "edges": []}

    relationships = _to_relationship_rows(extractions, domain=domain)
    graph_display = _to_display_graph(graph)

    print(f"[ingestion] Duplicate detected (matched_by={matched_by}) document_id={document_id}")
    _report_progress(
        progress_callback,
        "completed",
        "Duplicate detected; reusing existing document",
        100,
    )

    return {
        "duplicate": True,
        "matched_by": matched_by,
        "document": {
            "id": document_id,
            "title": entry.get("title", ""),
            "domain": domain,
            "source": entry.get("source", ""),
            "document_group": entry.get("document_group", ""),
            "owner_user_id": entry.get("owner_user_id", ""),
            "visibility_scope": entry.get("visibility_scope", "global"),
            "source_type": entry.get("source_type", ""),
            "graph": graph_display,
            "relationships": relationships,
            "processed_text_path": str(paths.get("processed_text") or ""),
            "chunks_path": str(paths.get("chunks") or ""),
            "extractions_path": str(paths.get("extractions") or ""),
            "graph_path": str(paths.get("graph") or ""),
            "vector_store_path": str(paths.get("vector_store") or ""),
            "content_hash": entry.get("text_hash") or "",
            "neo4j_sync": {"enabled": False, "synced": False, "reason": "duplicate_skipped"},
        },
        "stats": {
            "chunk_count": len(chunks),
            "entity_count": len(graph_display["nodes"]),
            "relation_count": len(relationships),
        },
        "neo4j": {"enabled": False, "synced": False, "reason": "duplicate_skipped"},
    }


def rebuild_document_graph(document: Dict[str, Any]) -> Dict:
    """Rebuild graph and relationship payloads for an existing document artifact set."""
    ensure_directories()

    document_id = str(document.get("id") or "").strip()
    if not document_id:
        raise ValueError("Document id is required to rebuild the graph.")

    chunks_path = Path(str(document.get("chunks_path") or (CHUNK_DIR / f"{document_id}_chunks.jsonl")))
    extractions_path = Path(str(document.get("extractions_path") or (EXTRACTION_DIR / f"{document_id}_extractions.jsonl")))
    graph_path = Path(str(document.get("graph_path") or (GRAPH_DIR / f"{document_id}_graph.json")))

    if not chunks_path.exists():
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")
    if not extractions_path.exists():
        raise FileNotFoundError(f"Extraction file not found: {extractions_path}")

    chunks = _load_jsonl_rows(chunks_path)
    extractions = _load_jsonl_rows(extractions_path)
    if not chunks:
        raise ValueError(f"No chunks found in {chunks_path}")
    if not extractions:
        raise ValueError(f"No extraction rows found in {extractions_path}")

    graph = build_graph_from_extractions(extractions)
    if graph_path:
        save_graph(graph, str(graph_path))

    neo4j_sync = maybe_sync_to_neo4j(document=document, chunks=chunks, extractions=extractions, graph=graph)
    relationships = _to_relationship_rows(extractions, domain=str(document.get("domain") or "general"))
    graph_display = _to_display_graph(graph)

    updated_document = {
        **document,
        "graph": graph_display,
        "relationships": relationships,
        "neo4j_sync": neo4j_sync,
    }
    return {
        "document": updated_document,
        "stats": {
            "chunk_count": len(chunks),
            "entity_count": len(graph_display["nodes"]),
            "relation_count": len(relationships),
        },
        "neo4j": neo4j_sync,
    }


def _resolve_text_input(content: str = "", filename: str | None = None, file_bytes: bytes | None = None) -> tuple[str, str]:
    if content and content.strip():
        return content.strip(), "manual_input"

    if not filename or file_bytes is None:
        raise ValueError("Either non-empty content or an uploaded file is required.")

    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages if (page.extract_text() or "").strip())
        if not text.strip():
            raise ValueError("No extractable text found in the uploaded PDF.")
        return text.strip(), filename

    if suffix in {".txt", ".md", ".markdown"}:
        return file_bytes.decode("utf-8", errors="ignore").strip(), filename

    if suffix in {".docx", ".doc"}:
        doc = DocxDocument(io.BytesIO(file_bytes))
        text = "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())
        if not text.strip():
            raise ValueError("No extractable text found in the uploaded Word document.")
        return text.strip(), filename

    if suffix == ".rtf":
        raw = file_bytes.decode("utf-8", errors="ignore")
        text = re.sub(r"\\[a-z]+\d*\s?", "", raw)
        text = re.sub(r"\{[^}]*\}", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            raise ValueError("No extractable text found in the uploaded RTF file.")
        return text, filename

    raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")


def _load_jsonl_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def _load_graph_display(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {
            "nodes": [],
            "edges": [],
            "metadata": {
                "node_count": 0,
                "edge_count": 0,
                "is_directed": True,
                "is_acyclic": False,
            },
        }
    return _to_display_graph(load_graph(str(path)))


def _to_display_graph(graph: Dict) -> Dict:
    nodes = []
    edges = []

    for node in graph.get("nodes", []):
        properties = node.get("properties", {}) or {}
        nodes.append(
            {
                "id": node.get("id"),
                "label": properties.get("display_name") or node.get("id"),
                "domain": properties.get("esg_domain") or properties.get("domain") or "general",
                "type": node.get("type", "Entity"),
                "confidence": float(properties.get("confidence", 0.8)),
            }
        )

    for edge in graph.get("edges", []):
        properties = edge.get("properties", {}) or {}
        edges.append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "relationship_type": edge.get("relation", "related_to"),
                "confidence": float(properties.get("confidence", 0.75)),
                "evidence": str(properties.get("evidence", "")),
                "domain": properties.get("domain") or properties.get("esg_domain") or "general",
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "is_directed": True,
            "is_acyclic": _is_acyclic(edges),
        },
    }


def _to_relationship_rows(extractions: List[Dict], domain: str) -> List[Dict]:
    rows: List[Dict] = []
    for row in extractions:
        entity_lookup = _build_entity_lookup(row.get("entities", []) or [])
        for relation in row.get("relations", []) or []:
            if not isinstance(relation, dict):
                continue
            source = _resolve_relation_endpoint(
                relation.get("subject_id")
                or relation.get("source_id")
                or relation.get("from")
                or relation.get("source_entity")
                or relation.get("subject")
                or relation.get("source")
                or relation.get("entity_1"),
                entity_lookup,
            )
            target = _resolve_relation_endpoint(
                relation.get("object_id")
                or relation.get("target_id")
                or relation.get("to")
                or relation.get("target_entity")
                or relation.get("object")
                or relation.get("target")
                or relation.get("entity_2"),
                entity_lookup,
            )
            relation_type = relation.get("relation_type") or relation.get("relation") or relation.get("predicate") or "related_to"
            if not source or not target:
                continue
            rows.append(
                {
                    "cause": str(source),
                    "effect": str(target),
                    "confidence": float(relation.get("confidence", 0.75)),
                    "evidence": str(relation.get("evidence") or relation.get("context") or ""),
                    "domain": domain,
                    "relationship_type": str(relation_type),
                }
            )
    return rows


def _build_entity_lookup(entities: List[Dict]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for entity in entities:
        if isinstance(entity, str):
            normalized = normalize_entity_name(entity)
            if normalized:
                lookup[normalized] = normalized
            continue
        if not isinstance(entity, dict):
            continue
        resolved_name = normalize_entity_name(
            entity.get("name") or entity.get("entity") or entity.get("text") or entity.get("id") or ""
        )
        if not resolved_name:
            continue
        for key in (entity.get("id"), entity.get("name"), entity.get("entity"), entity.get("text")):
            normalized_key = normalize_entity_name(str(key or ""))
            if normalized_key:
                lookup[normalized_key] = resolved_name
    return lookup


def _resolve_relation_endpoint(value: object, entity_lookup: Dict[str, str]) -> str:
    normalized = normalize_entity_name(str(value or ""))
    if not normalized:
        return ""
    return entity_lookup.get(normalized, normalized)


def _is_acyclic(edges: List[Dict]) -> bool:
    if nx is None:
        return False
    graph = nx.DiGraph()
    for edge in edges:
        graph.add_edge(edge.get("source"), edge.get("target"))
    try:
        return nx.is_directed_acyclic_graph(graph)
    except Exception:
        return False


def _slugify(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return value.strip("_") or "document"


def _report_progress(
    callback: Optional[Callable[[str, str, int], None]],
    stage: str,
    message: str,
    progress: int,
) -> None:
    if callback is None:
        return
    callback(stage, message, max(0, min(progress, 100)))
