# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MediGenius is a production-oriented healthcare AI assistant with two core pipelines:
1. Multi-department medical Q&A (RAG + LLM + optional web search) with streaming chat
2. Structured ECG parameter analysis with professional Chinese report generation (PDF output)

Tech stack: FastAPI backend + React/Vite frontend, LangGraph orchestration, ChromaDB retrieval, SQLite + JSON profiles.

## Development Commands

### Start Application
```bash
conda activate medigenius
python run.py
```
- Backend: port 8000 (fails if occupied)
- Frontend: port 5173 (auto-increments if occupied)

### Backend
```bash
cd backend
pip install -r requirements.txt
pytest -v                          # all tests
pytest tests/test_agents.py -v     # single file
pytest tests/test_agents.py::test_memory_read_agent -v  # single test
pytest --cov=app -v                # with coverage
pytest --cov=app --cov-report=html # HTML coverage report
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # dev server
npm run build    # production build
npm test         # run tests (vitest)
npm run lint     # ESLint
```

### Environment Setup
```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys
```

## Architecture

### Workflow (LangGraph) — 9 Nodes

```
semantic_cache
  ├── cache hit ───────────────────────────────────────────────► response
  └── cache miss
          │
          ▼
memory_read
  │
  ▼
keyword_router  ←── binary medical-intent classification
  │
  ├── selected_department_forced ──► query_rewriter → rag → reranker → executor
  │
  ├── domain = "medical" ──► medical_router → query_rewriter → rag → reranker → executor
  │                                            └─ (use_rag=false) → executor
  │
  └── non-medical ──► judge_need_rag → (need_rag) query_rewriter → rag → reranker → executor
                                      └─ (!need_rag) executor
                                                                         │
                                                                         ▼
                                                                  memory_write_async → END
                                                                         │
                                                                         ▼
                                                            semantic_cache store → response
```

Key rules:
- All paths converge to `executor` (single sink pattern)
- `keyword_router` performs one deterministic medical/non-medical classification
- `medical_router` only activates for `domain == "medical"` queries
- `judge_need_rag` only activates for non-medical queries
- `query_rewriter` remains in the pipeline but is a pass-through by default; the retained C2 path is fixed chunks + vector/Elasticsearch RRF + BGE reranking
- `memory_write_async` runs in background, doesn't block response
- `semantic_cache` lookup/store is handled by `ChatService`, outside the LangGraph nodes

### Agents (backend/app/agents/)

| File | Agent | Role |
|---|---|---|
| `memory.py` | MemoryReadAgent | Loads profile JSON, trims history to 20 entries |
| `memory.py` | MemoryWriteAsyncAgent | Async profile updates (non-blocking) |
| `planner.py` | KeywordRouterAgent | Deterministic medical/non-medical keyword classification |
| `medical_router.py` | MedicalRouterAgent | Routes medical queries across the 8 supported departments |
| `judge_need_rag.py` | JudgeNeedRAGAgent | Binary RAG-needed decision for general-domain queries only |
| `query_rewriter.py` | QueryRewriterAgent | Rewrites user question into retrieval-optimized queries (per-department for medical, single for others) |
| `retriever.py` | RetrieverAgent | Multi-scope parallel hybrid retrieval (ChromaDB vector + keyword) |
| `reranker.py` | RerankerAgent | Two-stage reranking: rule-based scoring + optional cross-encoder model |
| `executor.py` | ExecutorAgent | Final answer synthesis with web search, ECG skill, personalization, citation enforcement, safety templates |

### User/Session Identity

All state carries `user_id` + `session_id` for isolation. Identity is resolved via `RequestContext` (in `backend/app/api/v1/request_context.py`) with this priority:
1. Bearer token (HMAC-signed, from `Authorization` header)
2. Cookie session (`session_id`, `user_id` in starlette session)
3. Identity headers (`X-User-ID`, `X-Session-ID`) — only when `AUTH_TRUST_IDENTITY_HEADERS=true`

### AgentState (backend/app/core/state.py)

