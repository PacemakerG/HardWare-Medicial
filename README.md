<div align="center">

# MediGenius · 医枢智疗

**An engineering-oriented medical AI agent for multi-department Q&A and ECG report delivery**

MediGenius combines hierarchical routing, hybrid RAG, evidence-grounded generation, Redis semantic caching, LangSmith evaluation, and real-time SSE streaming in one runnable system.

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

MediGenius is more than a single-turn medical chatbot. It provides two complete application pipelines:

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
| B0 | Fixed chunks + vector only | 14.67% | 35.33% | 0.2419 | 25.06 ms |
| B1 | Semantic chunks | 16.00% | 31.67% | 0.2412 | 16.64 ms |
| B2 | Parent-child index | 12.00% | 36.00% | 0.2297 | 16.79 ms |
| B3 | OCR/text cleaning | 12.67% | 36.33% | 0.2321 | 16.79 ms |
| B4 | Query Rewrite | 14.67% | 38.00% | 0.2511 | 6344.59 ms |
| B5 | Vector + ES + RRF | 19.33% | 41.67% | 0.2989 | 17.64 ms |
| B6 | BGE Reranker | **28.67%** | **44.33%** | **0.3773** | 1054.75 ms |

### Final Combination and Trade-offs

The retained C2 system uses **fixed chunks + parallel vector/Elasticsearch retrieval + RRF + BGE Reranker**.

| Combination | Hit@1 | Recall@5 | MRR | Mean latency | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| C0 baseline | 14.67% | 35.33% | 0.2419 | 25.06 ms | Baseline |
| C1 + Reranker | 28.67% | 44.33% | 0.3773 | 1054.75 ms | Keep |
| C2 + ES/RRF | **30.00%** | **48.67%** | **0.4050** | 1067.76 ms | **Final** |
| C3 + Query Rewrite | 26.67% | 54.67% | 0.3970 | 7395.45 ms | Drop |
| C6 with parent-child | 22.67% | 46.33% | 0.3453 | 7393.07 ms | Drop |

- The Reranker provides the largest independent quality gain.
- ES/RRF adds about 13 ms while improving all three retrieval metrics.
- Query Rewrite is disabled by default because it reduces Hit@1/MRR and adds about 6.3 seconds on average.
- Parent-child indexing is removed because it lowers final quality while increasing indexing and storage complexity.

### Routing and Cache Results

| Experiment | Current result | Status |
| --- | --- | --- |
| Routing | 76.00% route accuracy, 65.00% department accuracy | Pre-fix diagnostic; formal post-fix model rerun pending |
| Redis | 100% decisions on 50 pairs; ~10.7 s → 6.70 ms | Five-field signature implemented; Redis Stack v2 rerun pending archival |

Model-dependent answer-faithfulness coverage and the post-fix routing run are not presented as completed. See the [evaluation report](docs/evaluation/评测结果.md) for definitions and limitations.

## Quick Start

### Requirements

- Python `3.11`
- Node.js `20+`
- Redis Stack with RediSearch/`FT.SEARCH`
- Elasticsearch `9.x`

### Install and Configure

```bash
git clone https://github.com/PacemakerG/HardWare-Medicial.git
cd HardWare-Medicial

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
HardWare-Medicial/
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

The original idea was inspired by [Md. Emon Hasan / MediGenius](https://github.com/Md-Emon-Hasan/MediGenius). This repository substantially rebuilds the prototype with hierarchical routing, scoped RAG, hybrid retrieval and reranking, Redis semantic caching, identity management, ECG delivery, and a complete evaluation pipeline.

Creators: [ElonGe](https://github.com/PacemakerG) · [xhforever](https://github.com/xhforever)

## Disclaimer

This project is for medical assistance, engineering practice, and research demonstration only. It does not replace licensed clinical diagnosis. Seek immediate in-person care for acute high-risk symptoms such as chest pain, breathing difficulty, or altered consciousness.
