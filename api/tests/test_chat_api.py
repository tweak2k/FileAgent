from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.llm.openai_compat import LLMError
from app.core.sandbox.exceptions import SandboxUnavailable
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
    """Câu hỏi không mất khi agent lỗi, và cũng không bị mồ côi: một assistant
    message báo lỗi phải được ghi kèm, nếu không lượt sau build_history() sẽ
    luôn thấy hai user liên tiếp trong prompt (không có API xoá message)."""
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = []  # FakeLLMClient sẽ ném AssertionError

    with pytest.raises(AssertionError):
        client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi lỗi"})

    messages = client.get(f"/conversations/{conv_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Hỏi lỗi"


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


def test_session_sandbox_khong_bi_mo_coi_khi_llm_loi_giua_luot(client, document, db_session):
    """Session vừa tạo phải được commit ngay, kể cả khi bước sau đó của agent lỗi.

    SessionResolver._create chỉ flush(), không commit(). Nếu LLM ném lỗi ở
    bước 2 (sau khi session đã được tạo ở bước 1) và ChatService không tự
    commit trước khi để exception bay lên, get_db() sẽ rollback toàn bộ khi
    request kết thúc: Postgres quên mất session vừa tạo trong khi session
    thật vẫn còn sống trên python-vm — mồ côi, tốn slot cho tới khi reaper
    dọn.
    """
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]

    class FlakyLLM:
        """LLM giả: bước 1 trả code (khiến sandbox session được tạo), bước 2 ném LLMError."""

        def __init__(self) -> None:
            self._step = 0

        def complete(self, messages: list[dict[str, str]]) -> str:
            self._step += 1
            if self._step == 1:
                return "```python\nprint(1)\n```"
            raise LLMError("hết retry")

    client.app.dependency_overrides[get_llm_client] = lambda: FlakyLLM()

    response = client.post(f"/conversations/{conv_id}/messages", json={"content": "Hỏi"})

    assert response.status_code == 502
    conversation = db_session.get(Conversation, conv_id)
    assert conversation.sandbox_session_id == "sess_1"
    assert len(client.fake_sandbox.created_sessions) == 1


def test_agent_step_khong_mat_va_khong_con_user_mo_coi_khi_llm_loi_giua_luot(
    client, document, db_session
):
    """Hai bước code đã chạy thành công không được biến mất khi bước 3 LLM lỗi.

    Nếu ChatService không bắt exception của agent.run và ghi lại các AgentStep
    đã thu được cộng một assistant message báo lỗi, thì (a) hai bước code đã
    thực thi trong sandbox sẽ không có bản ghi nào trong DB, và (b)
    conversation sẽ còn lại một message user không có assistant đi kèm —
    lượt kế tiếp build_history() trả về hai user liên tiếp trong prompt, mãi
    mãi (không có API xoá message).
    """
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]

    class FlakyLLM:
        """LLM giả: 2 bước đầu trả code chạy được, bước 3 ném LLMError."""

        def __init__(self) -> None:
            self._step = 0

        def complete(self, messages: list[dict[str, str]]) -> str:
            self._step += 1
            if self._step <= 2:
                return f"```python\nprint({self._step})\n```"
            raise LLMError("hết retry")

    client.app.dependency_overrides[get_llm_client] = lambda: FlakyLLM()

    response = client.post(
        f"/conversations/{conv_id}/messages", json={"content": "Hỏi lỗi giữa lượt"}
    )
    assert response.status_code == 502

    conversation = db_session.get(Conversation, conv_id)
    db_session.refresh(conversation)
    messages = conversation.messages
    assert [m.role for m in messages] == ["user", "assistant"]

    error_message = messages[-1]
    steps = error_message.steps
    assert len(steps) == 2
    assert [s.step_index for s in steps] == [0, 1]

    # Lượt kế tiếp: build_history() không được trả về hai user liên tiếp.
    client.app.dependency_overrides[get_llm_client] = lambda: client.fake_llm
    client.fake_llm.responses = ["Trả lời lượt hai."]
    response2 = client.post(
        f"/conversations/{conv_id}/messages", json={"content": "Hỏi lượt hai"}
    )
    assert response2.status_code == 200

    roles = [m["role"] for m in client.fake_llm.calls[-1]]
    for role_a, role_b in zip(roles, roles[1:]):
        assert not (role_a == "user" and role_b == "user")


def test_reset_sandbox_khi_sandbox_loi_tra_503(client, document):
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = ["```python\nprint(1)\n```", "xong"]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "q"})

    def _boom(session_id: str) -> None:
        raise SandboxUnavailable("mất kết nối")

    client.fake_sandbox.close_session = _boom

    response = client.post(f"/conversations/{conv_id}/reset-sandbox")

    assert response.status_code == 503


def test_xoa_conversation_van_thanh_cong_khi_dong_session_loi(client, document, db_session):
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = ["```python\nprint(1)\n```", "xong"]
    client.post(f"/conversations/{conv_id}/messages", json={"content": "q"})

    def _boom(session_id: str) -> None:
        raise SandboxUnavailable("mất kết nối")

    client.fake_sandbox.close_session = _boom

    response = client.delete(f"/conversations/{conv_id}")

    assert response.status_code == 204
    assert db_session.get(Conversation, conv_id) is None