The state TypedDict has ~46 fields. Key categories:
- **Identity**: `user_id`, `session_id`, `question`, `messages`
- **Memory**: `memory_context`, `memory_profile`
- **Routing**: `keyword_hit`, `domain`, `selected_department`, `selected_department_forced`
- **Medical routing**: `primary_department`, `department_candidates`, `department_queries`, `department_multi_queries`, `routing_reason`
- **Retrieval pipeline**: `use_rag`, `need_rag`, `retrieval_query`, `retrieval_queries`, `query_complexity`, `retrieval_scopes`, `retrieval_results_by_scope`, `merged_rag_context`, `reranked_rag_context`, `rag_context`, `packed_rag_context`
- **Execution**: `generation`, `source`, `ecg_metrics`, `intent`
- **Tool tracking**: `tool_budget_used`, `tool_calls`, `current_tool`, `retry_count`
- **Profiling**: nested `profiling` dict with `node_timings_ms`, `token_usage`, `cost_usd`, `retrieval`
- **Trace**: `flow_trace` (list of visited node names for debugging)

### Services (backend/app/services/)

Core services:
- `chat_service.py`: Main chat orchestration with semantic cache integration
- `database_service.py`: SQLite for chat history + user auth tables
- `profile_service.py`: User profile CRUD with atomic writes

Auth & infrastructure:
- `auth_service.py`: PBKDF2-SHA256 password hashing + HMAC-signed access tokens (stateful, not JWT)
- `redis_service.py`: Optional Redis client with transparent in-memory fallback
- `rate_limit_service.py`: Fixed-window rate limiter (login: 10/min, chat: 60/min)
- `semantic_cache_service.py`: qwen3.5-flash structured signature (`entities`, `action`, `constraints`) + Redis Stack HNSW semantic cache
- `task_queue_service.py`: Thread-pool task queue with Redis-compatible status storage

ECG services:
- `ecg_report_service.py`: ECG report generation with risk stratification
- `ecg_monitor_service.py`: Remote ECG site monitoring and auto-report generation
- `ecg_pdf_service.py`: PDF report generation with waveform rendering

### Tools (backend/app/tools/)

- `llm_client.py`: OpenAI-compatible LLM clients (main + lightweight)
- `tavily_search.py`: Tavily web search integration
- `duckduckgo_search.py`: DuckDuckGo search fallback (needs `pip install duckduckgo-search`)
- `wikipedia_search.py`: Wikipedia API wrapper via langchain_community
- `vector_store.py`: ChromaDB vector store for RAG
- `keyword_retriever.py`: In-memory BM25-style keyword retriever
- `es_client.py`: Elasticsearch/OpenSearch REST client (httpx-based, non-ORM)
- `es_keyword_retriever.py`: Elasticsearch BM25 keyword search with field-weighted multi_match
- `model_reranker.py`: Cross-encoder model reranker (e.g., BAAI/bge-reranker-v2-m3)
- `pdf_loader.py`: Medical knowledge PDF processing with parent-child chunking

## API Endpoints

### Auth
- `GET /api/v1/auth/me` — current login status and identity
- `POST /api/v1/auth/login` — password login, returns Bearer token
- `POST /api/v1/auth/logout` — clear session identity

### Chat & Sessions
- `POST /api/v1/chat` — non-streaming chat
- `POST /api/v1/chat/stream` — SSE streaming chat (events: `start` → `delta*` → `done`/`error`)
- `POST /api/v1/chat/jobs` — queue async chat task, returns `job_id`
- `GET /api/v1/jobs/{job_id}` — poll async job status
- `GET /api/v1/sessions` — list sessions (scoped by user)
- `GET /api/v1/session/{session_id}` — load session details
- `DELETE /api/v1/session/{session_id}` — delete session
- `GET /api/v1/history` — current session chat history
- `POST /api/v1/new-chat` — create new session
- `POST /api/v1/clear` — clear conversation state
- `POST /api/v1/welcome` — generate proactive greeting

