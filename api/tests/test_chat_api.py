"""Tests for the conversation and chat routes, including failure handling mid-turn."""

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
    """The question survives an agent failure without being left orphaned.

    An assistant message recording the failure must be written alongside it,
    otherwise build_history() would see two user messages in a row on every
    later turn — and there is no API for deleting a message.
    """
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]
    client.fake_llm.responses = []  # FakeLLMClient raises AssertionError when exhausted

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
    """A freshly created session must be committed even if a later step fails.

    SessionResolver._create only flushes, it never commits. If the LLM raises
    on step 2 (after step 1 created the session) and ChatService does not
    commit before letting the exception escape, get_db() rolls everything back
    when the request ends: Postgres forgets the session while the real one is
    still alive on python-vm — orphaned, holding a slot until the reaper runs.
    """
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]

    class FlakyLLM:
        """Fake LLM: step 1 returns code (creating the session), step 2 raises LLMError."""

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
    """Two successful code steps must not vanish when step 3 fails in the LLM.

    Without ChatService catching agent.run's exception and persisting both the
    collected AgentSteps and an assistant message noting the failure, (a) the
    two steps that really ran in the sandbox would have no DB record, and (b)
    the conversation would keep a user message with no assistant reply — so
    build_history() would return two user messages in a row on every later
    turn, permanently, since no API deletes a message.
    """
    conv_id = client.post("/conversations", json={"document_id": document.id}).json()["id"]

    class FlakyLLM:
        """Fake LLM: the first two steps return runnable code, the third raises LLMError."""

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

    # Next turn: build_history() must not return two user messages in a row.
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
