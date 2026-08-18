"""Tests for the document routes: upload, background parsing, and status readback."""

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

    # TestClient runs BackgroundTasks synchronously once the response is returned.
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


def test_loi_ghi_markdown_khien_document_chuyen_sang_failed_khong_ket_o_parsing(
    client, db_session, tmp_path
):
    # A plain file occupies artifacts_dir, so mkdir(parents=True, exist_ok=True)
    # raises FileExistsError right after the parser has already succeeded —
    # simulating an I/O failure while writing the markdown.
    (tmp_path / "artifacts").write_text("khong phai thu muc")

    response = client.post(
        "/documents", files={"file": ("a.pdf", b"x", "application/pdf")}
    )
    doc_id = response.json()["id"]

    doc = db_session.get(Document, doc_id)
    db_session.refresh(doc)
    assert doc.parse_status == "failed"
    assert doc.parse_error


def test_upload_voi_ten_file_path_traversal_khong_ghi_ra_ngoai_thu_muc_upload(
    client, db_session, tmp_path
):
    response = client.post(
        "/documents",
        files={"file": ("../../evil.pdf", b"noi dung doc hai", "application/pdf")},
    )

    assert response.status_code == 201
    doc_id = response.json()["id"]

    doc = db_session.get(Document, doc_id)
    db_session.refresh(doc)

    uploads_dir = (tmp_path / "uploads").resolve()
    saved_path = Path(doc.source_path).resolve()
    assert saved_path.is_relative_to(uploads_dir)
    assert not (tmp_path / "evil.pdf").exists()
