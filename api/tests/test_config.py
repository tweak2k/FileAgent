from pathlib import Path

from app.config import Settings


def test_settings_doc_gia_tri_tu_moi_truong(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "key-123")
    monkeypatch.setenv("LLM_MODEL", "some/model")
    monkeypatch.setenv("SANDBOX_BASE_URL", "http://localhost:8081")
    monkeypatch.setenv("DATA_DIR", "/tmp/fu-data")

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://u:p@h:5432/db"
    assert settings.llm_base_url == "https://example.test/v1"
    assert settings.llm_api_key == "key-123"
    assert settings.llm_model == "some/model"
    assert settings.sandbox_base_url == "http://localhost:8081"
    assert settings.data_dir == Path("/tmp/fu-data")


def test_settings_co_gia_tri_mac_dinh_cho_agent_va_sandbox(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")

    settings = Settings()

    assert settings.agent_max_steps == 8
    assert settings.sandbox_timeout_seconds == 30
    assert settings.llm_max_tokens == 4096