### ECG
- `POST /api/v1/ecg/report` — generate ECG report from structured parameters
- `GET /api/v1/ecg/report/{report_id}` — query report by ID
- `GET /api/v1/ecg/report/{report_id}/pdf` — download PDF report
- `POST /api/v1/ecg/monitor/start` — start ECG site monitoring task
- `GET /api/v1/ecg/monitor/{task_id}` — query monitoring task status

### Health
- `GET /api/v1/health` — health check
- `GET /api/v1/healthz` — lightweight liveness probe
- `GET /api/v1/readyz` — readiness probe (checks DB + Redis if enabled)

## Configuration

### Environment Variables (backend/.env)

See `backend/.env.example` for the full list. Key groups:

**Required:**
- `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`, `LIGHT_LLM_MODEL`
- `OPENAI_WIRE_API` — `chat` or `responses` (default: `chat`)
- `SESSION_SECRET_KEY`, `AUTH_TOKEN_SECRET`

**Auth:**
- `AUTH_ACCESS_TOKEN_TTL_SECONDS` (default: 1800)
- `AUTH_PASSWORD_HASH_ITERATIONS` (default: 310000)
- `AUTH_AUTO_CREATE_USERS` (default: true)
- `AUTH_TRUST_IDENTITY_HEADERS` (default: false)
- `AUTH_LOGIN_RATE_LIMIT_PER_MINUTE` (default: 10)

**RAG pipeline:**
- `RAG_ENABLED`, `EMBEDDING_MODEL_NAME`
- `QUERY_REWRITER_ENABLED`, `QUERY_REWRITER_USE_LLM`, `QUERY_REWRITER_MAX_SUBQUERIES`
- `HYBRID_RETRIEVAL_ENABLED`, `HYBRID_VECTOR_TOPK_SIMPLE/COMPLEX`, `HYBRID_KEYWORD_TOPK_SIMPLE/COMPLEX`
- `RETRIEVAL_PARALLEL_ENABLED`, `RETRIEVAL_PARALLEL_WORKERS`
- `KEYWORD_BACKEND` — `memory` or `elasticsearch`
- `RERANKER_MODEL_ENABLED`, `RERANKER_MODEL_NAME`, `RERANKER_STAGE1_TOP_N`, `RERANKER_FINAL_TOP_K`
- `RAG_CHUNK_STRATEGY` (default: `adaptive`), `RAG_PARENT_CHILD_ENABLED`

**Elasticsearch (when `KEYWORD_BACKEND=elasticsearch`):**
- `ES_ENABLED`, `ES_HOST`, `ES_INDEX_NAME`, `ES_USERNAME`, `ES_PASSWORD`, `ES_VERIFY_CERTS`, `ES_TIMEOUT_SECONDS`

**Generation:**
- `GENERATION_MAX_CONTEXT_CHUNKS`, `GENERATION_MAX_CONTEXT_CHARS`, `GENERATION_REQUIRE_CITATION`
- `WEB_SEARCH_ENABLED`, `WEB_SEARCH_USE_LLM_DECIDER`, `TAVILY_API_KEY`

**Infrastructure:**
- `REDIS_ENABLED`, `REDIS_URL` — optional Redis (falls back to in-memory)
- `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_TTL_SECONDS`
- `CHAT_RATE_LIMIT_PER_MINUTE` (default: 60), `CHAT_MAX_CONCURRENT_WORKFLOWS` (default: 8)
- `WORKFLOW_TIMEOUT_SECONDS` (default: 90)
- `TASK_QUEUE_ENABLED`, `TASK_QUEUE_MAX_WORKERS` (default: 4)

**ECG:**
- `ECG_SITE_URL`, `ECG_SITE_USER`, `ECG_SITE_PASS`
- `ECG_MONITOR_TARGET_CREATE_TIME`, `ECG_MONITOR_DATA_MODE` (`live` or `synthetic_normal`)
- `ECG_REPORT_PDF_DIR`

**Observability:**
- `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`, `LANGSMITH_WORKSPACE_ID`, `LANGSMITH_TAGS`

