"""Application configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment."""

    ollama_base_url: str
    ollama_chat_model: str
    ollama_embed_model: str
    postgres_dsn: str
    top_k: int = 5
    max_history_pairs: int = 5
    embedding_cache_size: int = 1000
    embedding_batch_size: int = 50
    embedding_cache_ttl_seconds: int | None = 3600  # 1 hour default


def load_settings() -> Settings:
    """Load runtime settings with safe defaults for local development."""
    return Settings(
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_chat_model=os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b"),
        ollama_embed_model=os.getenv(
            "OLLAMA_EMBED_MODEL",
            "nomic-embed-text:latest",
        ),
        postgres_dsn=os.getenv(
            "POSTGRES_DSN",
            "postgresql://postgres:postgres@localhost:5432/findocbot",
        ),
    )
