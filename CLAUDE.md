# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MediGenius is a personal medical AI assistant focused on two main capabilities:
1. Daily medical Q&A (RAG + LLM + optional web search)
2. Structured ECG parameter analysis with professional Chinese report generation

The project uses a LangGraph-based workflow with single-executor architecture and JSON-based user profiles for long-term memory.

## Development Commands

### Start Application
```bash
# Activate conda environment
conda activate medigenius

# Run both backend and frontend from root directory
python run.py
```
- Backend runs on port 8000 (fails if already in use)
- Frontend runs on port 5173 (auto-increments to 5174, 5175... if occupied)

### Backend Development
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest -v

# Run single test file
pytest tests/test_agents.py -v

# Run tests with coverage
pytest --cov=app -v
```

### Frontend Development
```bash
cd frontend

# Install dependencies (auto-run by run.py)
npm install

# Run dev server
npm run dev

# Build for production
npm run build

# Run tests
npm test

# Lint code
npm run lint
```

### Environment Setup
```bash
# Copy example environment file
cp backend/.env.example backend/.env

# Then edit backend/.env with your API keys
```

## Architecture

### Workflow (LangGraph)
The main conversation flow follows this path:
```
MemoryRead → KeywordRouter → (RAG | JudgeNeedRAG) → Executor → MemoryWriteAsync
```

Key points:
- All paths converge to `ExecutorAgent` (single sink pattern)
- `RAG` node only retrieves, does NOT make sufficiency decisions
- `MemoryWriteAsync` runs in background, doesn't block response
- ECG skill can be triggered directly via embedded JSON payload

### Core Components

**Agents (backend/app/agents/):**
- `memory.py`: MemoryReadAgent (reads profile JSON), MemoryWriteAsyncAgent (async profile updates)
- `planner.py`: KeywordRouterAgent (keyword-based routing)
- `judge_need_rag.py`: JudgeNeedRAGAgent (binary decision: need RAG or not)
- `retriever.py`: RetrieverAgent (pure RAG execution)
- `executor.py`: ExecutorAgent (final answer synthesis with optional web search)

**Services (backend/app/services/):**
- `profile_service.py`: User profile CRUD operations with atomic writes
- `ecg_report_service.py`: ECG report generation with risk stratification
- `ecg_monitor_service.py`: Remote ECG site monitoring and auto-report generation
- `ecg_pdf_service.py`: PDF report generation with waveform rendering

**Tools (backend/app/tools/):**
- `llm_client.py`: OpenAI-compatible LLM clients (main + lightweight)
- `tavily_search.py`: Web search integration (optional, requires TAVILY_API_KEY)
- `vector_store.py`: ChromaDB vector store for RAG
- `pdf_loader.py`: Medical knowledge PDF processing

### User Profile Structure (JSON)
Stored in `backend/storage/profiles/{session_id}.json`:
```json
{
  "basic_info": {
    "age": 30,
    "gender": "male",
    "height": 175,
    "weight": 70
  },
  "preferences": {
    "preferred_name": "小张",
    "communication_style": "warm",
    "detail_level": "balanced",
    "language": "zh"
  },
  "current_context": {
    "symptoms": "...",
    "medications": "...",
    "recent_exams": "...",
    "last_ecg_summary": "..."
  }
}
```

### State Management (AgentState)
Key fields in `backend/app/core/state.py`:
- `question`: Current user query
- `session_id`: User session identifier
- `memory_context`: Formatted profile context
- `rag_context`: Retrieved RAG chunks
- `use_rag`: Flag from keyword router
- `need_rag`: Flag from judge agent
- `generation`: Final LLM response
- `source`: Response source attribution
- `tool_budget_used`: Tool call count (max=2)
- `tool_calls`: History of tool invocations

## Testing

### Test Files
- `test_agents.py`: Agent unit tests
- `test_workflow.py`: Workflow integration tests
- `test_workflow_routing.py`: Routing branch tests
- `test_ecg_service.py`: ECG service tests
- `test_ecg_api.py`: ECG API endpoint tests
- `test_ecg_monitor_service.py`: ECG monitor tests
- `test_profile_service.py`: Profile service tests

### Running Tests
```bash
# All tests
pytest

# Specific test
pytest tests/test_agents.py::test_memory_read_agent

