# Project Structure Summary

This repository has been cleaned for the main CausalGraph product path. The
old notebook experiments, raw ESG PDF corpora, Docs2KG sandbox, and standalone
text-to-KG prototype were removed because they are not required by the current
FastAPI + React application and made the GitHub repository unnecessarily large.

## Main Runtime

| Path | Role |
| --- | --- |
| `app.py` | Primary FastAPI entrypoint for auth, documents, chat, RAG, graph, admin, and feedback APIs. |
| `frontend/` | React application, including the Agent workspace and public pages. |
| `rag/` | Retrieval, routing, HyDE, reranking, query decomposition, OpenAI/Claude answering, Pinecone/local vector support. |
| `ai_service/` | ESG extraction layer and remote extraction fallback. |
| `document_processing/` | PDF parsing, text cleaning, and chunking used by ingestion. |
| `pipeline_runtime.py` | Upload ingestion orchestration: parse, chunk, extract, build graph, index vectors. |
| `graph/` | Causal graph helpers and Neo4j integration. |
| `metric_extraction/` | Structured ESG metric extraction and normalization. |
| `notifications/` | Notification and digest helpers. |
| `configs/` | Shared settings and environment-derived configuration. |
| `kg_view/` | Static graph inspection page. |
| `tests/` | Regression tests for RAG, retrieval, security, admin, notifications, and evaluation helpers. |

## Data Policy

Runtime data is intentionally ignored by Git:

- `auth.db`
- `backend/*.db`
- `data/raw/`
- `data/processed/`
- `data/chunks/`
- `data/extractions/`
- `data/graph/`
- `data/vector_store/`
- `data/documents/`
- local model folders under `models/` and `qlora_model/`

The taxonomy under `data/taxonomy/` is kept as source configuration because the
metric extraction code uses it at runtime.

## Removed Tracks

These paths were removed during cleanup because current code does not import
them and they mostly contained raw data, notebooks, generated outputs, or old
standalone prototypes:

- `ESG_Entity_Extraction/`
- `ESG_Ontology_Design/`
- `LLAMA_on_Colab/`
- `causalgraph_mvp/`
- `data_preprocessing/`
- `docs2kg/`
- `esg_relations/`
- `team_health_and_environment/`
- `text-to-kg-esg/`

If those assets are needed later, restore them in a separate archive or data
repository rather than mixing them back into the production app repo.
