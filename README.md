# MediGenius (HardWare-Medicial)

[English](./README.md) | [简体中文](./README.zh-CN.md)

MediGenius is a production-oriented healthcare AI assistant built for real clinical-support workflows, not just single-turn demos.

It integrates two core pipelines:

1. Multi-department medical Q&A (`manual department lock + automatic routing + RAG`)
2. ECG report generation (`cloud fetch or synthetic-normal mode -> structured analysis -> PDF report`)

## About

This project combines agent orchestration, retrieval, streaming interaction, long-term memory, and medical report delivery into one end-to-end system.

It is designed for practical scenarios such as:

- Pre-consult triage and symptom guidance
- Chronic-care follow-up with context continuity
- Wearable/monitor ECG interpretation support

## Key Highlights

- Multi-agent workflow with a unified executor sink
- Department-level RAG routing with manual override support
- Real-time streaming chat (SSE, token-level updates)
- ECG end-to-end pipeline with waveform + narrative PDF output
- Multi-tenant isolation via `tenant_id + user_id + session_id`
- Config-driven behavior through `.env` switches

## Tech Stack

- Frontend: React + Vite
- Backend: FastAPI
- Orchestration: LangGraph
- Retrieval: ChromaDB
- Storage: SQLite + JSON profile store + filesystem artifacts

## Architecture (Simplified)

```text
Frontend (React/Vite)
   ├─ /api/v1/chat/stream (SSE)
   ├─ /api/v1/ecg/monitor/start
   └─ /api/v1/ecg/monitor/{task_id}

Backend (FastAPI)
   ├─ Agent Workflow:
   │   MemoryRead
   │    -> HealthConcierge / Router
   │    -> QueryRewriter
   │    -> Retriever / Reranker
   │    -> Executor
   │    -> MemoryWriteAsync
   ├─ RAG Vector Store (ChromaDB)
   ├─ Chat DB (SQLite)
   └─ ECG Report Service (PDF)
```

## Quick Start

### 1) Environment

```bash
conda activate medigenius
```

### 2) Install Dependencies

```bash
# backend
cd backend
pip install -r requirements.txt

# frontend
cd ../frontend
npm install
```

### 3) Configure Environment Variables

```bash
cp backend/.env.example backend/.env
```

Required examples:

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_WIRE_API` (`chat` or `responses`)
- `LLM_MODEL`
- `LIGHT_LLM_MODEL`

ECG-related examples:

- `ECG_SITE_URL` / `ECG_SITE_USER` / `ECG_SITE_PASS`
- `ECG_MONITOR_TARGET_CREATE_TIME`
- `ECG_MONITOR_DATA_MODE` (`live` or `synthetic_normal`)

### 4) Run

```bash
python run.py
```

Default ports:

- Backend: `8000`
- Frontend: `5173` (auto-increments if occupied)

## Core APIs

- `POST /api/v1/chat/stream`
- `GET /api/v1/sessions`
- `GET /api/v1/history`
- `POST /api/v1/new-chat`
- `POST /api/v1/ecg/report`
- `GET /api/v1/ecg/report/{report_id}`
- `GET /api/v1/ecg/report/{report_id}/pdf`
- `POST /api/v1/ecg/monitor/start`
- `GET /api/v1/ecg/monitor/{task_id}`

## Acknowledgement

This project was inspired by the original MediGenius prototype by **Md. Emon Hasan**:

- https://github.com/Md-Emon-Hasan/MediGenius

On top of that prototype, this repository introduces substantial re-engineering and feature expansion in routing, RAG, streaming, ECG reporting, and multi-user isolation.

## Creators

- ElonGe
  - GitHub: https://github.com/PacemakerG
- xhforever
  - GitHub: https://github.com/xhforever
- Project:
  - https://github.com/PacemakerG/HardWare-Medicial

## Disclaimer

This system is for medical assistance and research demonstration only. It does not replace licensed clinical diagnosis.
