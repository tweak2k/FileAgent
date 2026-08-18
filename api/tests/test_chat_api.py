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
