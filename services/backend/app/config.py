"""Central application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the CircuitMind AI backend."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # CORS: comma-separated list of allowed origins.
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+psycopg://circuitmind:circuitmind@localhost:5432/circuitmind"

    redis_url: str = "redis://localhost:6379/0"
    bom_queue: str = "bom-processing-queue"

    # Agent engine.
    recursion_limit: int = 5
    # PRD target: drop-in substitutes must clear >= 0.95 compatibility when the
    # trained embedding model is in use. This is the score surfaced to the UI.
    compatibility_threshold: float = 0.95
    # Offline hash-embedding fallback produces lower cosine similarities for the
    # same semantic distance, so a genuine drop-in scores ~0.6-0.8 rather than
    # ~0.95. This floor keeps the alternate/HITL flow functional offline.
    hash_compatibility_threshold: float = 0.55
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    upload_dir: str = "uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
