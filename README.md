# CircuitMind AI

Autonomous, agentic procurement platform for electronics/PCBA manufacturing. It converts
manual datasheet cross-referencing and multi-vendor checkout into a ~10-second
human-in-the-loop approval workflow.

Upload a Bill of Materials (BOM) as PDF / XLSX / CSV / image. The system parses it, checks
stock across distributors, uses `pgvector` RAG to find drop-in replacements for out-of-stock
parts, pauses for human approval, then generates optimized split purchase orders.

## Architecture

```
Browser (Next.js dashboard)
    │  upload BOM  ▲ SSE stream   ▲ approve
    ▼             │               │
FastAPI Gateway + Redis Queue + SSE Router      (services/backend/app)
    │  background worker pulls job
    ▼
LangGraph Multi-Agent Engine                    (services/backend/app/agents)
  BOM Parser → Market Check → Alternate Match (Vector RAG)
       → Human Approval Gate (interrupt/resume) → PO Generator
    │                              │
    ▼ file bytes                   ▼ query / write
Document AI (parser+OCR+embeddings)   PostgreSQL + pgvector
```

Members map to modules:

| Member | Module | Location |
| --- | --- | --- |
| 1 | Frontend Dashboard | `services/frontend` |
| 2 | Database Layer (PostgreSQL + pgvector) | `services/backend/app/db` |
| 3 | API Gateway & Queue Manager | `services/backend/app/api`, `app/queue` |
| 4 | Unstructured Data AI (parser/embeddings) | `services/backend/app/docai` |
| 5 | Multi-Agent Execution Engine | `services/backend/app/agents` |

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

The backend runs DB migrations + seeds a synthetic component catalog with embeddings on startup.

## Local dev (without Docker)

Backend:

```bash
cd services/backend
python -m venv .venv && . .venv/Scripts/activate   # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Requires a running Postgres (with pgvector) and Redis; see .env
uvicorn app.main:app --reload
python -m app.worker    # in a second terminal — background agent worker
```

Frontend:

```bash
cd services/frontend
npm install
npm run dev
```

## Design notes

- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (384-dim). If the model can't be
  downloaded (offline), the code falls back to a deterministic hash-based 384-dim embedding so
  the pipeline still runs end-to-end.
- **Distributor APIs:** DigiKey / Mouser / Arrow are simulated by a seeded multi-vendor stock
  table so the arbitrage logic is fully runnable without external credentials.
- **Human-in-the-loop:** the LangGraph engine raises an interrupt when a stockout is detected;
  state is checkpointed in Redis and resumed via `POST /api/v1/jobs/{id}/approve`.
- **Auditability:** every agent decision and human override is written to `audit_logs`.