# With coverage
pytest --cov=app --cov-report=html
```

## Configuration

### Environment Variables (backend/.env)
Required:
- `OPENAI_API_KEY`: LLM API key
- `OPENAI_BASE_URL`: LLM base URL (for OpenAI-compatible APIs)
- `LLM_MODEL`: Main model (default: gpt-4o-mini)

Optional:
- `LIGHT_LLM_MODEL`: Lightweight model for routing (default: same as LLM_MODEL)
- `TAVILY_API_KEY`: Web search (if missing, web search disabled)
- `EMBEDDING_MODEL_NAME`: Embedding model for RAG
- `RAG_ENABLED`: Enable/disable RAG (default: true)

ECG Monitor:
- `ECG_SITE_URL`: Remote ECG monitoring site URL
- `ECG_SITE_USER`: Site username
- `ECG_SITE_PASS`: Site password

### Hardware Data Pipeline
Script: `hardware/fetch_latest_ecg_and_convert.py`

Flow:
1. Login to cloud site and fetch latest ECG record
2. Download `.xls` ECG data to `hardware/ECGdata/`
3. Parse signal and calculate key metrics (no raw waveform/lead_stats retention)
4. Generate JSON ready for ECG Skill/LLM consumption
5. If age/height/weight missing, generate `manual_input_template.json` for manual completion

### Path Configuration (in backend/app/core/config.py)
- `LOG_DIR`: Backend logs directory
- `CHAT_DB_PATH`: SQLite chat database path
- `VECTOR_STORE_DIR`: ChromaDB vector store directory
- `PDF_PATH`: Medical knowledge PDF path
- `PROFILE_STORE_DIR`: User profile JSON storage
- `ECG_REPORT_PDF_DIR`: Generated ECG PDF reports

## API Endpoints

### Chat & Session
- `POST /api/v1/chat`: Main chat endpoint
- `GET /api/v1/sessions`: List all sessions
- `GET /api/v1/session/{session_id}`: Get session details
- `GET /api/v1/history`: Get chat history

### ECG
- `POST /api/v1/ecg/report`: Generate ECG report from structured parameters
- `GET /api/v1/ecg/report/{report_id}`: Query report by ID
- `GET /api/v1/ecg/report/{report_id}/pdf`: Download PDF report
- `POST /api/v1/ecg/monitor/start`: Start ECG site monitoring task
- `GET /api/v1/ecg/monitor/{task_id}`: Query monitoring task status

### Health
- `GET /api/v1/health`: Backend health check

## Current Status (2026-03-09)

Completed Phases:
- Phase A: State and workflow refactoring
- Phase B: Memory JSON read/write with atomic updates
- Phase C: KeywordRouter + JudgeNeedRAG
- Phase D: RAG node pure execution
- Phase F: Async memory write after executor
- Phase H: Chinese experience with proactive follow-up questions
- Phase I: ECG report skill with risk stratification

In Progress:
- Phase E: Executor streaming output and tool strategy refinement
- Phase G: Full regression test coverage (some timeout issues need handling)

Next Steps:
1. Complete Executor tool call optimization and stop conditions
2. Fix and expand regression test coverage
3. Optimize "frontend guidance -> cloud fetch -> local calculation -> report generation" pipeline stability
4. Add ECG skill observability (logging, retry strategies)
5. Upgrade memory personalization from `preferences` for tone/detail control

## Risk Controls

- **Executor tool loop risk**: Hard budget (max 2 calls) + same-tool repeat limit (max 1) + timeout + forced final answer
- **Memory JSON corruption**: Atomic writes + file locking + limited retry on failure
- **Judge1 drift leading to misrouting**: Keyword priority + binary schema + offline sample regression
- **RAG low quality affecting answers**: Executor autonomous judgment with optional WebSearch fallback
- **Prompt-only output drift**: Prompt constraints + lightweight output post-processing as double safety
- **Over-warm tone obscuring medical advice**: Conclusion first, empathy second; emergency template priority for high-risk scenarios

## Important Notes

### Language & Tone
- All responses default to Simplified Chinese
- Executor uses personalized tone based on user preferences
- Medical advice is cautious; high-risk symptoms get emergency prompts
- Responses always end with proactive follow-up questions
- Response structure: (1) Brief answer to core question, (2) 1-3 actionable suggestions, (3) Mandatory proactive follow-up question
- High-risk symptoms (chest pain, dyspnea, altered consciousness) trigger emergency advice template
- Non-urgent issues get "observe at home + seek care thresholds" dual-track advice
- Output fallback: High English content triggers brief Chinese restatement; missing follow-up gets safe template auto-completion

### ECG Skill Trigger
ECG reports can be triggered by embedding JSON in user messages:
```json
{
  "ecg": {
    "patient_info": {...},
    "features": {...}
  }
}
```

### Memory Updates
- Profile updates run asynchronously after response generation
- Uses atomic file writes to prevent corruption
- Failures are logged but don't block responses

### Tool Call Limits
- Max 2 tool calls per query
- Max 1 repeated call to same tool
- Web search falls back gracefully if TAVILY_API_KEY is missing