## Frontend Architecture

Single-file React 19 app (`frontend/src/App.jsx`, ~1460 lines). No client-side router, no state management library — all state lives in the root `App` component via `useState` and is passed down through props.

Key characteristics:
- **SSE streaming**: Chat uses `fetch` with `ReadableStream` to parse SSE frames (`event: delta` → incremental message updates)
- **Auth**: Login modal → Bearer token stored in `localStorage` → attached to all API calls via centralized `apiFetch` wrapper
- **ECG flow**: Guide modal collects patient info → starts monitor task → polls via `EventSource` or REST → displays report with risk level + PDF download link in chat
- **Styling**: Tailwind CSS 4 + daisyUI 5 + custom CSS in `index.css`
- **Testing**: vitest + @testing-library/react + happy-dom

## Testing

### Test Configuration
- `pytest.ini`: `asyncio_mode = auto`
- `pyproject.toml`: test discovery in `tests/`, auto `--cov=app`
- `conftest.py`: Autouse fixtures mock ALL external dependencies (DB, LLM, vector store, PDF processing, workflow) so tests run without real API keys

### Test Files (20 total)
- `test_agents.py` — all agent unit tests
- `test_workflow.py`, `test_workflow_routing.py` — LangGraph integration + routing branches
- `test_api.py`, `test_api_edge_cases.py`, `test_auth_api.py` — API endpoint tests
- `test_database.py`, `test_services.py`, `test_profile_service.py` — service layer
- `test_ecg_service.py`, `test_ecg_api.py`, `test_ecg_monitor_service.py` — ECG
- `test_tools.py` — LLM client, vector store, PDF loader, keyword retriever
- `test_semantic_cache_service.py`, `test_semantic_cache_redis_integration.py`, `test_greeting_service.py` — semantic cache and specific services
- `test_evaluation_tools.py` — consolidated evaluation pipeline tests
- `test_coverage_gaps.py` — deep branch coverage for Executor, session endpoints, lifespan
- `test_logging.py` — logging infrastructure

## LangSmith Evaluation Pipeline

Five scripts under `backend/scripts/evaluation/` build, upload, and evaluate three independent datasets: RAG 150, end-to-end routing 50, and Redis semantic-cache 50 pairs. The RAG report uses Hit@1, Recall@5, MRR, answer faithfulness, and retrieval latency; routing reports route and department accuracy; Redis reports hit-decision accuracy and paired latency. See `docs/evaluation/` for the exact protocol and current results.

## Risk Controls

- **Executor tool loop**: Hard budget (max 2 calls) + same-tool repeat limit (max 1) + timeout + forced final answer
- **Memory JSON corruption**: Atomic writes + file locking + limited retry on failure
- **RAG low quality**: Executor autonomous judgment with optional WebSearch fallback
- **Semantic cache matching**: Exact `entities + action + constraints` TAG filtering precedes the 0.80 vector threshold; extraction or Redis Search failures fall through to the full workflow
- **Rate limiting**: Fixed-window counters on login (10/min) and chat (60/min)

## Language & Tone

- All responses default to Simplified Chinese
- Response structure: (1) Brief answer to core question, (2) 1-3 actionable suggestions, (3) Mandatory proactive follow-up question
- High-risk symptoms (chest pain, dyspnea, altered consciousness) trigger emergency advice template
- Non-urgent issues get "observe at home + seek care thresholds" dual-track advice
- Executor personalizes tone based on user profile preferences

## ECG Skill Trigger

ECG reports triggered by embedding JSON in user messages:
```json
{"ecg": {"patient_info": {...}, "features": {...}}}
```

## Hardware Data Pipeline

Script: `hardware/fetch_latest_ecg_and_convert.py`

1. Login to cloud site, fetch latest ECG record
2. Download `.xls` ECG data to `hardware/ECGdata/`
3. Parse signal, calculate key metrics (no raw waveform retention)
4. Generate JSON ready for ECG Skill consumption
5. If age/height/weight missing, generate `manual_input_template.json`
