# Bộ khung agent hỏi đáp tài liệu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng bộ khung cho phép người dùng upload tài liệu, chuyển sang markdown, rồi hỏi đáp nhiều lượt qua agent CodeAct chạy code trong sandbox python-vm.

**Architecture:** Ba service trong docker compose — `postgres`, `api` (FastAPI, chứa toàn bộ core agent), `ui` (Streamlit, chỉ gọi HTTP). Sandbox `python-vm` chạy độc lập ngoài compose ở port 8081, `api` gọi qua HTTP. Ba `Protocol` (`LLMClient`, `Parser`, `SandboxClient`) là ranh giới thay thế được, mỗi cái test bằng fake.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.x + Alembic, Postgres 17, Streamlit, httpx, openai SDK (trỏ base_url tới OpenRouter/Cerebras), LlamaParse REST API, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-file-understanding-framework-design.md`

## Global Constraints

- Python chạy bằng conda env `minhln`: `/Users/macpro24/miniconda3/envs/minhln/bin/python` (Python 3.14.6). Không tạo venv mới. Cài package bằng `/Users/macpro24/miniconda3/envs/minhln/bin/pip`.
- Mọi lệnh `pytest` trong plan chạy từ thư mục `api/` bằng `/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest`.
- Postgres cho test chạy từ compose, map ra host port **5433** (tránh đụng Postgres sẵn có ở 5432).
- `python-vm` KHÔNG nằm trong compose. Mặc định `SANDBOX_BASE_URL=http://host.docker.internal:8081`; khi chạy test/dev ngoài container dùng `http://localhost:8081`.
- Không dùng SDK `llama-cloud-services`; gọi LlamaParse bằng REST qua `httpx`.
- Không streaming SSE. Chat là request/response đồng bộ.
- Tên biến môi trường và giá trị mặc định lấy đúng theo spec, mục "Cấu hình".
- Docker base image: `python:3.14-slim`.
- Commit sau mỗi task, message tiếng Việt, prefix `feat:` / `test:` / `chore:`.

---

### Task 1: Nền tảng dự án — Settings, app FastAPI, Postgres cho test

**Files:**
- Create: `pyproject.toml`
- Create: `api/app/__init__.py`, `api/app/config.py`, `api/app/main.py`
- Create: `api/app/api/__init__.py`, `api/app/api/health.py`
- Create: `api/tests/__init__.py`, `api/tests/test_config.py`, `api/tests/test_health.py`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: không có.
- Produces: `app.config.Settings` (pydantic-settings) với các thuộc tính `database_url: str`, `llm_base_url: str`, `llm_api_key: str`, `llm_model: str`, `llm_max_tokens: int`, `llama_cloud_api_key: str`, `sandbox_base_url: str`, `sandbox_api_key: str`, `sandbox_timeout_seconds: int`, `agent_max_steps: int`, `data_dir: Path`; hàm `get_settings() -> Settings` (có `lru_cache`); `app.main.create_app() -> FastAPI`.

- [ ] **Step 1: Tạo `pyproject.toml`**

```toml
[project]
name = "file-understanding"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi==0.141.1",
    "uvicorn[standard]==0.52.3",
    "sqlalchemy==2.0.52",
    "alembic==1.19.1",
    "psycopg[binary]==3.3.4",
    "pydantic==2.12.5",
    "pydantic-settings==2.15.0",
    "httpx==0.28.1",
    "openai==3.2.0",
    "python-multipart==0.0.20",
]

[project.optional-dependencies]
dev = [
    "pytest==9.1.1",
    "pytest-asyncio==1.3.0",
]
ui = [
    "streamlit==1.61.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: test cần compose và python-vm đang chạy thật",
]

[tool.setuptools.packages.find]
where = ["api"]
include = ["app*"]
```

