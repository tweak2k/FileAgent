from __future__ import annotations

from contextlib import contextmanager
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

    import app.api.documents as documents_module

    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(
        documents_module, "get_session_factory", lambda: fake_session_scope
    )

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
