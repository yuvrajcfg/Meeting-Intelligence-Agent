from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Meeting Intelligence Agent"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    database_backend: Literal["memory", "sqlserver"] = "memory"
    indexing_mode: Literal["local", "celery"] = "local"
    transcript_storage_directory: Path = Path("storage/transcripts")
    chroma_persist_directory: Path = Path("storage/chroma")
    sqlserver_connection_string: str | None = None
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_model: str = "gpt-5-2-chat"
    embedding_api_key: SecretStr | None = None
    embedding_api_url: str | None = None
    embedding_base_url: str | None = None
    embedding_dimensions: int = Field(default=736, ge=1)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1000, ge=1)
    redis_url: str = "redis://localhost:6379/0"
    chroma_host: str | None = None
    chroma_port: int = Field(default=8001, ge=1, le=65535)


@lru_cache
def get_settings() -> Settings:
    return Settings()