- [ ] **Step 2: Cài dependency vào env `minhln`**

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/pip install -e ".[dev,ui]"
```

Expected: cài thành công, không lỗi build wheel.

- [ ] **Step 3: Cập nhật `.gitignore`**

```
data/*
__pycache__/
*.pyc
.pytest_cache/
.env
*.egg-info/
```

- [ ] **Step 4: Viết `.env.example`**

```
DATABASE_URL=postgresql+psycopg://app:app@postgres:5432/file_understanding

LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_MAX_TOKENS=4096

LLAMA_CLOUD_API_KEY=

SANDBOX_BASE_URL=http://host.docker.internal:8081
SANDBOX_API_KEY=dev-secret
SANDBOX_TIMEOUT_SECONDS=30

AGENT_MAX_STEPS=8
DATA_DIR=/data
```

- [ ] **Step 5: Viết test cho Settings (test thất bại trước)**

File `api/tests/test_config.py`:

```python
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
```

- [ ] **Step 6: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 7: Viết `api/app/config.py`**

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
        return self.data_dir / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

Tạo `api/app/__init__.py` rỗng.

- [ ] **Step 8: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_config.py -v
```

Expected: 2 passed

- [ ] **Step 9: Viết test cho endpoint health (FAIL trước)**

File `api/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_tra_ve_trang_thai_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "file-understanding-api"
```

- [ ] **Step 10: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_health.py -v
```

Expected: FAIL — `No module named 'app.main'`

- [ ] **Step 11: Viết `api/app/api/health.py` và `api/app/main.py`**

`api/app/api/__init__.py` rỗng.

`api/app/api/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "file-understanding-api"}
```

`api/app/main.py`:

```python
from __future__ import annotations

from fastapi import FastAPI

from app.api import health


def create_app() -> FastAPI:
    app = FastAPI(title="File Understanding API", version="0.1.0")
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 12: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/ -v
```

Expected: 3 passed

- [ ] **Step 13: Viết `docker-compose.yml` với riêng service postgres**

```yaml
services:
  postgres:
    image: postgres:17-alpine
    container_name: fu-postgres
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: file_understanding
    ports:
      - "5433:5432"
    volumes:
      - fu_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d file_understanding"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  fu_pgdata:
```

- [ ] **Step 14: Khởi động Postgres và tạo DB test**

```bash
docker compose up -d postgres
docker compose exec -T postgres psql -U app -d file_understanding -c "SELECT 1;"
docker compose exec -T postgres createdb -U app file_understanding_test
```

Expected: `SELECT 1` trả về 1 hàng; `createdb` không báo lỗi.

- [ ] **Step 15: Commit**

```bash
git add pyproject.toml .gitignore .env.example docker-compose.yml api/
git commit -m "feat: nền tảng dự án — Settings, FastAPI health, Postgres compose"
```

---

### Task 2: Mô hình dữ liệu và migration

**Files:**
- Create: `api/app/db/__init__.py`, `api/app/db/base.py`, `api/app/db/models.py`, `api/app/db/session.py`
- Create: `api/alembic.ini`, `api/alembic/env.py`, `api/alembic/script.py.mako`, `api/alembic/versions/0001_initial.py`
- Create: `api/tests/conftest.py`, `api/tests/test_models.py`

**Interfaces:**
- Consumes: `app.config.get_settings`.
- Produces: `app.db.base.Base`; các model `Document`, `DocumentArtifact`, `Conversation`, `Message`, `AgentStep`; `app.db.session.get_session_factory() -> sessionmaker`, `app.db.session.get_db()` (FastAPI dependency yield `Session`); fixture pytest `db_session`.

- [ ] **Step 1: Viết test cho model (FAIL trước)**

File `api/tests/conftest.py`:

```python
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://app:app@localhost:5433/file_understanding_test",
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

File `api/tests/test_models.py`:

```python
from __future__ import annotations

from app.db.models import AgentStep, Conversation, Document, DocumentArtifact, Message


def test_tao_document_va_artifact(db_session):
    doc = Document(filename="hsmt.pdf", mime_type="application/pdf", source_path="/data/uploads/1/hsmt.pdf")
    db_session.add(doc)
    db_session.flush()

    assert doc.parse_status == "pending"

    artifact = DocumentArtifact(
        document_id=doc.id,
        kind="markdown",
        content_path="/data/artifacts/1.md",
        char_count=1234,
        parser_name="llamaparse",
    )
    db_session.add(artifact)
    db_session.flush()

    assert artifact.document_id == doc.id
    assert doc.artifacts[0].kind == "markdown"


def test_conversation_giu_sandbox_session_id(db_session):
    doc = Document(filename="a.pdf", mime_type="application/pdf", source_path="/x")
    db_session.add(doc)
    db_session.flush()

    conv = Conversation(document_id=doc.id, title="Hỏi về HSMT")
    db_session.add(conv)
    db_session.flush()

    assert conv.sandbox_session_id is None

    conv.sandbox_session_id = "sess_abc"
    db_session.flush()

    assert conv.sandbox_session_id == "sess_abc"


def test_message_va_agent_step_lien_ket(db_session):
    doc = Document(filename="a.pdf", mime_type="application/pdf", source_path="/x")
    db_session.add(doc)
    db_session.flush()
    conv = Conversation(document_id=doc.id, title="t")
    db_session.add(conv)
    db_session.flush()

    msg = Message(conversation_id=conv.id, role="assistant", content="trả lời")
    db_session.add(msg)
    db_session.flush()

    step = AgentStep(
        message_id=msg.id,
        step_index=0,
        code="print(1)",
        stdout="1\n",
        stderr="",
        status="completed",
        duration_ms=12,
    )
    db_session.add(step)
    db_session.flush()

    assert msg.steps[0].code == "print(1)"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_models.py -v
```

Expected: FAIL — `No module named 'app.db'`

- [ ] **Step 3: Viết `api/app/db/base.py`**

```python
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

Tạo `api/app/db/__init__.py` rỗng.

- [ ] **Step 4: Viết `api/app/db/models.py`**

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    source_path: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    artifacts: Mapped[list["DocumentArtifact"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    content_path: Mapped[str] = mapped_column(String(1024))
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    parser_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="artifacts")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(512))
    sandbox_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sandbox_session_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="(Message.created_at, Message.id)",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="AgentStep.step_index",
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    step_index: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(Text)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    message: Mapped[Message] = relationship(back_populates="steps")
```

- [ ] **Step 5: Viết `api/app/db/session.py`**

```python
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    factory = get_session_factory()
    with factory() as session:
        yield session
```

- [ ] **Step 6: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_models.py -v
```

Expected: 3 passed

- [ ] **Step 7: Khởi tạo Alembic và sinh migration đầu tiên**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/alembic init alembic
```

Sửa `api/alembic/env.py`, thay phần cấu hình target metadata và URL:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401  — nạp model để autogenerate thấy bảng

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 8: Sinh và chạy migration**

```bash
cd api && DATABASE_URL="postgresql+psycopg://app:app@localhost:5433/file_understanding" \
  /Users/macpro24/miniconda3/envs/minhln/bin/alembic revision --autogenerate -m "initial schema"
cd api && DATABASE_URL="postgresql+psycopg://app:app@localhost:5433/file_understanding" \
  /Users/macpro24/miniconda3/envs/minhln/bin/alembic upgrade head
```

Expected: sinh file trong `api/alembic/versions/`, `upgrade head` chạy không lỗi.

- [ ] **Step 9: Xác nhận bảng đã tạo**

```bash
docker compose exec -T postgres psql -U app -d file_understanding -c "\dt"
```

Expected: thấy 5 bảng `documents`, `document_artifacts`, `conversations`, `messages`, `agent_steps` (kèm `alembic_version`).

- [ ] **Step 10: Commit**

```bash
git add api/
git commit -m "feat: mô hình dữ liệu và migration Alembic"
```

---

### Task 3: SandboxClient — wrap HTTP của python-vm

**Files:**
- Create: `api/app/core/__init__.py`, `api/app/core/sandbox/__init__.py`
- Create: `api/app/core/sandbox/models.py`, `api/app/core/sandbox/exceptions.py`, `api/app/core/sandbox/base.py`, `api/app/core/sandbox/client.py`
- Create: `api/tests/test_sandbox_client.py`

**Interfaces:**
- Consumes: `app.config.get_settings`.
- Produces:
  - `SandboxFile(path: str, content: str)` — dataclass, `content` là text thuần, client tự base64.
  - `ExecutionResult(status: str, stdout: str, stderr: str, timed_out: bool, duration_ms: int)` — dataclass.
  - Protocol `SandboxClient` với `create_session(files: list[SandboxFile]) -> str`, `execute(session_id: str, code: str) -> ExecutionResult`, `close_session(session_id: str) -> None`.
  - `HttpSandboxClient(base_url: str, api_key: str, timeout_seconds: int)` — hiện thực protocol.
  - Exception: `SandboxError` (gốc), `SandboxSessionNotFound`, `SandboxCapacityError`, `SandboxUnavailable`.

- [ ] **Step 1: Viết test (FAIL trước)**

File `api/tests/test_sandbox_client.py`:

```python
from __future__ import annotations

import base64

import httpx
import pytest

from app.core.sandbox.client import HttpSandboxClient
from app.core.sandbox.exceptions import (
    SandboxCapacityError,
    SandboxSessionNotFound,
    SandboxUnavailable,
)
from app.core.sandbox.models import SandboxFile


def build_client(handler) -> HttpSandboxClient:
    transport = httpx.MockTransport(handler)
    return HttpSandboxClient(
        base_url="http://sandbox.test",
        api_key="secret",
        timeout_seconds=30,
        transport=transport,
    )


def test_create_session_gui_file_base64_va_bearer_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"session_id": "sess_1"})

    client = build_client(handler)

    session_id = client.create_session([SandboxFile(path="document.md", content="# Xin chào")])

    assert session_id == "sess_1"
    assert captured["url"] == "http://sandbox.test/sessions"
    assert captured["auth"] == "Bearer secret"
    assert base64.b64encode("# Xin chào".encode()).decode() in captured["body"]


def test_execute_tra_ve_ket_qua_chuan_hoa():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://sandbox.test/sessions/sess_1/execute"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "stdout": "42\n",
                "stderr": "",
                "timed_out": False,
                "duration_ms": 15,
            },
        )

    client = build_client(handler)

    result = client.execute("sess_1", "print(42)")

    assert result.status == "completed"
    assert result.stdout == "42\n"
    assert result.timed_out is False
    assert result.duration_ms == 15


def test_execute_404_nem_session_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "session not found"})

    client = build_client(handler)

    with pytest.raises(SandboxSessionNotFound):
        client.execute("sess_die", "print(1)")


def test_create_session_429_nem_capacity_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "session limit reached"})

    client = build_client(handler)

    with pytest.raises(SandboxCapacityError):
        client.create_session([])


def test_khong_ket_noi_duoc_nem_sandbox_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = build_client(handler)

    with pytest.raises(SandboxUnavailable):
        client.create_session([])


def test_close_session_bo_qua_404():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(404)

    client = build_client(handler)

    client.close_session("sess_die")  # không được ném lỗi
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_sandbox_client.py -v
```

Expected: FAIL — `No module named 'app.core'`

- [ ] **Step 3: Viết models và exceptions**

`api/app/core/__init__.py`, `api/app/core/sandbox/__init__.py` rỗng.

`api/app/core/sandbox/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxFile:
    path: str
    content: str


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int

    @property
    def failed(self) -> bool:
        return self.status != "completed"
```

`api/app/core/sandbox/exceptions.py`:

```python
from __future__ import annotations


class SandboxError(Exception):
    """Lỗi hạ tầng khi làm việc với sandbox."""


class SandboxSessionNotFound(SandboxError):
    """Session không còn tồn tại (đã bị reap)."""


class SandboxCapacityError(SandboxError):
    """Sandbox hết slot session."""


class SandboxUnavailable(SandboxError):
    """Không kết nối được tới sandbox."""
```

- [ ] **Step 4: Viết protocol `api/app/core/sandbox/base.py`**

```python
from __future__ import annotations

from typing import Protocol

from app.core.sandbox.models import ExecutionResult, SandboxFile


class SandboxClient(Protocol):
    def create_session(self, files: list[SandboxFile]) -> str: ...

    def execute(self, session_id: str, code: str) -> ExecutionResult: ...

    def close_session(self, session_id: str) -> None: ...
```

- [ ] **Step 5: Viết `api/app/core/sandbox/client.py`**

```python
from __future__ import annotations

import base64

import httpx

from app.core.sandbox.exceptions import (
    SandboxCapacityError,
    SandboxError,
    SandboxSessionNotFound,
    SandboxUnavailable,
)
from app.core.sandbox.models import ExecutionResult, SandboxFile


class HttpSandboxClient:
    """Gọi python-vm qua HTTP. Xem README của python-vm cho hợp đồng API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds + 15,
            transport=transport,
        )

    def create_session(self, files: list[SandboxFile]) -> str:
        payload = {
            "files": [
                {
                    "path": f.path,
                    "content_base64": base64.b64encode(f.content.encode()).decode(),
                    "size_bytes": len(f.content.encode()),
                }
                for f in files
            ]
        }
        data = self._request("POST", "/sessions", json=payload)
        return data["session_id"]

    def execute(self, session_id: str, code: str) -> ExecutionResult:
        data = self._request(
            "POST",
            f"/sessions/{session_id}/execute",
            json={"code": code, "timeout_seconds": self._timeout_seconds},
        )
        return ExecutionResult(
            status=data.get("status", "failed"),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            timed_out=bool(data.get("timed_out", False)),
            duration_ms=int(data.get("duration_ms", 0)),
        )

    def close_session(self, session_id: str) -> None:
        try:
            self._request("DELETE", f"/sessions/{session_id}")
        except SandboxSessionNotFound:
            return

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            response = self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise SandboxUnavailable(f"Không gọi được sandbox: {exc}") from exc

        if response.status_code == 404:
            raise SandboxSessionNotFound(path)
        if response.status_code == 429:
            raise SandboxCapacityError("Sandbox đã hết slot session")
        if response.status_code >= 400:
            raise SandboxError(f"Sandbox trả về {response.status_code}: {response.text[:500]}")

        if not response.content:
            return {}
        return response.json()
```

- [ ] **Step 6: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_sandbox_client.py -v
```

Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add api/
git commit -m "feat: SandboxClient gọi python-vm qua HTTP"
```

---

### Task 4: SessionResolver — lazy re-attach

**Files:**
- Create: `api/app/core/sandbox/resolver.py`
- Create: `api/tests/fakes.py`
- Create: `api/tests/test_session_resolver.py`

**Interfaces:**
- Consumes: `SandboxClient` protocol, `SandboxFile`, `ExecutionResult`, `SandboxSessionNotFound`, model `Conversation`.
- Produces:
  - `SessionResolver(client: SandboxClient, db: Session)` với:
    - `ensure(conversation: Conversation, markdown: str) -> str`
    - `run_code(conversation: Conversation, markdown: str, code: str) -> ExecutionResult` — tự `ensure`, gặp `SandboxSessionNotFound` thì tái tạo và retry **đúng một lần**.
    - `reset(conversation: Conversation) -> None` — đóng session và xoá id khỏi DB.
  - Hằng số `WORKSPACE_DOCUMENT_PATH = "document.md"`.
- `api/tests/fakes.py` sinh `FakeSandboxClient` dùng lại ở Task 9.

- [ ] **Step 1: Viết `api/tests/fakes.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.sandbox.exceptions import SandboxSessionNotFound
from app.core.sandbox.models import ExecutionResult, SandboxFile


@dataclass
class FakeSandboxClient:
    """Sandbox giả: đếm số lần tạo session và cho phép ép session chết."""

    created_sessions: list[list[SandboxFile]] = field(default_factory=list)
    closed_sessions: list[str] = field(default_factory=list)
    executed: list[tuple[str, str]] = field(default_factory=list)
    dead_sessions: set[str] = field(default_factory=set)
    stdout_queue: list[str] = field(default_factory=list)
    _counter: int = 0

    def create_session(self, files: list[SandboxFile]) -> str:
        self._counter += 1
        self.created_sessions.append(files)
        return f"sess_{self._counter}"

    def execute(self, session_id: str, code: str) -> ExecutionResult:
        if session_id in self.dead_sessions:
            raise SandboxSessionNotFound(session_id)
        self.executed.append((session_id, code))
        stdout = self.stdout_queue.pop(0) if self.stdout_queue else ""
        return ExecutionResult(
            status="completed", stdout=stdout, stderr="", timed_out=False, duration_ms=1
        )

    def close_session(self, session_id: str) -> None:
        self.closed_sessions.append(session_id)


@dataclass
class FakeLLMClient:
    """LLM giả: trả lần lượt các response đã dựng sẵn."""

    responses: list[str] = field(default_factory=list)
    calls: list[list[dict[str, str]]] = field(default_factory=list)

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append([dict(m) for m in messages])
        if not self.responses:
            raise AssertionError("FakeLLMClient hết response nhưng vẫn bị gọi")
        return self.responses.pop(0)
```

- [ ] **Step 2: Viết test cho resolver (FAIL trước)**

File `api/tests/test_session_resolver.py`:

```python
from __future__ import annotations

import pytest

from app.core.sandbox.exceptions import SandboxSessionNotFound
from app.core.sandbox.resolver import WORKSPACE_DOCUMENT_PATH, SessionResolver
from app.db.models import Conversation, Document
from tests.fakes import FakeSandboxClient

MARKDOWN = "# Tài liệu\n\nNội dung."


@pytest.fixture
def conversation(db_session):
    doc = Document(filename="a.pdf", mime_type="application/pdf", source_path="/x")
    db_session.add(doc)
    db_session.flush()
    conv = Conversation(document_id=doc.id, title="t")
    db_session.add(conv)
    db_session.flush()
    return conv


def test_ensure_tao_session_moi_va_upload_markdown(db_session, conversation):
    client = FakeSandboxClient()
    resolver = SessionResolver(client=client, db=db_session)

    session_id = resolver.ensure(conversation, MARKDOWN)

    assert session_id == "sess_1"
    assert conversation.sandbox_session_id == "sess_1"
    assert len(client.created_sessions) == 1
    uploaded = client.created_sessions[0][0]
    assert uploaded.path == WORKSPACE_DOCUMENT_PATH
    assert uploaded.content == MARKDOWN


def test_ensure_dung_lai_session_da_co(db_session, conversation):
    client = FakeSandboxClient()
    resolver = SessionResolver(client=client, db=db_session)

    first = resolver.ensure(conversation, MARKDOWN)
    second = resolver.ensure(conversation, MARKDOWN)

    assert first == second
    assert len(client.created_sessions) == 1


def test_run_code_tai_tao_session_khi_gap_404(db_session, conversation):
    client = FakeSandboxClient()
    resolver = SessionResolver(client=client, db=db_session)
    resolver.ensure(conversation, MARKDOWN)
    client.dead_sessions.add("sess_1")

    result = resolver.run_code(conversation, MARKDOWN, "print(1)")

    assert result.status == "completed"
    assert conversation.sandbox_session_id == "sess_2"
    assert len(client.created_sessions) == 2
    assert client.executed == [("sess_2", "print(1)")]


def test_run_code_chi_retry_mot_lan(db_session, conversation):
    class AlwaysDead(FakeSandboxClient):
        def execute(self, session_id: str, code: str):
            raise SandboxSessionNotFound(session_id)

    client = AlwaysDead()
    resolver = SessionResolver(client=client, db=db_session)

    with pytest.raises(SandboxSessionNotFound):
        resolver.run_code(conversation, MARKDOWN, "print(1)")

    assert len(client.created_sessions) == 2


def test_reset_dong_session_va_xoa_id(db_session, conversation):
    client = FakeSandboxClient()
    resolver = SessionResolver(client=client, db=db_session)
    resolver.ensure(conversation, MARKDOWN)

    resolver.reset(conversation)

    assert client.closed_sessions == ["sess_1"]
    assert conversation.sandbox_session_id is None
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_session_resolver.py -v
```

Expected: FAIL — `No module named 'app.core.sandbox.resolver'`

- [ ] **Step 4: Viết `api/app/core/sandbox/resolver.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.sandbox.base import SandboxClient
from app.core.sandbox.exceptions import SandboxSessionNotFound
from app.core.sandbox.models import ExecutionResult, SandboxFile
from app.db.models import Conversation

WORKSPACE_DOCUMENT_PATH = "document.md"


class SessionResolver:
    """Sandbox session là cache, không phải nguồn sự thật.

    Nguồn sự thật là Postgres. Nếu session đã bị reaper của python-vm dọn,
    ta tạo lại và upload lại markdown — người dùng không cần biết.
    """

    def __init__(self, client: SandboxClient, db: Session) -> None:
        self._client = client
        self._db = db

    def ensure(self, conversation: Conversation, markdown: str) -> str:
        if conversation.sandbox_session_id:
            return conversation.sandbox_session_id
        return self._create(conversation, markdown)

    def run_code(self, conversation: Conversation, markdown: str, code: str) -> ExecutionResult:
        session_id = self.ensure(conversation, markdown)
        try:
            return self._client.execute(session_id, code)
        except SandboxSessionNotFound:
            session_id = self._create(conversation, markdown)
            return self._client.execute(session_id, code)

    def reset(self, conversation: Conversation) -> None:
        if conversation.sandbox_session_id:
            self._client.close_session(conversation.sandbox_session_id)
        conversation.sandbox_session_id = None
        conversation.sandbox_session_created_at = None
        self._db.flush()

    def _create(self, conversation: Conversation, markdown: str) -> str:
        session_id = self._client.create_session(
            [SandboxFile(path=WORKSPACE_DOCUMENT_PATH, content=markdown)]
        )
        conversation.sandbox_session_id = session_id
        conversation.sandbox_session_created_at = datetime.now(timezone.utc)
        self._db.flush()
        return session_id
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_session_resolver.py -v
```

Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add api/
git commit -m "feat: SessionResolver với lazy re-attach khi sandbox session bị reap"
```

---

### Task 5: LLMClient — adapter OpenAI-compatible

**Files:**
- Create: `api/app/core/llm/__init__.py`, `api/app/core/llm/base.py`, `api/app/core/llm/openai_compat.py`
- Create: `api/tests/test_llm_client.py`

**Interfaces:**
- Consumes: `app.config.Settings`.
- Produces:
  - Protocol `LLMClient` với `complete(messages: list[dict[str, str]]) -> str`.
  - `OpenAICompatibleClient(base_url: str, api_key: str, model: str, max_tokens: int, client=None)` — hiện thực protocol, retry 2 lần với backoff khi lỗi mạng/5xx, sau đó ném `LLMError`.
  - Exception `LLMError`.

`messages` là list dict `{"role": "system"|"user"|"assistant", "content": str}` — cùng dạng OpenAI dùng, để adapter không phải chuyển đổi gì.

- [ ] **Step 1: Viết test (FAIL trước)**

File `api/tests/test_llm_client.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.core.llm.openai_compat import LLMError, OpenAICompatibleClient


@dataclass
class FakeChoiceMessage:
    content: str


@dataclass
class FakeChoice:
    message: FakeChoiceMessage


@dataclass
class FakeCompletion:
    choices: list[FakeChoice]


@dataclass
class FakeCompletions:
    responses: list[object] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeOpenAI:
    def __init__(self, responses: list[object]) -> None:
        self.completions = FakeCompletions(responses=responses)
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_complete_tra_ve_noi_dung_va_gui_dung_model():
    fake = FakeOpenAI([FakeCompletion(choices=[FakeChoice(FakeChoiceMessage("xin chào"))])])
    client = OpenAICompatibleClient(
        base_url="https://x.test/v1", api_key="k", model="vendor/model", max_tokens=100, client=fake
    )

    answer = client.complete([{"role": "user", "content": "hi"}])

    assert answer == "xin chào"
    call = fake.completions.calls[0]
    assert call["model"] == "vendor/model"
    assert call["max_tokens"] == 100
    assert call["messages"] == [{"role": "user", "content": "hi"}]


def test_complete_retry_hai_lan_roi_thanh_cong():
    fake = FakeOpenAI(
        [
            RuntimeError("mạng lỗi"),
            RuntimeError("mạng lỗi"),
            FakeCompletion(choices=[FakeChoice(FakeChoiceMessage("ok"))]),
        ]
    )
    client = OpenAICompatibleClient(
        base_url="https://x.test/v1",
        api_key="k",
        model="m",
        max_tokens=10,
        client=fake,
        backoff_seconds=0,
    )

    assert client.complete([{"role": "user", "content": "hi"}]) == "ok"
    assert len(fake.completions.calls) == 3


def test_complete_that_bai_qua_so_lan_retry_thi_nem_llm_error():
    fake = FakeOpenAI([RuntimeError("x"), RuntimeError("x"), RuntimeError("x")])
    client = OpenAICompatibleClient(
        base_url="https://x.test/v1",
        api_key="k",
        model="m",
        max_tokens=10,
        client=fake,
        backoff_seconds=0,
    )

    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "hi"}])
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_llm_client.py -v
```

Expected: FAIL — `No module named 'app.core.llm'`

- [ ] **Step 3: Viết `api/app/core/llm/base.py`**

```python
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...
```

Tạo `api/app/core/llm/__init__.py` rỗng.

- [ ] **Step 4: Viết `api/app/core/llm/openai_compat.py`**

```python
from __future__ import annotations

import time

from openai import OpenAI

MAX_ATTEMPTS = 3


class LLMError(Exception):
    """Gọi LLM thất bại sau khi đã retry."""


class OpenAICompatibleClient:
    """Adapter cho mọi endpoint OpenAI-compatible: OpenRouter, Cerebras, Groq, vLLM..."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int,
        client=None,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._client = client or OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._backoff_seconds = backoff_seconds

    def complete(self, messages: list[dict[str, str]]) -> str:
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                )
                return completion.choices[0].message.content or ""
            except Exception as exc:  # provider nào cũng ném kiểu riêng
                last_error = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(self._backoff_seconds * (2**attempt))
        raise LLMError(f"Gọi LLM thất bại sau {MAX_ATTEMPTS} lần: {last_error}") from last_error
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_llm_client.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add api/
git commit -m "feat: LLM client OpenAI-compatible với retry"
```

---

### Task 6: Parser — LlamaParse qua REST

**Files:**
- Create: `api/app/core/parsing/__init__.py`, `api/app/core/parsing/base.py`, `api/app/core/parsing/llamaparse.py`
- Create: `api/tests/test_llamaparse.py`

**Interfaces:**
- Consumes: `app.config.Settings`.
- Produces:
  - `ParseResult(markdown: str, parser_name: str)` — dataclass.
  - Protocol `Parser` với `to_markdown(file_path: Path, mime_type: str | None = None) -> ParseResult`.
  - `LlamaParseParser(api_key: str, poll_interval_seconds: float = 2.0, max_wait_seconds: float = 600, transport=None)`.
  - Exception `ParserError`.

LlamaParse REST: `POST {BASE}/api/v1/parsing/upload` (multipart, trả `{"id": ...}`) → `GET {BASE}/api/v1/parsing/job/{id}` (trả `{"status": "SUCCESS"|"PENDING"|"ERROR"}`) → `GET {BASE}/api/v1/parsing/job/{id}/result/markdown` (trả `{"markdown": "..."}`). `BASE = https://api.cloud.llamaindex.ai`.

- [ ] **Step 1: Viết test (FAIL trước)**

File `api/tests/test_llamaparse.py`:

```python
from __future__ import annotations

import httpx
import pytest

from app.core.parsing.llamaparse import LlamaParseParser, ParserError


def build_parser(handler) -> LlamaParseParser:
    return LlamaParseParser(
        api_key="llx-test",
        poll_interval_seconds=0,
        max_wait_seconds=5,
        transport=httpx.MockTransport(handler),
    )


def test_parse_thanh_cong_tra_ve_markdown(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.headers["authorization"] == "Bearer llx-test"
        if request.url.path.endswith("/parsing/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        if request.url.path.endswith("/parsing/job/job-1"):
            return httpx.Response(200, json={"status": "SUCCESS"})
        if request.url.path.endswith("/result/markdown"):
            return httpx.Response(200, json={"markdown": "# Tiêu đề\n\nnội dung"})
        raise AssertionError(f"đường dẫn lạ: {request.url.path}")

    parser = build_parser(handler)

    result = parser.to_markdown(source, mime_type="application/pdf")

    assert result.markdown == "# Tiêu đề\n\nnội dung"
    assert result.parser_name == "llamaparse"
    assert any(p.endswith("/parsing/upload") for p in seen)


def test_parse_poll_qua_trang_thai_pending(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"x")
    statuses = ["PENDING", "PENDING", "SUCCESS"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/parsing/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        if request.url.path.endswith("/parsing/job/job-1"):
            return httpx.Response(200, json={"status": statuses.pop(0)})
        return httpx.Response(200, json={"markdown": "ok"})

    parser = build_parser(handler)

    assert parser.to_markdown(source).markdown == "ok"
    assert statuses == []


def test_parse_job_loi_thi_nem_parser_error(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/parsing/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(200, json={"status": "ERROR", "error_message": "file hỏng"})

    parser = build_parser(handler)

    with pytest.raises(ParserError, match="file hỏng"):
        parser.to_markdown(source)


def test_upload_loi_http_thi_nem_parser_error(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "sai key"})

    parser = build_parser(handler)

    with pytest.raises(ParserError):
        parser.to_markdown(source)
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_llamaparse.py -v
```

Expected: FAIL — `No module named 'app.core.parsing'`

- [ ] **Step 3: Viết `api/app/core/parsing/base.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParseResult:
    markdown: str
    parser_name: str


class Parser(Protocol):
    def to_markdown(self, file_path: Path, mime_type: str | None = None) -> ParseResult: ...
```

Tạo `api/app/core/parsing/__init__.py` rỗng.

- [ ] **Step 4: Viết `api/app/core/parsing/llamaparse.py`**

```python
from __future__ import annotations

import time
from pathlib import Path

import httpx

from app.core.parsing.base import ParseResult

LLAMA_CLOUD_BASE_URL = "https://api.cloud.llamaindex.ai"


class ParserError(Exception):
    """Chuyển file sang markdown thất bại."""


class LlamaParseParser:
    """Gọi LlamaParse qua REST, không dùng SDK để khỏi kéo llama-index-core."""

    parser_name = "llamaparse"

    def __init__(
        self,
        api_key: str,
        poll_interval_seconds: float = 2.0,
        max_wait_seconds: float = 600.0,
        base_url: str = LLAMA_CLOUD_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._max_wait_seconds = max_wait_seconds
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120.0,
            transport=transport,
        )

    def to_markdown(self, file_path: Path, mime_type: str | None = None) -> ParseResult:
        job_id = self._upload(file_path, mime_type)
        self._wait_for_job(job_id)
        markdown = self._fetch_markdown(job_id)
        return ParseResult(markdown=markdown, parser_name=self.parser_name)

    def _upload(self, file_path: Path, mime_type: str | None) -> str:
        with file_path.open("rb") as handle:
            files = {"file": (file_path.name, handle, mime_type or "application/octet-stream")}
            data = self._request("POST", "/api/v1/parsing/upload", files=files)
        job_id = data.get("id")
        if not job_id:
            raise ParserError(f"LlamaParse không trả job id: {data}")
        return job_id

    def _wait_for_job(self, job_id: str) -> None:
        deadline = time.monotonic() + self._max_wait_seconds
        while True:
            data = self._request("GET", f"/api/v1/parsing/job/{job_id}")
            status = data.get("status", "").upper()
            if status == "SUCCESS":
                return
            if status in {"ERROR", "FAILED", "CANCELED"}:
                raise ParserError(data.get("error_message") or f"Job {job_id} thất bại: {status}")
            if time.monotonic() > deadline:
                raise ParserError(f"Job {job_id} quá thời gian chờ {self._max_wait_seconds}s")
            time.sleep(self._poll_interval_seconds)

    def _fetch_markdown(self, job_id: str) -> str:
        data = self._request("GET", f"/api/v1/parsing/job/{job_id}/result/markdown")
        return data.get("markdown", "")

    def _request(self, method: str, path: str, files: dict | None = None) -> dict:
        try:
            response = self._client.request(method, path, files=files)
        except httpx.HTTPError as exc:
            raise ParserError(f"Không gọi được LlamaParse: {exc}") from exc
        if response.status_code >= 400:
            raise ParserError(f"LlamaParse trả về {response.status_code}: {response.text[:500]}")
        return response.json()
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_llamaparse.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add api/
git commit -m "feat: parser LlamaParse qua REST API"
```

---

### Task 7: CodeActAgent — vòng lặp reason → code → exec → observe

**Files:**
- Create: `api/app/core/agent/__init__.py`, `api/app/core/agent/prompts.py`, `api/app/core/agent/codeact.py`
- Create: `api/tests/test_codeact.py`

**Interfaces:**
- Consumes: `LLMClient` protocol, `ExecutionResult`.
- Produces:
  - `AgentStepRecord(step_index: int, code: str, stdout: str, stderr: str, status: str, duration_ms: int)` — dataclass.
  - `AgentRunResult(answer: str, steps: list[AgentStepRecord], hit_step_limit: bool)` — dataclass.
  - `CodeActAgent(llm: LLMClient, max_steps: int)` với
    `run(question: str, document_context: str, history: list[dict[str, str]], executor: Callable[[str], ExecutionResult]) -> AgentRunResult`.
  - `extract_code(text: str) -> str | None` — lấy block ```python đầu tiên.
  - `build_system_prompt() -> str`, `build_document_context(filename: str, char_count: int, head: str) -> str`.

Agent nhận `executor` là callable, không biết gì về sandbox hay DB — nhờ vậy test được bằng hàm thường.

- [ ] **Step 1: Viết test (FAIL trước)**

File `api/tests/test_codeact.py`:

```python
from __future__ import annotations

from app.core.agent.codeact import CodeActAgent, extract_code
from app.core.sandbox.models import ExecutionResult
from tests.fakes import FakeLLMClient

DOC_CONTEXT = "File: hsmt.pdf, 1000 ký tự"


def ok(stdout: str) -> ExecutionResult:
    return ExecutionResult(
        status="completed", stdout=stdout, stderr="", timed_out=False, duration_ms=5
    )


def test_extract_code_lay_block_python():
    text = "Tôi sẽ đọc file.\n\n```python\nprint(1)\n```\n\nXong."

    assert extract_code(text) == "print(1)"


def test_extract_code_tra_none_khi_khong_co_block():
    assert extract_code("Đây là câu trả lời cuối cùng.") is None


def test_agent_tra_loi_ngay_khi_llm_khong_sinh_code():
    llm = FakeLLMClient(responses=["Tài liệu nói về gói thầu số 33."])
    agent = CodeActAgent(llm=llm, max_steps=8)

    result = agent.run(
        question="Gói thầu số mấy?",
        document_context=DOC_CONTEXT,
        history=[],
        executor=lambda code: ok(""),
    )

    assert result.answer == "Tài liệu nói về gói thầu số 33."
    assert result.steps == []
    assert result.hit_step_limit is False


def test_agent_chay_code_roi_dua_stdout_vao_luot_ke_tiep():
    llm = FakeLLMClient(
        responses=[
            "Để tôi đếm.\n\n```python\nprint(len(open('document.md').read()))\n```",
            "Tài liệu dài 4200 ký tự.",
        ]
    )
    agent = CodeActAgent(llm=llm, max_steps=8)
    executed: list[str] = []

    def executor(code: str) -> ExecutionResult:
        executed.append(code)
        return ok("4200\n")

    result = agent.run(
        question="Tài liệu dài bao nhiêu?",
        document_context=DOC_CONTEXT,
        history=[],
        executor=executor,
    )

    assert executed == ["print(len(open('document.md').read()))"]
    assert result.answer == "Tài liệu dài 4200 ký tự."
    assert len(result.steps) == 1
    assert result.steps[0].stdout == "4200\n"
    assert result.steps[0].step_index == 0

    observation = llm.calls[1][-1]
    assert observation["role"] == "user"
    assert "4200" in observation["content"]


def test_agent_dua_stderr_vao_observation_de_tu_sua():
    llm = FakeLLMClient(
        responses=[
            "```python\nopen('sai.md')\n```",
            "```python\nopen('document.md')\n```",
            "Đã đọc được file.",
        ]
    )
    agent = CodeActAgent(llm=llm, max_steps=8)

    def executor(code: str) -> ExecutionResult:
        if "sai.md" in code:
            return ExecutionResult(
                status="failed",
                stdout="",
                stderr="FileNotFoundError: sai.md",
                timed_out=False,
                duration_ms=3,
            )
        return ok("ok")

    result = agent.run(
        question="Đọc file", document_context=DOC_CONTEXT, history=[], executor=executor
    )

    assert result.answer == "Đã đọc được file."
    assert len(result.steps) == 2
    assert result.steps[0].status == "failed"
    assert "FileNotFoundError" in llm.calls[1][-1]["content"]


def test_agent_dung_khi_cham_max_steps():
    llm = FakeLLMClient(responses=["```python\nprint(1)\n```"] * 3)
    agent = CodeActAgent(llm=llm, max_steps=3)

    result = agent.run(
        question="q", document_context=DOC_CONTEXT, history=[], executor=lambda code: ok("1")
    )

    assert result.hit_step_limit is True
    assert len(result.steps) == 3
    assert "chưa hoàn tất" in result.answer.lower()


def test_agent_nap_lich_su_hoi_thoai_vao_prompt():
    llm = FakeLLMClient(responses=["Câu trả lời."])
    agent = CodeActAgent(llm=llm, max_steps=8)
    history = [
        {"role": "user", "content": "Câu hỏi lượt trước"},
        {"role": "assistant", "content": "Trả lời lượt trước"},
    ]

    agent.run(
        question="Câu hỏi lượt này",
        document_context=DOC_CONTEXT,
        history=history,
        executor=lambda code: ok(""),
    )

    messages = llm.calls[0]
    assert messages[0]["role"] == "system"
    contents = [m["content"] for m in messages]
    assert "Câu hỏi lượt trước" in contents
    assert "Trả lời lượt trước" in contents
    assert contents.index("Câu hỏi lượt trước") < contents.index("Câu hỏi lượt này")
    assert messages[-1]["content"] == "Câu hỏi lượt này"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_codeact.py -v
```

Expected: FAIL — `No module named 'app.core.agent'`

- [ ] **Step 3: Viết `api/app/core/agent/prompts.py`**

```python
from __future__ import annotations

SYSTEM_PROMPT = """Bạn là trợ lý đọc hiểu tài liệu. Tài liệu đã được chuyển sang markdown và \
nằm tại `document.md` trong thư mục làm việc của một môi trường Python.

Bạn KHÔNG được nhìn thấy toàn bộ nội dung tài liệu. Cách làm việc của bạn là viết code Python \
để tự tìm phần mình cần: đọc file, tìm chuỗi, cắt đoạn, đếm, lọc bảng.

Quy tắc:
- Khi cần xem dữ liệu, trả lời bằng đúng một block ```python. Code sẽ được chạy và bạn nhận lại \
stdout/stderr ở lượt sau.
- Biến và import được giữ nguyên giữa các lần chạy, không cần đọc lại file mỗi lượt.
- In ra vừa đủ để suy luận. Đừng in cả tài liệu.
- Khi đã đủ thông tin, trả lời bằng tiếng Việt, KHÔNG kèm block code nào.
- Nếu code lỗi, đọc stderr rồi sửa ở lượt tiếp theo.
"""

STEP_LIMIT_NOTICE = (
    "\n\n(Lưu ý: agent đã chạm giới hạn số bước nên phần tìm hiểu chưa hoàn tất. "
    "Câu trả lời trên dựa vào những gì thu thập được cho tới lúc dừng.)"
)


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_document_context(filename: str, char_count: int, head: str) -> str:
    return (
        f"Tài liệu đang xét: `{filename}`, đã chuyển sang markdown, dài {char_count} ký tự, "
        f"đọc được tại `document.md`.\n\n"
        f"Phần đầu tài liệu:\n\n{head}"
    )


def build_observation(stdout: str, stderr: str, timed_out: bool) -> str:
    parts = [f"Kết quả chạy code:\n\nstdout:\n{stdout or '(rỗng)'}"]
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    if timed_out:
        parts.append("Code đã chạy quá thời gian cho phép và bị dừng.")
    return "\n\n".join(parts)
```

- [ ] **Step 4: Viết `api/app/core/agent/codeact.py`**

```python
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.agent.prompts import (
    STEP_LIMIT_NOTICE,
    build_observation,
    build_system_prompt,
)
from app.core.llm.base import LLMClient
from app.core.sandbox.models import ExecutionResult

CODE_BLOCK_PATTERN = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class AgentStepRecord:
    step_index: int
    code: str
    stdout: str
    stderr: str
    status: str
    duration_ms: int


@dataclass
class AgentRunResult:
    answer: str
    steps: list[AgentStepRecord] = field(default_factory=list)
    hit_step_limit: bool = False


def extract_code(text: str) -> str | None:
    match = CODE_BLOCK_PATTERN.search(text)
    if match is None:
        return None
    code = match.group(1).strip()
    return code or None


class CodeActAgent:
    def __init__(self, llm: LLMClient, max_steps: int) -> None:
        self._llm = llm
        self._max_steps = max_steps

    def run(
        self,
        question: str,
        document_context: str,
        history: list[dict[str, str]],
        executor: Callable[[str], ExecutionResult],
    ) -> AgentRunResult:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "system", "content": document_context},
            *[{"role": m["role"], "content": m["content"]} for m in history],
            {"role": "user", "content": question},
        ]

        steps: list[AgentStepRecord] = []
        last_text = ""

        for step_index in range(self._max_steps):
            last_text = self._llm.complete(messages)
            code = extract_code(last_text)

            if code is None:
                return AgentRunResult(answer=last_text, steps=steps, hit_step_limit=False)

            result = executor(code)
            steps.append(
                AgentStepRecord(
                    step_index=step_index,
                    code=code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    status=result.status,
                    duration_ms=result.duration_ms,
                )
            )
            messages.append({"role": "assistant", "content": last_text})
            messages.append(
                {
                    "role": "user",
                    "content": build_observation(result.stdout, result.stderr, result.timed_out),
                }
            )

        return AgentRunResult(
            answer=self._summarise_on_limit(last_text),
            steps=steps,
            hit_step_limit=True,
        )

    def _summarise_on_limit(self, last_text: str) -> str:
        stripped = CODE_BLOCK_PATTERN.sub("", last_text).strip()
        base = stripped or "Chưa tìm ra câu trả lời trong giới hạn số bước cho phép."
        return base + STEP_LIMIT_NOTICE
```

Tạo `api/app/core/agent/__init__.py` rỗng.

- [ ] **Step 5: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_codeact.py -v
```

Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add api/
git commit -m "feat: CodeActAgent với vòng lặp reason-code-observe"
```

---

### Task 8: API documents — upload và parse nền

**Files:**
- Create: `api/app/core/parsing/pipeline.py`
- Create: `api/app/api/schemas.py`, `api/app/api/documents.py`
- Create: `api/app/dependencies.py`
- Modify: `api/app/main.py`
- Create: `api/tests/test_documents_api.py`

**Interfaces:**
- Consumes: `Document`, `DocumentArtifact`, `Parser` protocol, `ParserError`, `get_db`, `get_settings`.
- Produces:
  - `app.core.parsing.pipeline.parse_document(document_id: int, session_factory, parser: Parser, artifacts_dir: Path) -> None` — job nền, tự mở session DB riêng.
  - `app.core.parsing.pipeline.read_markdown(document: Document) -> str` — đọc markdown artifact mới nhất, ném `ValueError` nếu chưa có.
  - `app.dependencies.get_parser()`, `get_sandbox_client()`, `get_llm_client()` — FastAPI dependency, ghi đè được trong test bằng `app.dependency_overrides`.
  - Routes: `POST /documents` (multipart `file`), `GET /documents`, `GET /documents/{id}`.
  - Schema `DocumentOut(id, filename, mime_type, parse_status, parse_error, char_count)`.

- [ ] **Step 1: Viết test (FAIL trước)**

File `api/tests/test_documents_api.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.parsing.base import ParseResult
from app.core.parsing.llamaparse import ParserError
from app.db.models import Document
from app.dependencies import get_parser
from app.db.session import get_db
from app.main import create_app


class FakeParser:
    def __init__(self, markdown: str = "# Nội dung", error: Exception | None = None) -> None:
        self.markdown = markdown
        self.error = error
        self.calls: list[Path] = []

    def to_markdown(self, file_path: Path, mime_type: str | None = None) -> ParseResult:
        self.calls.append(file_path)
        if self.error:
            raise self.error
        return ParseResult(markdown=self.markdown, parser_name="fake")


@pytest.fixture
def client(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    parser = FakeParser()
    app.dependency_overrides[get_parser] = lambda: parser

    test_client = TestClient(app)
    test_client.fake_parser = parser
    yield test_client

    get_settings.cache_clear()


def test_upload_tra_ve_document_id_va_trang_thai_ready_sau_khi_parse(client, db_session):
    response = client.post(
        "/documents",
        files={"file": ("hsmt.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "hsmt.pdf"

    # TestClient chạy BackgroundTasks đồng bộ sau khi response trả về
    doc = db_session.get(Document, body["id"])
    db_session.refresh(doc)
    assert doc.parse_status == "ready"
    assert doc.artifacts[0].kind == "markdown"
    assert Path(doc.artifacts[0].content_path).read_text() == "# Nội dung"


def test_parse_that_bai_ghi_trang_thai_failed(client, db_session):
    client.fake_parser.error = ParserError("file hỏng")

    response = client.post(
        "/documents", files={"file": ("a.pdf", b"x", "application/pdf")}
    )
    doc_id = response.json()["id"]

    doc = db_session.get(Document, doc_id)
    db_session.refresh(doc)
    assert doc.parse_status == "failed"
    assert "file hỏng" in doc.parse_error


def test_get_document_tra_ve_trang_thai(client):
    doc_id = client.post(
        "/documents", files={"file": ("a.pdf", b"x", "application/pdf")}
    ).json()["id"]

    response = client.get(f"/documents/{doc_id}")

    assert response.status_code == 200
    assert response.json()["parse_status"] == "ready"
    assert response.json()["char_count"] == len("# Nội dung")


def test_get_document_khong_ton_tai_tra_404(client):
    assert client.get("/documents/9999").status_code == 404


def test_list_documents_tra_ve_danh_sach(client):
    client.post("/documents", files={"file": ("a.pdf", b"x", "application/pdf")})
    client.post("/documents", files={"file": ("b.pdf", b"y", "application/pdf")})

    response = client.get("/documents")

    assert response.status_code == 200
    assert {d["filename"] for d in response.json()} == {"a.pdf", "b.pdf"}
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_documents_api.py -v
```

Expected: FAIL — `No module named 'app.dependencies'`

- [ ] **Step 3: Viết `api/app/dependencies.py`**

```python
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.core.llm.openai_compat import OpenAICompatibleClient
from app.core.parsing.llamaparse import LlamaParseParser
from app.core.sandbox.client import HttpSandboxClient


@lru_cache(maxsize=1)
def _parser() -> LlamaParseParser:
    return LlamaParseParser(api_key=get_settings().llama_cloud_api_key)


@lru_cache(maxsize=1)
def _sandbox_client() -> HttpSandboxClient:
    settings = get_settings()
    return HttpSandboxClient(
        base_url=settings.sandbox_base_url,
        api_key=settings.sandbox_api_key,
        timeout_seconds=settings.sandbox_timeout_seconds,
    )


@lru_cache(maxsize=1)
def _llm_client() -> OpenAICompatibleClient:
    settings = get_settings()
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
    )


def get_parser() -> LlamaParseParser:
    return _parser()


def get_sandbox_client() -> HttpSandboxClient:
    return _sandbox_client()


def get_llm_client() -> OpenAICompatibleClient:
    return _llm_client()
```

- [ ] **Step 4: Viết `api/app/core/parsing/pipeline.py`**

```python
from __future__ import annotations

from pathlib import Path

from app.core.parsing.base import Parser
from app.db.models import Document, DocumentArtifact


def parse_document(
    document_id: int,
    session_factory,
    parser: Parser,
    artifacts_dir: Path,
) -> None:
    """Job nền: chuyển file sang markdown rồi ghi artifact.

    Mở session DB riêng vì chạy sau khi request đã trả về.
    """
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.parse_status = "parsing"
        db.commit()

        try:
            result = parser.to_markdown(Path(document.source_path), document.mime_type)
        except Exception as exc:
            document.parse_status = "failed"
            document.parse_error = str(exc)[:2000]
            db.commit()
            return

        artifacts_dir.mkdir(parents=True, exist_ok=True)
        target = artifacts_dir / f"{document_id}.md"
        target.write_text(result.markdown)

        db.add(
            DocumentArtifact(
                document_id=document.id,
                kind="markdown",
                content_path=str(target),
                char_count=len(result.markdown),
                parser_name=result.parser_name,
            )
        )
        document.parse_status = "ready"
        document.parse_error = None
        db.commit()


def read_markdown(document: Document) -> str:
    artifacts = [a for a in document.artifacts if a.kind == "markdown"]
    if not artifacts:
        raise ValueError(f"Tài liệu {document.id} chưa có artifact markdown")
    latest = max(artifacts, key=lambda a: a.id)
    return Path(latest.content_path).read_text()
```

- [ ] **Step 5: Viết `api/app/api/schemas.py`**

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    parse_status: str
    parse_error: str | None = None
    char_count: int = 0


class ConversationCreate(BaseModel):
    document_id: int
    title: str | None = None


class ConversationOut(BaseModel):
    id: int
    document_id: int
    title: str
    sandbox_session_id: str | None = None


class AgentStepOut(BaseModel):
    step_index: int
    code: str
    stdout: str
    stderr: str
    status: str
    duration_ms: int


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    steps: list[AgentStepOut] = []


class MessageCreate(BaseModel):
    content: str
```

- [ ] **Step 6: Viết `api/app/api/documents.py`**

```python
from __future__ import annotations

import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import DocumentOut
from app.config import get_settings
from app.core.parsing.base import Parser
from app.core.parsing.pipeline import parse_document
from app.db.models import Document
from app.db.session import get_db, get_session_factory
from app.dependencies import get_parser

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_out(document: Document) -> DocumentOut:
    markdown = [a for a in document.artifacts if a.kind == "markdown"]
    return DocumentOut(
        id=document.id,
        filename=document.filename,
        mime_type=document.mime_type,
        parse_status=document.parse_status,
        parse_error=document.parse_error,
        char_count=max((a.char_count for a in markdown), default=0),
    )


@router.post("", status_code=201, response_model=DocumentOut)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    parser: Parser = Depends(get_parser),
) -> DocumentOut:
    settings = get_settings()

    document = Document(
        filename=file.filename or "unnamed",
        mime_type=file.content_type or "application/octet-stream",
        source_path="",
    )
    db.add(document)
    db.flush()

    target_dir = settings.uploads_dir / str(document.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / document.filename
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    document.source_path = str(target)
    document.size_bytes = target.stat().st_size
    db.commit()

    background_tasks.add_task(
        parse_document,
        document_id=document.id,
        session_factory=get_session_factory(),
        parser=parser,
        artifacts_dir=settings.artifacts_dir,
    )
    return _to_out(document)


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    documents = db.scalars(select(Document).order_by(Document.id.desc())).all()
    return [_to_out(d) for d in documents]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)) -> DocumentOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    db.refresh(document)
    return _to_out(document)
```

- [ ] **Step 7: Đăng ký router trong `api/app/main.py`**

```python
from __future__ import annotations

from fastapi import FastAPI

from app.api import documents, health


def create_app() -> FastAPI:
    app = FastAPI(title="File Understanding API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(documents.router)
    return app


app = create_app()
```

- [ ] **Step 8: Sửa test để job nền dùng chung session của test**

Trong `parse_document`, `session_factory` được truyền vào — test override bằng cách patch `get_session_factory`. Thêm vào `api/tests/test_documents_api.py`, ngay trong fixture `client`, sau dòng `app.dependency_overrides[get_parser] = lambda: parser`:

```python
    from contextlib import contextmanager

    import app.api.documents as documents_module

    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(
        documents_module, "get_session_factory", lambda: fake_session_scope
    )
```

- [ ] **Step 9: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_documents_api.py -v
```

Expected: 5 passed

- [ ] **Step 10: Commit**

```bash
git add api/
git commit -m "feat: API upload tài liệu và parse nền sang markdown"
```

---

### Task 9: API hội thoại và chat multi-turn

**Files:**
- Create: `api/app/core/chat_service.py`
- Create: `api/app/api/conversations.py`
- Modify: `api/app/main.py`
- Create: `api/tests/test_chat_api.py`
- Create: `api/tests/test_multi_turn.py`

**Interfaces:**
- Consumes: `CodeActAgent`, `SessionResolver`, `read_markdown`, `build_document_context`, `LLMClient`, `SandboxClient`, schemas ở Task 8.
- Produces:
  - `ChatService(db: Session, llm: LLMClient, sandbox: SandboxClient, max_steps: int)` với `answer(conversation: Conversation, question: str) -> Message`.
  - `ChatService.build_history(conversation: Conversation) -> list[dict[str, str]]` — lịch sử theo `(created_at, id)` tăng dần, chỉ lấy role `user`/`assistant`.
  - Routes: `POST /conversations`, `GET /conversations`, `GET /conversations/{id}/messages`, `POST /conversations/{id}/messages`, `POST /conversations/{id}/reset-sandbox`, `DELETE /conversations/{id}`.

**Đây là task then chốt của cả plan** — tiêu chí thành công số một là multi-turn đúng.

- [ ] **Step 1: Viết test chat API (FAIL trước)**

File `api/tests/test_chat_api.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.models import Conversation, Document, DocumentArtifact
from app.db.session import get_db
from app.dependencies import get_llm_client, get_sandbox_client
from app.main import create_app
from tests.fakes import FakeLLMClient, FakeSandboxClient


@pytest.fixture
def document(db_session, tmp_path):
    markdown_path = tmp_path / "1.md"
    markdown_path.write_text("# Gói thầu 33\n\nGiá gói thầu: 5 tỷ.")
    doc = Document(
        filename="hsmt.pdf",
        mime_type="application/pdf",
        source_path=str(tmp_path / "hsmt.pdf"),
        parse_status="ready",
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(
        DocumentArtifact(
            document_id=doc.id,
            kind="markdown",
            content_path=str(markdown_path),
            char_count=len(markdown_path.read_text()),
            parser_name="fake",
        )
    )
    db_session.flush()
    return doc


@pytest.fixture
def client(db_session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    llm = FakeLLMClient()
    sandbox = FakeSandboxClient()
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_sandbox_client] = lambda: sandbox

    test_client = TestClient(app)
    test_client.fake_llm = llm
    test_client.fake_sandbox = sandbox
    return test_client


def test_tao_conversation(client, document):
    response = client.post("/conversations", json={"document_id": document.id})

    assert response.status_code == 201
    assert response.json()["document_id"] == document.id
    assert response.json()["sandbox_session_id"] is None


def test_tao_conversation_voi_tai_lieu_chua_parse_xong_tra_409(client, db_session):
    doc = Document(
        filename="x.pdf", mime_type="application/pdf", source_path="/x", parse_status="pending"
    )
    db_session.add(doc)
    db_session.flush()

    response = client.post("/conversations", json={"document_id": doc.id})

    assert response.status_code == 409


def test_gui_cau_hoi_tra_ve_cau_tra_loi_va_cac_buoc(client, document):
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = [
        "```python\nprint(open('document.md').read()[:20])\n```",
        "Giá gói thầu là 5 tỷ.",
    ]
    client.fake_sandbox.stdout_queue = ["# Gói thầu 33\n"]

    response = client.post(f"/conversations/{conv_id}/messages", json={"content": "Giá bao nhiêu?"})

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"] == "Giá gói thầu là 5 tỷ."
    assert len(body["steps"]) == 1
    assert body["steps"][0]["stdout"] == "# Gói thầu 33\n"


def test_lich_su_message_duoc_luu_dung_thu_tu(client, document):
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = ["Trả lời 1"]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi 1"})

    response = client.get(f"/conversations/{conv_id}/messages")

    assert [m["role"] for m in response.json()] == ["user", "assistant"]
    assert [m["content"] for m in response.json()] == ["Hỏi 1", "Trả lời 1"]


def test_cau_hoi_van_duoc_luu_khi_agent_loi(client, document):
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = []  # FakeLLMClient sẽ ném AssertionError

    with pytest.raises(AssertionError):
        client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi lỗi"})

    messages = client.get(f"/conversations/{conv_id}/messages").json()
    assert [m["content"] for m in messages] == ["Hỏi lỗi"]


def test_reset_sandbox_dong_session(client, document):
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = ["```python\nprint(1)\n```", "xong"]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "q"})

    response = client.post(f"/conversations/{conv_id}/reset-sandbox")

    assert response.status_code == 204
    assert client.fake_sandbox.closed_sessions == ["sess_1"]


def test_xoa_conversation_dong_session(client, document):
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = ["```python\nprint(1)\n```", "xong"]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "q"})

    response = client.delete(f"/conversations/{conv_id}")

    assert response.status_code == 204
    assert client.fake_sandbox.closed_sessions == ["sess_1"]
```

- [ ] **Step 2: Viết test multi-turn (FAIL trước)**

File `api/tests/test_multi_turn.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.models import Document, DocumentArtifact
from app.db.session import get_db
from app.dependencies import get_llm_client, get_sandbox_client
from app.main import create_app
from tests.fakes import FakeLLMClient, FakeSandboxClient


@pytest.fixture
def client_and_doc(db_session, tmp_path):
    markdown_path = tmp_path / "doc.md"
    markdown_path.write_text("# Tài liệu thử")
    doc = Document(
        filename="a.pdf", mime_type="application/pdf", source_path="/x", parse_status="ready"
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(
        DocumentArtifact(
            document_id=doc.id,
            kind="markdown",
            content_path=str(markdown_path),
            char_count=13,
            parser_name="fake",
        )
    )
    db_session.flush()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    llm = FakeLLMClient()
    sandbox = FakeSandboxClient()
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_sandbox_client] = lambda: sandbox

    client = TestClient(app)
    client.fake_llm = llm
    client.fake_sandbox = sandbox
    return client, doc


def test_hai_luot_dung_lai_dung_mot_sandbox_session(client_and_doc):
    client, doc = client_and_doc
    conv_id = client.post("/conversations", json={"document_id": doc.id}).json()["id"]

    client.fake_llm.responses = ["```python\nx = 1\nprint(x)\n```", "Đã gán x = 1."]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "Gán x bằng 1"})

    client.fake_llm.responses = ["```python\nprint(x + 1)\n```", "x + 1 bằng 2."]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "x cộng 1 bằng mấy?"})

    assert len(client.fake_sandbox.created_sessions) == 1
    assert [session_id for session_id, _ in client.fake_sandbox.executed] == ["sess_1", "sess_1"]


def test_luot_hai_nhan_du_lich_su_luot_mot_dung_thu_tu(client_and_doc):
    client, doc = client_and_doc
    conv_id = client.post("/conversations", json={"document_id": doc.id}).json()["id"]

    client.fake_llm.responses = ["Gói thầu số 33."]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "Gói thầu số mấy?"})

    client.fake_llm.responses = ["Giá là 5 tỷ."]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "Còn giá thì sao?"})

    messages = client.fake_llm.calls[-1]
    contents = [m["content"] for m in messages]

    assert "Gói thầu số mấy?" in contents
    assert "Gói thầu số 33." in contents
    assert "Còn giá thì sao?" in contents
    assert contents.index("Gói thầu số mấy?") < contents.index("Gói thầu số 33.")
    assert contents.index("Gói thầu số 33.") < contents.index("Còn giá thì sao?")
    assert messages[-1]["content"] == "Còn giá thì sao?"


def test_lich_su_khong_chua_lai_cac_buoc_code_cua_luot_truoc(client_and_doc):
    client, doc = client_and_doc
    conv_id = client.post("/conversations", json={"document_id": doc.id}).json()["id"]

    client.fake_llm.responses = ["```python\nprint('bí mật nội bộ')\n```", "Trả lời 1."]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi 1"})

    client.fake_llm.responses = ["Trả lời 2."]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi 2"})

    contents = " ".join(m["content"] for m in client.fake_llm.calls[-1])
    assert "bí mật nội bộ" not in contents
    assert "Trả lời 1." in contents


def test_session_bi_reap_giua_hai_luot_thi_tu_tao_lai(client_and_doc):
    client, doc = client_and_doc
    conv_id = client.post("/conversations", json={"document_id": doc.id}).json()["id"]

    client.fake_llm.responses = ["```python\nprint(1)\n```", "Xong lượt 1."]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi 1"})

    client.fake_sandbox.dead_sessions.add("sess_1")

    client.fake_llm.responses = ["```python\nprint(2)\n```", "Xong lượt 2."]
    response = client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi 2"})

    assert response.status_code == 200
    assert response.json()["content"] == "Xong lượt 2."
    assert len(client.fake_sandbox.created_sessions) == 2
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_chat_api.py tests/test_multi_turn.py -v
```

Expected: FAIL — `No module named 'app.core.chat_service'`

- [ ] **Step 4: Viết `api/app/core/chat_service.py`**

```python
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.agent.codeact import CodeActAgent
from app.core.agent.prompts import build_document_context
from app.core.llm.base import LLMClient
from app.core.parsing.pipeline import read_markdown
from app.core.sandbox.base import SandboxClient
from app.core.sandbox.resolver import SessionResolver
from app.db.models import AgentStep, Conversation, Message

DOCUMENT_HEAD_LINES = 30


class ChatService:
    """Ghép lịch sử hội thoại, sandbox session và agent thành một lượt trả lời."""

    def __init__(self, db: Session, llm: LLMClient, sandbox: SandboxClient, max_steps: int) -> None:
        self._db = db
        self._resolver = SessionResolver(client=sandbox, db=db)
        self._agent = CodeActAgent(llm=llm, max_steps=max_steps)

    def build_history(self, conversation: Conversation) -> list[dict[str, str]]:
        return [
            {"role": m.role, "content": m.content}
            for m in conversation.messages
            if m.role in {"user", "assistant"}
        ]

    def answer(self, conversation: Conversation, question: str) -> Message:
        markdown = read_markdown(conversation.document)

        # Lịch sử phải chụp TRƯỚC khi thêm câu hỏi mới, vì agent tự nối câu hỏi ở cuối.
        history = self.build_history(conversation)

        user_message = Message(conversation_id=conversation.id, role="user", content=question)
        self._db.add(user_message)
        self._db.commit()
        self._db.refresh(conversation)

        document_context = build_document_context(
            filename=conversation.document.filename,
            char_count=len(markdown),
            head="\n".join(markdown.splitlines()[:DOCUMENT_HEAD_LINES]),
        )

        result = self._agent.run(
            question=question,
            document_context=document_context,
            history=history,
            executor=lambda code: self._resolver.run_code(conversation, markdown, code),
        )

        assistant_message = Message(
            conversation_id=conversation.id, role="assistant", content=result.answer
        )
        self._db.add(assistant_message)
        self._db.flush()

        for step in result.steps:
            self._db.add(
                AgentStep(
                    message_id=assistant_message.id,
                    step_index=step.step_index,
                    code=step.code,
                    stdout=step.stdout,
                    stderr=step.stderr,
                    status=step.status,
                    duration_ms=step.duration_ms,
                )
            )
        self._db.commit()
        self._db.refresh(assistant_message)
        return assistant_message

    def reset_sandbox(self, conversation: Conversation) -> None:
        self._resolver.reset(conversation)
        self._db.commit()
```

- [ ] **Step 5: Viết `api/app/api/conversations.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AgentStepOut,
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
)
from app.config import get_settings
from app.core.chat_service import ChatService
from app.core.llm.base import LLMClient
from app.core.llm.openai_compat import LLMError
from app.core.sandbox.base import SandboxClient
from app.core.sandbox.exceptions import SandboxCapacityError, SandboxError
from app.db.models import Conversation, Document
from app.db.session import get_db
from app.dependencies import get_llm_client, get_sandbox_client

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _to_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        document_id=conversation.document_id,
        title=conversation.title,
        sandbox_session_id=conversation.sandbox_session_id,
    )


def _message_out(message) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        steps=[
            AgentStepOut(
                step_index=s.step_index,
                code=s.code,
                stdout=s.stdout,
                stderr=s.stderr,
                status=s.status,
                duration_ms=s.duration_ms,
            )
            for s in message.steps
        ],
    )


def _get_conversation(conversation_id: int, db: Session) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    return conversation


def _build_service(
    db: Session, llm: LLMClient, sandbox: SandboxClient
) -> ChatService:
    return ChatService(db=db, llm=llm, sandbox=sandbox, max_steps=get_settings().agent_max_steps)


@router.post("", status_code=201, response_model=ConversationOut)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> ConversationOut:
    document = db.get(Document, payload.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if document.parse_status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Tài liệu chưa sẵn sàng (trạng thái: {document.parse_status})",
        )

    conversation = Conversation(
        document_id=document.id, title=payload.title or f"Hỏi đáp — {document.filename}"
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _to_out(conversation)


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    document_id: int | None = None, db: Session = Depends(get_db)
) -> list[ConversationOut]:
    statement = select(Conversation).order_by(Conversation.id.desc())
    if document_id is not None:
        statement = statement.where(Conversation.document_id == document_id)
    return [_to_out(c) for c in db.scalars(statement).all()]


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: int, db: Session = Depends(get_db)) -> list[MessageOut]:
    conversation = _get_conversation(conversation_id, db)
    return [_message_out(m) for m in conversation.messages]


@router.post("/{conversation_id}/messages", response_model=MessageOut)
def post_message(
    conversation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> MessageOut:
    conversation = _get_conversation(conversation_id, db)
    service = _build_service(db, llm, sandbox)

    try:
        message = service.answer(conversation, payload.content)
    except SandboxCapacityError as exc:
        raise HTTPException(status_code=503, detail=f"Sandbox quá tải: {exc}") from exc
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=f"Sandbox không dùng được: {exc}") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Lỗi gọi LLM: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _message_out(message)


@router.post("/{conversation_id}/reset-sandbox", status_code=204, response_class=Response)
def reset_sandbox(
    conversation_id: int,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> Response:
    conversation = _get_conversation(conversation_id, db)
    _build_service(db, llm, sandbox).reset_sandbox(conversation)
    return Response(status_code=204)


@router.delete("/{conversation_id}", status_code=204, response_class=Response)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> Response:
    conversation = _get_conversation(conversation_id, db)
    _build_service(db, llm, sandbox).reset_sandbox(conversation)
    db.delete(conversation)
    db.commit()
    return Response(status_code=204)
```

- [ ] **Step 6: Đăng ký router trong `api/app/main.py`**

```python
from __future__ import annotations

from fastapi import FastAPI

from app.api import conversations, documents, health


def create_app() -> FastAPI:
    app = FastAPI(title="File Understanding API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(conversations.router)
    return app


app = create_app()
```

- [ ] **Step 7: Chạy test, xác nhận PASS**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest tests/test_chat_api.py tests/test_multi_turn.py -v
```

Expected: 11 passed

- [ ] **Step 8: Chạy toàn bộ test**

```bash
cd api && /Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -v -m "not integration"
```

Expected: tất cả pass

- [ ] **Step 9: Commit**

```bash
git add api/
git commit -m "feat: API hội thoại và chat multi-turn qua CodeAct"
```

---

### Task 10: UI Streamlit

**Files:**
- Create: `ui/__init__.py`, `ui/api_client.py`, `ui/app.py`
- Create: `ui/tests/__init__.py`, `ui/tests/test_api_client.py`
- Modify: `pyproject.toml` (thêm `ui` vào `testpaths`)

**Interfaces:**
- Consumes: HTTP API ở Task 8 và 9.
- Produces: `ui.api_client.ApiClient(base_url: str, transport=None)` với `health() -> bool`, `upload_document(name, data, mime) -> dict`, `list_documents() -> list[dict]`, `get_document(doc_id) -> dict`, `create_conversation(document_id) -> dict`, `list_conversations(document_id) -> list[dict]`, `list_messages(conversation_id) -> list[dict]`, `send_message(conversation_id, content) -> dict`, `reset_sandbox(conversation_id) -> None`.

- [ ] **Step 1: Cho pytest thấy thư mục `ui`**

Sửa `[tool.pytest.ini_options]` trong `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["api/tests", "ui/tests"]
pythonpath = ["api", "."]
markers = [
    "integration: test cần compose và python-vm đang chạy thật",
]
```

Từ đây pytest chạy ở thư mục gốc repo:

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -m "not integration"
```

- [ ] **Step 2: Viết test cho ApiClient (FAIL trước)**

File `ui/tests/test_api_client.py`:

```python
from __future__ import annotations

import httpx
import pytest

from ui.api_client import ApiClient, ApiError


def build_client(handler) -> ApiClient:
    return ApiClient(base_url="http://api.test", transport=httpx.MockTransport(handler))


def test_health_tra_true_khi_api_song():
    client = build_client(lambda r: httpx.Response(200, json={"status": "ok"}))

    assert client.health() is True


def test_health_tra_false_khi_khong_ket_noi_duoc():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert build_client(handler).health() is False


def test_upload_document_gui_multipart():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.read()
        return httpx.Response(201, json={"id": 7, "filename": "a.pdf"})

    result = build_client(handler).upload_document("a.pdf", b"data", "application/pdf")

    assert result["id"] == 7
    assert captured["path"] == "/documents"
    assert b"a.pdf" in captured["body"]


def test_send_message_tra_ve_message():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/conversations/3/messages"
        return httpx.Response(200, json={"id": 9, "role": "assistant", "content": "ok", "steps": []})

    result = build_client(handler).send_message(3, "câu hỏi")

    assert result["content"] == "ok"


def test_loi_http_nem_api_error_kem_thong_diep():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "Sandbox không dùng được"})

    with pytest.raises(ApiError, match="Sandbox không dùng được"):
        build_client(handler).send_message(1, "q")
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest ui/tests -v
```

Expected: FAIL — `No module named 'ui.api_client'`

- [ ] **Step 4: Viết `ui/api_client.py`**

```python
from __future__ import annotations

import httpx


class ApiError(Exception):
    """API trả về lỗi hoặc không gọi được."""


class ApiClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=600.0, transport=transport
        )

    def health(self) -> bool:
        try:
            return self._client.get("/health").status_code == 200
        except httpx.HTTPError:
            return False

    def upload_document(self, name: str, data: bytes, mime: str) -> dict:
        return self._request("POST", "/documents", files={"file": (name, data, mime)})

    def list_documents(self) -> list[dict]:
        return self._request("GET", "/documents")

    def get_document(self, document_id: int) -> dict:
        return self._request("GET", f"/documents/{document_id}")

    def create_conversation(self, document_id: int) -> dict:
        return self._request("POST", "/conversations", json={"document_id": document_id})

    def list_conversations(self, document_id: int) -> list[dict]:
        return self._request("GET", "/conversations", params={"document_id": document_id})

    def list_messages(self, conversation_id: int) -> list[dict]:
        return self._request("GET", f"/conversations/{conversation_id}/messages")

    def send_message(self, conversation_id: int, content: str) -> dict:
        return self._request(
            "POST", f"/conversations/{conversation_id}/messages", json={"content": content}
        )

    def reset_sandbox(self, conversation_id: int) -> None:
        self._request("POST", f"/conversations/{conversation_id}/reset-sandbox")

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"Không gọi được API: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
            raise ApiError(str(detail))

        if not response.content:
            return None
        return response.json()
```

Tạo `ui/__init__.py` và `ui/tests/__init__.py` rỗng.

- [ ] **Step 5: Chạy test, xác nhận PASS**

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest ui/tests -v
```

Expected: 5 passed

- [ ] **Step 6: Viết `ui/app.py`**

```python
from __future__ import annotations

import os
import time

import streamlit as st

from ui.api_client import ApiClient, ApiError

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
POLL_INTERVAL_SECONDS = 3


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient(base_url=API_BASE_URL)


def render_sidebar(client: ApiClient) -> int | None:
    st.sidebar.title("Tài liệu")

    uploaded = st.sidebar.file_uploader("Tải tài liệu lên", type=None)
    if uploaded is not None and st.sidebar.button("Bắt đầu bóc tách"):
        document = client.upload_document(
            uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream"
        )
        st.session_state["pending_document_id"] = document["id"]
        st.rerun()

    pending_id = st.session_state.get("pending_document_id")
    if pending_id:
        document = client.get_document(pending_id)
        if document["parse_status"] in {"pending", "parsing"}:
            st.sidebar.info(f"Đang bóc tách `{document['filename']}`...")
            time.sleep(POLL_INTERVAL_SECONDS)
            st.rerun()
        else:
            st.session_state.pop("pending_document_id")
            if document["parse_status"] == "failed":
                st.sidebar.error(f"Bóc tách thất bại: {document['parse_error']}")
            st.rerun()

    documents = [d for d in client.list_documents() if d["parse_status"] == "ready"]
    if not documents:
        st.sidebar.warning("Chưa có tài liệu nào sẵn sàng.")
        return None

    labels = {d["id"]: f"{d['filename']} ({d['char_count']} ký tự)" for d in documents}
    document_id = st.sidebar.selectbox(
        "Chọn tài liệu", options=list(labels), format_func=lambda i: labels[i]
    )

    st.sidebar.divider()
    st.sidebar.subheader("Hội thoại")

    conversations = client.list_conversations(document_id)
    if st.sidebar.button("Tạo hội thoại mới"):
        conversation = client.create_conversation(document_id)
        st.session_state["conversation_id"] = conversation["id"]
        st.rerun()

    if not conversations:
        st.sidebar.caption("Chưa có hội thoại nào cho tài liệu này.")
        return None

    conversation_labels = {c["id"]: f"#{c['id']} — {c['title']}" for c in conversations}
    conversation_id = st.sidebar.selectbox(
        "Chọn hội thoại",
        options=list(conversation_labels),
        format_func=lambda i: conversation_labels[i],
    )

    if st.sidebar.button("Reset phiên phân tích"):
        client.reset_sandbox(conversation_id)
        st.sidebar.success("Đã reset sandbox cho hội thoại này.")

    return conversation_id


def render_steps(steps: list[dict]) -> None:
    if not steps:
        return
    with st.expander(f"Các bước agent đã chạy ({len(steps)})"):
        for step in steps:
            st.markdown(f"**Bước {step['step_index'] + 1}** — {step['status']}, {step['duration_ms']}ms")
            st.code(step["code"], language="python")
            if step["stdout"]:
                st.text(step["stdout"])
            if step["stderr"]:
                st.error(step["stderr"])


def main() -> None:
    st.set_page_config(page_title="Hỏi đáp tài liệu", layout="wide")
    client = get_client()

    if not client.health():
        st.error(f"Không kết nối được tới API tại {API_BASE_URL}")
        return

    conversation_id = render_sidebar(client)
    st.title("Hỏi đáp tài liệu")

    if conversation_id is None:
        st.info("Tải tài liệu lên và tạo một hội thoại ở thanh bên để bắt đầu.")
        return

    for message in client.list_messages(conversation_id):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            render_steps(message.get("steps", []))

    question = st.chat_input("Hỏi gì về tài liệu này?")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"), st.spinner("Agent đang đọc tài liệu..."):
            try:
                answer = client.send_message(conversation_id, question)
            except ApiError as exc:
                st.error(str(exc))
                return
            st.markdown(answer["content"])
            render_steps(answer.get("steps", []))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Chạy toàn bộ test**

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -m "not integration" -v
```

Expected: tất cả pass

- [ ] **Step 8: Commit**

```bash
git add ui/ pyproject.toml
git commit -m "feat: UI Streamlit gọi API qua HTTP client"
```

---

### Task 11: Docker compose đầy đủ, README và smoke test

**Files:**
- Create: `api/Dockerfile`, `api/entrypoint.sh`
- Create: `ui/Dockerfile`
- Modify: `docker-compose.yml`
- Create: `README.md`
- Create: `api/tests/test_smoke_integration.py`

**Interfaces:**
- Consumes: mọi thứ ở các task trước.
- Produces: `docker compose up` chạy được cả ba service; smoke test đánh dấu `integration`.

- [ ] **Step 1: Viết `api/Dockerfile`**

```dockerfile
FROM python:3.14-slim

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /srv/pyproject.toml
COPY api /srv/api

RUN pip install --no-cache-dir -e "/srv"

WORKDIR /srv/api
COPY api/entrypoint.sh /srv/api/entrypoint.sh
RUN chmod +x /srv/api/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/srv/api/entrypoint.sh"]
```

- [ ] **Step 2: Viết `api/entrypoint.sh`**

```bash
#!/bin/sh
set -e

echo "Chạy migration..."
alembic upgrade head

echo "Khởi động API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: Viết `ui/Dockerfile`**

```dockerfile
FROM python:3.14-slim

WORKDIR /srv

COPY pyproject.toml /srv/pyproject.toml
COPY api /srv/api
COPY ui /srv/ui

RUN pip install --no-cache-dir -e "/srv[ui]"

ENV PYTHONPATH=/srv

EXPOSE 8501
CMD ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

- [ ] **Step 4: Viết `docker-compose.yml` đầy đủ**

```yaml
services:
  postgres:
    image: postgres:17-alpine
    container_name: fu-postgres
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: file_understanding
    ports:
      - "5433:5432"
    volumes:
      - fu_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d file_understanding"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    container_name: fu-api
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://app:app@postgres:5432/file_understanding
      DATA_DIR: /data
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

  ui:
    build:
      context: .
      dockerfile: ui/Dockerfile
    container_name: fu-ui
    depends_on:
      api:
        condition: service_healthy
    environment:
      API_BASE_URL: http://api:8000
    ports:
      - "8501:8501"

volumes:
  fu_pgdata:
```

- [ ] **Step 5: Viết smoke test `api/tests/test_smoke_integration.py`**

```python
from __future__ import annotations

import os

import httpx
import pytest

API_URL = os.getenv("SMOKE_API_URL", "http://localhost:8000")
SANDBOX_URL = os.getenv("SMOKE_SANDBOX_URL", "http://localhost:8081")

pytestmark = pytest.mark.integration


def test_api_health_song():
    response = httpx.get(f"{API_URL}/health", timeout=10)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sandbox_python_vm_song():
    response = httpx.get(f"{SANDBOX_URL}/health", timeout=10)

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_danh_sach_tai_lieu_goi_duoc():
    response = httpx.get(f"{API_URL}/documents", timeout=30)

    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 6: Viết `README.md`**

```markdown
# file-understanding

Bộ khung agent hỏi đáp tài liệu: upload file → chuyển sang markdown bằng LlamaParse →
hỏi đáp nhiều lượt qua agent CodeAct chạy code trong sandbox `python-vm`.

## Yêu cầu

- Docker + Docker Compose
- `python-vm` đang chạy sẵn ở port 8081 (repo riêng, không nằm trong compose này)
- Key LlamaParse và key của một provider LLM OpenAI-compatible (OpenRouter, Cerebras...)

## Chạy

```bash
cp .env.example .env
# điền LLM_API_KEY và LLAMA_CLOUD_API_KEY vào .env
docker compose up --build
```

- UI: http://localhost:8501
- API docs: http://localhost:8000/docs

## Kiến trúc

| Thành phần | Vai trò |
|---|---|
| `postgres` | conversation, message, document, artifact, agent step |
| `api` | FastAPI, chứa core agent |
| `ui` | Streamlit, chỉ gọi HTTP |
| `python-vm` (ngoài compose) | sandbox chạy code, giữ state theo session |

Sandbox session là cache chứ không phải nguồn sự thật: nếu session bị `python-vm`
dọn do idle, hệ thống tự tạo lại và upload lại markdown.

## Test

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -m "not integration"
```

Smoke test cần compose và `python-vm` đang chạy:

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -m integration
```

## Thiết kế và kế hoạch

- Spec: `docs/superpowers/specs/2026-08-18-file-understanding-framework-design.md`
- Plan: `docs/superpowers/plans/2026-08-18-file-understanding-framework.md`
```

- [ ] **Step 7: Build và chạy compose**

```bash
docker compose up -d --build
docker compose ps
```

Expected: cả ba service `running`, `api` ở trạng thái `healthy`.

- [ ] **Step 8: Chạy smoke test**

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -m integration -v
```

Expected: 3 passed. Nếu `test_sandbox_python_vm_song` fail, khởi động python-vm ở repo riêng rồi chạy lại.

- [ ] **Step 9: Kiểm tra thủ công UI**

Mở http://localhost:8501, upload một PDF, đợi trạng thái `ready`, tạo hội thoại, hỏi hai câu liên tiếp trong đó câu thứ hai tham chiếu tới câu thứ nhất (ví dụ: "Gói thầu số mấy?" rồi "Giá của nó là bao nhiêu?"). Xác nhận câu thứ hai hiểu được "nó".

- [ ] **Step 10: Chạy toàn bộ test lần cuối**

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -v
```

Expected: tất cả pass.

- [ ] **Step 11: Commit**

```bash
git add api/Dockerfile api/entrypoint.sh ui/Dockerfile docker-compose.yml README.md api/tests/test_smoke_integration.py
git commit -m "feat: docker compose đầy đủ, README và smoke test"
```
