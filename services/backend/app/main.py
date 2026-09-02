"""CircuitMind AI — FastAPI application entrypoint (API Gateway)."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .config import settings
from .db.init_db import init_db
from .db.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort DB init + seed on startup (idempotent). Retries while the
    # Postgres container becomes healthy.
    for attempt in range(30):
        try:
            init_db()
            seed_if_empty()
            print("[api] database ready")
            break
        except Exception as exc:
            print(f"[api] waiting for DB ({attempt + 1}/30): {exc}")
            time.sleep(2)
    yield


app = FastAPI(
    title="CircuitMind AI",
    version="1.0.0",
    description="Autonomous agentic procurement platform for PCBA manufacturing.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "circuitmind-api", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "service": "CircuitMind AI",
        "docs": "/docs",
        "endpoints": {
            "analyze": "POST /api/v1/bom/analyze",
            "status": "GET /api/v1/jobs/{job_id}",
            "stream": "GET /api/v1/jobs/{job_id}/stream",
            "approve": "POST /api/v1/jobs/{job_id}/approve",
            "results": "GET /api/v1/jobs/{job_id}/results",
        },
    }
