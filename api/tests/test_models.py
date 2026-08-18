"""Tests for the ORM models and their relationships."""

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
