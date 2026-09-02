"""Create all tables (with pgvector extension) and seed synthetic data."""
from __future__ import annotations

from sqlalchemy import text

from .models import Base
from .session import engine


def init_db() -> None:
    """Run once at startup: ensure pgvector extension + create tables."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
