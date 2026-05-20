# COMP8715 CasualGraphAI

This repository now contains a complete Python-first ESG report analysis workflow built around:

- PDF parsing and text chunking
- local vector retrieval for RAG
- a QLoRA fine-tuned ESG extraction model
- optional OpenAI/Claude-backed answer generation for higher-quality responses
- lightweight knowledge graph JSON generation
- optional Neo4j persistence for a real graph database backend
- a FastAPI service for extraction, RAG, and PDF pipeline execution

Historical experiment folders and raw training datasets have been removed from
the main repository so the GitHub version focuses on the production app and the
active ingestion/RAG pipeline.

## What This System Does

1. Read an ESG PDF report
2. Clean the extracted text
3. Split the report into chunks
4. Build a local vector index
5. Run the fine-tuned QLoRA model to extract `entities` and `relations`
6. Save extraction results as JSONL
7. Convert extractions into a graph JSON
8. Optionally sync documents, chunks, entities, and relationships into Neo4j
9. Answer questions with retrieval-augmented generation

## Directory Structure

```text
project/
├── app.py
├── requirements.txt
├── README.md
├── configs/
│   └── settings.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── chunks/
│   ├── extractions/
│   ├── graph/
│   └── vector_store/
├── ai_service/
│   ├── __init__.py
│   ├── model_loader.py
│   ├── extractor.py
│   ├── schemas.py
│   └── utils.py
├── document_processing/
│   ├── __init__.py
│   ├── pdf_parser.py
│   ├── text_cleaner.py
│   └── chunker.py
├── rag/
│   ├── __init__.py
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── retriever.py
│   └── rag_pipeline.py
├── graph/
│   ├── __init__.py
│   ├── graph_builder.py
│   ├── neo4j_store.py
│   ├── graph_store.py
│   └── graph_utils.py
├── scripts/
│   ├── run_pdf_pipeline.py
│   ├── batch_extract.py
│   ├── build_vector_index.py
│   └── build_graph.py
└── esg_qlora_adapter/
    ├── adapter_config.json
    ├── adapter_model.safetensors
    └── ...
```

## Adapter Placement

Preferred adapter location:

```text
esg_qlora_adapter/
├── adapter_config.json
├── adapter_model.safetensors
└── ...
```

The loader also auto-detects your existing training output here:

```text
qlora_model/esg-qwen2.5-7b-qlora/
├── adapter_config.json
├── adapter_model.safetensors
└── ...
```

and, if needed, the latest `checkpoint-*` directory under it.

You can override detection explicitly with:

```bash
export ESG_ADAPTER_PATH=/absolute/path/to/your/adapter
```

If the base Qwen model is already stored locally, point the loader to it explicitly:

```bash
export ESG_BASE_MODEL_PATH=/absolute/path/to/Qwen2.5-7B-Instruct
export HF_LOCAL_FILES_ONLY=true
```

By default, the root pipeline now prefers fast local-only loading. If you explicitly want Hugging Face downloads, enable them:

```bash
export ESG_MODEL_ALLOW_DOWNLOAD=true
export ESG_EMBEDDING_ALLOW_DOWNLOAD=true
```

The repository must not store the base model weights. The code loads:

- base model: `Qwen/Qwen2.5-7B-Instruct`
- adapter: auto-detected local adapter directory

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Environment File

You can keep runtime configuration in a local `.env` file. Start by copying:

```bash
cp .env.example .env
```

Do not commit real secrets such as Pinecone API keys or model paths.

## OpenAI-Backed QA

The root `8000` pipeline can now answer questions in three tiers:

1. `OpenAI API` if `OPENAI_API_KEY` is configured
2. local `Qwen + QLoRA` model
3. extractive fallback when neither model path is available

Recommended `.env` snippet:

```bash
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.1
OPENAI_MAX_TOKENS=700
OPENAI_TIMEOUT=60
```

When OpenAI is configured, `/rag/ask` still uses Pinecone/local retrieval first and only uses the API for final grounded answer generation. The response now includes a `backend` field such as `openai`, `local_qlora`, or `extractive_fallback`.

## DeepSeek Extraction Fallback

The ESG extraction pipeline now runs in three tiers:

