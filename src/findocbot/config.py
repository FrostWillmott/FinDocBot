"""Application configuration."""

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text:latest"
    postgres_dsn: PostgresDsn = (
        "postgresql://postgres:postgres@localhost:5432/findocbot"  # type: ignore[assignment]
    )

    top_k: int = 5
    max_history_pairs: int = 5
    embedding_cache_size: int = 1000
    embedding_batch_size: int = 50
    embedding_cache_ttl_seconds: int | None = 3600


def load_settings() -> Settings:
    """Load and validate runtime settings."""
    return Settings()
