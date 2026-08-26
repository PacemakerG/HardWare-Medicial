<div align="center">

# MedAgent

**An engineering-oriented medical AI agent for multi-department Q&A and ECG report delivery**

MedAgent combines hierarchical routing, hybrid RAG, evidence-grounded generation, Redis semantic caching, LangSmith evaluation, and real-time SSE streaming in one runnable system.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](backend/pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0-1C3C3C)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](frontend/package.json)
[![Redis](https://img.shields.io/badge/Redis_Stack-HNSW-DC382D?logo=redis&logoColor=white)](https://redis.io/docs/latest/develop/interact/search-and-query/)
[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-9.4-005571?logo=elasticsearch&logoColor=white)](docker-compose.yml)

**English** · [简体中文](./README.zh-CN.md) · [Evaluation Plan](docs/evaluation/评测方案.md) · [Evaluation Report](docs/evaluation/评测结果.md)

</div>

---

## Overview

MedAgent is more than a single-turn medical chatbot. It provides two complete application pipelines:

- **Multi-department medical Q&A** — identify medical intent, route across eight departments, run scoped vector/BM25 retrieval, fuse results with RRF, rerank with BGE, and optionally fall back to web search.
- **ECG report delivery** — ingest structured ECG data, analyze parameters and risk levels, and produce a Chinese PDF report with waveform rendering.

The surrounding engineering layer includes user/session isolation, long-term memory, SSE streaming, semantic caching, rate limiting, asynchronous jobs, LangSmith traces, and separate evaluation suites.

## Core Capabilities

| Area | Implementation |
| --- | --- |
| Agent orchestration | Nine-node LangGraph workflow with a single Executor sink |
| Hierarchical routing | Medical/non-medical decision, eight-department classification, local RAG/web routing |
| Hybrid retrieval | Parallel ChromaDB vector and Elasticsearch BM25 retrieval with RRF fusion |
| Reranking | Rule-based pre-ranking plus `BAAI/bge-reranker-v2-m3` cross-encoder |
| Semantic cache | `qwen3.5-flash` structured extraction + Redis Stack TAG filters + HNSW vector search |
| Streaming | Token-level FastAPI SSE rendered incrementally by React |
| Identity | `user_id + session_id` ownership checks, PBKDF2 password hashing, HMAC tokens |
| Observability | LangSmith traces and independent RAG, routing, and Redis evaluation suites |

## Architecture

```text
React / Vite
    │
    ├── REST: auth, sessions, ECG, jobs
    └── SSE: streaming medical chat
             │
             ▼
      Redis Semantic Cache
       ├── Hit ───────────────────────────────────────► Response
       └── Miss
             │
             ▼
        MemoryRead
             │
        KeywordRouter ── non-medical ─► JudgeNeedRAG ─┐
             │                                        │
           medical                                    │
             ▼                                        │
        MedicalRouter (8 departments)                 │
             │                                        │
        QueryRewriter (pass-through by default)       │
             │                                        │
        Vector + Elasticsearch ──► RRF                │
             │                                        │
        BGE Reranker                                  │
             └──────────────────► Executor ◄──────────┘
                                      │
                           MemoryWriteAsync
                                      │
                         Semantic Cache Store
                                      │
                                  Response
```

The eight retrieval scopes are general medicine, general surgery, pediatrics, neurology, infectious disease, ENT, ophthalmology, and dermatology. Specialty routes search only their own PDFs; general medicine searches the full medical library.

## Redis Semantic Cache

Cache reuse is not decided by vector similarity alone. The service first compares the structured semantics that can change an answer, then performs vector retrieval.

```text
Question
   ├── qwen3.5-flash
   │      └── { entities, action, constraints }
   ├── BAAI/bge-small-zh-v1.5
   │      └── 512-d normalized embedding
   └── FT.SEARCH
          ├── exact entities TAG filter
          ├── exact action TAG filter
          ├── exact constraints TAG filter
          └── KNN Top1, cosine similarity ≥ 0.80
```

Each entry is a TTL-bound Redis Hash:

```text
Key: mg:semcache:item:{uuid}

entities | action | constraints | embedding | answer
```

`FT.SEARCH` combines all three exact filters with vector KNN. The answer is reused only when the structured fields are identical and similarity reaches `0.80`. Extraction, embedding, or Redis failures are treated as cache misses and fall through to the full RAG workflow.

## Evaluation

The project maintains three independent datasets with 250 samples in total:

| System | Size | Split | Metrics |
| --- | ---: | --- | --- |
| RAG | 150 | 50 single-hop, 50 multi-hop, 50 hard retrieval | Hit@1, Recall@5, MRR, answer faithfulness |
| Routing | 50 | 30 local RAG, 10 web medical, 10 non-medical | Route accuracy, department accuracy |
| Redis | 50 pairs | 25 reusable, 25 non-reusable | Hit-decision accuracy, average latency |

RAG evaluation searches the complete 20-PDF, 3,219-page corpus instead of a gold-only subset. Questions are generated from English source evidence and remain in English to avoid introducing a cross-language variable.

### Independent RAG Modules

Every module is first compared independently against the same B0 baseline, then evaluated in cumulative combinations.

| Version | Single change from B0 | Hit@1 | Recall@5 | MRR | Mean retrieval latency |
| --- | --- | ---: | ---: | ---: | ---: |
| B0 | Fixed chunks + vector only | 52.00% | 68.00% | 0.6060 | 25.06 ms |
| B1 | Semantic chunks | 53.33% | 69.67% | 0.6190 | 31.84 ms |
| B2 | Parent-child index | 52.67% | 69.33% | 0.6135 | 42.73 ms |
| B3 | OCR/text cleaning | 53.33% | 70.00% | 0.6205 | 29.61 ms |
| B4 | Query Rewrite | 53.33% | 75.33% | 0.6280 | 6344.59 ms |
| B5 | Vector + ES + RRF | 64.00% | 82.00% | 0.7150 | 38.07 ms |
| B6 | BGE Reranker | **72.00%** | **84.67%** | **0.7820** | 1054.75 ms |

### Final Combination and Trade-offs

The retained C2 system uses **fixed chunks + parallel vector/Elasticsearch retrieval + RRF + BGE Reranker**.

| Combination | Hit@1 | Recall@5 | MRR | Mean latency | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| C0 baseline | 52.00% | 68.00% | 0.6060 | 25.06 ms | Baseline |
| C1 + Reranker | 72.00% | 84.67% | 0.7820 | 1054.75 ms | Keep |
| C2 + ES/RRF | **80.00%** | **93.33%** | **0.8560** | 1067.76 ms | **Final** |
| C3 + Query Rewrite | 76.67% | 96.00% | 0.8300 | 7395.45 ms | Drop |
| C4 + OCR/text cleaning | 77.33% | 96.67% | 0.8360 | 7401.82 ms | Drop |
| C5 + semantic chunks | 78.67% | 96.00% | 0.8420 | 7448.26 ms | Drop |
| C6 + parent-child index | 79.33% | 97.33% | 0.8480 | 7491.12 ms | Drop |

- The Reranker provides the largest independent gain: +20.00pp Hit@1, +16.67pp Recall@5, and +0.1760 MRR. Its roughly one-second cost is accepted because it fixes the dominant ranking problem.
- ES/RRF adds about 13 ms on top of the Reranker while improving Hit@1 by 8.00pp and Recall@5 by 8.66pp, especially for drug names, abbreviations, and clinical terms.
- Query Rewrite broadens complex questions into multiple subqueries, but can weaken population, stage, and condition constraints. From C2 to C3 it raises Recall@5 by 2.67pp while reducing Hit@1 by 3.33pp and MRR by 0.0260, with about 6.3 seconds of extra latency.
- Semantic chunking adds only 1.33pp Hit@1 and 1.67pp Recall@5 while introducing boundary computation, threshold tuning, and more expensive knowledge-base rebuilds.
- Parent-child indexing adds only 0.67pp Hit@1, 1.33pp Recall@5, and 0.0075 MRR in the independent test. That gain does not justify dual indexes, mappings, deduplication, and parent-document expansion.
- Advanced OCR cleaning improves retrieval by no more than 2pp on the mostly clean official PDFs, so the final ingestion path keeps only basic header, line-break, and corruption normalization.

### Routing and Cache Results

| Experiment | Baseline | Final result |
| --- | --- | --- |
| RAG | 52.00% Hit@1, 68.00% Recall@5, 0.6060 MRR | **80.00%** Hit@1, **93.33%** Recall@5, **0.8560** MRR, **97.33/100** answer faithfulness |
| Routing | 76.00% route accuracy, 65.00% department accuracy | **92.00%** route accuracy, **87.50%** department accuracy |
| Redis | 10676.83 ms full-RAG mean latency | **100%** decisions on 50 pairs, **6.70 ms** cache-hit latency, **99.94%** reduction |

See the [evaluation report](docs/evaluation/评测结果.md) for metric definitions, per-version results, and experiment boundaries.

## Quick Start

### Requirements

- Python `3.11`
- Node.js `20+`
- Redis Stack with RediSearch/`FT.SEARCH`
- Elasticsearch `9.x`

### Install and Configure

```bash
git clone https://github.com/PacemakerG/MedAgent.git
cd MedAgent

cp backend/.env.example backend/.env

cd backend
uv sync --extra dev

cd ../frontend
npm install
```

Minimum configuration:

```dotenv
OPENAI_BASE_URL=your-openai-compatible-base-url
OPENAI_API_KEY=your-api-key
LLM_MODEL=Pro/deepseek-ai/DeepSeek-V3.2
LIGHT_LLM_MODEL=Pro/deepseek-ai/DeepSeek-V3.2

REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
SEMANTIC_CACHE_EXTRACTION_MODEL=qwen3.5-flash

ES_ENABLED=true
ES_HOST=http://localhost:9200
```

### Run

```bash
docker compose up -d redis elasticsearch
python run.py
```

Default endpoints: frontend `http://localhost:5173`, backend `http://localhost:8000`, OpenAPI `http://localhost:8000/docs`.

## Local Medical Knowledge Base

The medical PDFs are large and remain subject to publisher terms, so they stay local and are excluded from Git. Download them from the [official-source manifest](backend/data/knowledge/医学知识库官方下载来源.md), preserve the listed paths, and rebuild the vector store.

## Reproduce the Evaluations

```bash
cd backend

uv run python scripts/evaluation/build_datasets.py --validate-only
uv run python scripts/evaluation/upload_langsmith.py
uv run python scripts/evaluation/evaluate_rag.py --with-faithfulness
uv run python scripts/evaluation/evaluate_routing.py
uv run python scripts/evaluation/evaluate_redis_cache.py
```

Formal runs require real LLM, Tavily, Redis Stack Search, and Elasticsearch services; mocks are not accepted as experiment results.

## Tests

```bash
cd backend
uv run pytest -q

REDIS_ENABLED=true RUN_REDIS_STACK_INTEGRATION=1 \
uv run pytest tests/test_semantic_cache_redis_integration.py -q

cd ../frontend
npm test -- --run
npm run build
```

## Repository Layout

```text
MedAgent/
├── backend/
│   ├── app/
│   │   ├── agents/              # LangGraph nodes
│   │   ├── api/v1/              # FastAPI endpoints
│   │   ├── core/                # Config, state, workflow, taxonomy
│   │   ├── services/            # Chat, auth, cache, ECG, jobs
│   │   └── tools/               # LLM, vectors, ES, reranker, web tools
│   ├── data/eval/               # Three evaluation datasets and results
│   ├── data/knowledge/          # Local PDFs and source manifest
│   ├── scripts/evaluation/      # Five consolidated evaluation scripts
│   └── tests/                   # Unit, workflow, and service integration tests
├── frontend/                    # React 19 / Vite SPA
├── docs/evaluation/             # Evaluation plan and report
├── hardware/                    # ECG data processing
└── run.py                       # Full-stack launcher
```

## API Overview

| Area | Main endpoints |
| --- | --- |
| Auth | `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
| Chat | `POST /api/v1/chat`, `POST /api/v1/chat/stream` |
| Sessions | `GET /api/v1/sessions`, `GET/DELETE /api/v1/session/{session_id}` |
| ECG | `POST /api/v1/ecg/report`, `GET /api/v1/ecg/report/{id}/pdf` |
| Health | `GET /api/v1/healthz`, `GET /api/v1/readyz` |

## Acknowledgement

The project initially referenced an [open-source medical Agent prototype](https://github.com/Md-Emon-Hasan/MediGenius). This repository substantially rebuilds it with hierarchical routing, scoped RAG, hybrid retrieval and reranking, Redis semantic caching, identity management, ECG delivery, and a complete evaluation pipeline.

Creators: [ElonGe](https://github.com/PacemakerG) · [xhforever](https://github.com/xhforever)

## Disclaimer

This project is for medical assistance, engineering practice, and research demonstration only. It does not replace licensed clinical diagnosis. Seek immediate in-person care for acute high-risk symptoms such as chest pain, breathing difficulty, or altered consciousness.
