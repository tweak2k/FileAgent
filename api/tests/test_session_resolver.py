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
