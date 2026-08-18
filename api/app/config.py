"""Application configuration, read from environment variables and the .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting the application needs, loaded from env vars or a .env file.

    Precedence follows pydantic-settings: init arguments > environment
    variables > .env file > the defaults below. Tests that assert on defaults
    must pass `_env_file=None`, otherwise a developer's local .env wins.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5433/file_understanding"

    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "anthropic/claude-sonnet-4.5"
    llm_max_tokens: int = 4096

    llama_cloud_api_key: str = ""

    # python-vm runs outside this compose project; from inside a container the
    # host is reachable through host.docker.internal.
    sandbox_base_url: str = "http://host.docker.internal:8081"
    sandbox_api_key: str = "dev-secret"
    sandbox_timeout_seconds: int = 30

    agent_max_steps: int = 8

    data_dir: Path = Path("/data")

    @property
    def uploads_dir(self) -> Path:
        """Directory holding the original files users uploaded."""
        return self.data_dir / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        """Directory holding parser output (markdown) for each document."""
        return self.data_dir / "artifacts"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the single Settings instance, cached so the env is read once."""
    return Settings()
