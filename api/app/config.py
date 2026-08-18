"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tập hợp cấu hình cho toàn bộ ứng dụng, nạp từ env hoặc file .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5433/file_understanding"

    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "anthropic/claude-sonnet-4.5"
    llm_max_tokens: int = 4096

    llama_cloud_api_key: str = ""

    sandbox_base_url: str = "http://host.docker.internal:8081"
    sandbox_api_key: str = "dev-secret"
    sandbox_timeout_seconds: int = 30

    agent_max_steps: int = 8

    data_dir: Path = Path("/data")

    @property
    def uploads_dir(self) -> Path:
        """Thư mục lưu file người dùng upload."""
        return self.data_dir / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        """Thư mục lưu artifact do agent sinh ra."""
        return self.data_dir / "artifacts"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Trả về instance Settings duy nhất (cache để không đọc env nhiều lần)."""
    return Settings()
