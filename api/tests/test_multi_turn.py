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
    # list.index() chỉ tìm vị trí xuất hiện ĐẦU TIÊN — nếu build_history bị gọi
    # SAU khi lưu message người dùng, câu hỏi hiện tại sẽ lặp lại hai lần
    # trong prompt nhưng các assert index() ở trên vẫn xanh. Khoá thêm bằng
    # count() để bắt đúng lỗi trùng lặp này.
    assert contents.count("Còn giá thì sao?") == 1


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