1. local `Qwen + QLoRA`
2. remote `DeepSeek` API, if configured
3. heuristic extraction fallback

Recommended `.env` snippet:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT=60
```

The current implementation uses DeepSeek's OpenAI-compatible chat completion API. If you need a different DeepSeek endpoint path or model name, adjust only the `.env` values or the small client in `ai_service/remote_extractor.py`.

## Vector Store Provider

The project now supports two vector-store modes:

- `local`: default, using local FAISS or numpy/pickle fallback
- `pinecone`: remote Pinecone index, while keeping the existing local embedding pipeline

The default embedding model is now:

- `BAAI/bge-m3`

If a local copy exists under `./models/BAAI_bge-m3`, the project will automatically prefer that path.
The current local setup can use the SentenceTransformers ONNX backend when the downloaded model contains `onnx/model.onnx`.

If you use Pinecone with this default embedding model, create a dense index with:

- dimension: `1024`
- metric: `cosine`

To switch to Pinecone, set:

```bash
export VECTOR_STORE_PROVIDER=pinecone
export PINECONE_API_KEY=your_api_key
export PINECONE_INDEX_NAME=your_index_name
```

If Pinecone gave you a dedicated index host, you can use it instead of `PINECONE_INDEX_NAME`:

```bash
export PINECONE_INDEX_HOST=your_index_host
```

Optional:

```bash
export PINECONE_NAMESPACE=esg-demo
```

Recommended `.env` example for Pinecone:

```bash
VECTOR_STORE_PROVIDER=pinecone
PINECONE_API_KEY=your_api_key
PINECONE_INDEX_NAME=your_index_name
PINECONE_NAMESPACE=esg-demo
PINECONE_METRIC=cosine
```

Use `PINECONE_INDEX_HOST` if Pinecone provided a dedicated host for your index.
If your current Pinecone index was created for the old `384`-dimensional embedding setup, recreate it before switching to `bge-m3`.

## Neo4j Graph Store

The graph layer now supports two persistence modes:

- JSON graph files under `data/graph/`
- optional Neo4j sync for a real graph database

When Neo4j is configured, the root pipeline now syncs:

- `(:Document)` nodes
- `(:Chunk)` nodes
- `(:Entity)` nodes
- `(:Document)-[:HAS_CHUNK]->(:Chunk)`
- `(:Document)-[:HAS_ENTITY]->(:Entity)`
- `(:Entity)-[:MENTIONED_IN]->(:Chunk)`
- `(:Entity)-[:RELATIONSHIP {relation_type, evidence, confidence, ...}]->(:Entity)`

Recommended `.env` example for Neo4j:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j123
NEO4J_DATABASE=neo4j
NEO4J_AUTO_SYNC=true
```

The repository already contains a local Neo4j `docker-compose.yml` for MVP use.

## Start the API

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

If you are using a local `.env`, load it into the shell first:

```bash
set -a
source .env
set +a
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Pinecone startup example:

```bash
set -a
source .env
set +a
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
```

## API Endpoints

### Health Check

```bash
curl http://localhost:8000/health
```

### ESG Extraction

```bash
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"text":"NVIDIA achieved 100% renewable electricity in FY25."}'
```

### RAG Question Answering

This requires an already-built vector index.

```bash
curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What did NVIDIA achieve in renewable electricity in FY25?","top_k":5}'
```

### Upload And Rebuild Active Index

This endpoint ingests a manual text payload or uploaded file, rebuilds the active vector store, runs extraction, returns graph-ready JSON for the frontend, and auto-syncs into Neo4j when configured.

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "title=My ESG Report" \
  -F "domain=general" \
  -F "content=NVIDIA reported a 14% reduction in scope 2 market-based emissions."
```

### PDF Pipeline

```bash
curl -X POST http://localhost:8000/pipeline/pdf \
  -H "Content-Type: application/json" \
  -d '{"pdf_path":"data/raw/report.pdf","name":"nvidia_2025"}'
```

## Run the Full PDF Pipeline

```bash
python scripts/run_pdf_pipeline.py --pdf data/raw/report.pdf --name nvidia_2025
```

If Neo4j is configured, this command also writes the resulting document graph into Neo4j.

## Neo4j API Endpoints

### Neo4j Status And Stats

