"""Application configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text:latest"
    # Ollama silently drops the start of a prompt longer than num_ctx, i.e.
    # the retrieved sources. Sized for the worst case: see DECISIONS.md.
    ollama_num_ctx: int = 16384
    ollama_num_predict: int = 1024
    ollama_timeout_seconds: float = 120.0
    # Output size of ollama_embed_model; also sizes chunks.embedding.
    embedding_dim: int = 768
    postgres_dsn: PostgresDsn = PostgresDsn(
        "postgresql://postgres:postgres@localhost:5432/findocbot"
    )

    db_pool_max_size: int = 5

    # Feeds the num_ctx budget (top_k x chunk_tokens); applies to new uploads.
    chunk_tokens: int = 300
    chunk_overlap_ratio: float = 0.15

    top_k: int = 5
    max_history_pairs: int = 5
    embedding_cache_size: int = 1000
    embedding_batch_size: int = 50
    embedding_cache_ttl_seconds: int | None = 3600
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_settings() -> Settings:
    """Load and validate runtime settings."""
    return Settings()