```bash
curl http://localhost:8000/graph/neo4j/status
```

### Neo4j Entity Lookup

```bash
curl "http://localhost:8000/graph/neo4j/entity/NVIDIA?limit=20"
```

### Neo4j Subgraph

```bash
curl "http://localhost:8000/graph/neo4j/subgraph?entity=NVIDIA&hops=2&limit=50"
```

### Question-To-Subgraph Lookup

```bash
curl -X POST http://localhost:8000/graph/neo4j/question \
  -H "Content-Type: application/json" \
  -d '{"question":"What climate risks and emissions metrics are related to NVIDIA?","hops":2,"limit":10}'
```

This performs:

1. `parse_pdf`
2. `clean_text`
3. `chunk_text`
4. save `data/processed/nvidia_2025.txt`
5. save `data/chunks/nvidia_2025_chunks.jsonl`
6. build vector store at `data/vector_store/nvidia_2025`
7. run QLoRA extraction on each chunk
8. save `data/extractions/nvidia_2025_extractions.jsonl`
9. build graph JSON
10. save `data/graph/nvidia_2025_graph.json`

## Batch ESG Extraction

```bash
python scripts/batch_extract.py \
  --input data/chunks/nvidia_2025_chunks.jsonl \
  --output data/extractions/nvidia_2025_extractions.jsonl
```

## Build Vector Index Separately

```bash
python scripts/build_vector_index.py \
  --chunks data/chunks/nvidia_2025_chunks.jsonl \
  --output data/vector_store/nvidia_2025
```

## Build Graph JSON Separately

```bash
python scripts/build_graph.py \
  --input data/extractions/nvidia_2025_extractions.jsonl \
  --output data/graph/nvidia_2025_graph.json
```

## How the Components Fit Together

### Extraction

- `ai_service/model_loader.py` loads the QLoRA model once
- `ai_service/extractor.py` runs the extraction prompt
- `ai_service/utils.py` normalizes imperfect model output into valid JSON

### Document Processing

- `document_processing/pdf_parser.py` reads PDF text
- `document_processing/text_cleaner.py` removes noisy repeated boilerplate
- `document_processing/chunker.py` builds overlapping chunks

### RAG

- `rag/embeddings.py` prefers `BAAI/bge-m3`
- when a local `models/BAAI_bge-m3` directory contains `onnx/model.onnx`, the embedding layer automatically uses the ONNX backend
- if the embedding model is not cached locally, it falls back to a deterministic local hash embedding so the pipeline can still run offline
- `rag/vector_store.py` supports both local storage and Pinecone
- in local mode, it prefers FAISS persistence and falls back to a pickle-based in-memory index when FAISS is unavailable
- in Pinecone mode, it reuses the current embedding pipeline and upserts chunk vectors plus metadata into your Pinecone index
- `rag/retriever.py` returns top-k chunks
- `rag/rag_pipeline.py` answers questions from retrieved evidence and falls back to an extractive answer when the QA model cannot be loaded

### Knowledge Graph

- `graph/graph_builder.py` converts extraction JSONL into nodes and edges
- `graph/graph_store.py` saves graph JSON
- `graph/graph_utils.py` handles normalization and deduplication

## Current Limitations

- The QLoRA model is used for ESG extraction and also reused in the simple RAG answer path. That is acceptable for MVP use, but a dedicated QA model would be better.
- The local offline fallback embeddings are intended for demos and development. For better retrieval quality, cache the sentence-transformer locally or point `ESG_EMBEDDING_MODEL_PATH` to a local embedding model directory.
- The graph layer currently saves JSON, not Neo4j or a graph database.
- PDF parsing is text-only and does not include OCR.
- If GPU memory is insufficient, run extraction offline on Colab or another machine, then import the resulting JSONL files.

## Existing Backend Note

The repository still contains the existing `backend/` FastAPI MVP, and it now supports calling the root-level local extraction service as a fallback/upgrade path for chunk ingestion. That part has not been removed.

## TODO

- Add a dedicated ESG QA prompt/model for RAG answers
- Add graph-aware QA routing at the root-level API
- Add graph visualization
- Add Neo4j persistence as an optional store
- Add asynchronous long-running pipeline jobs for large reports
