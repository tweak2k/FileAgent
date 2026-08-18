"""ORM tables: documents, document_artifacts, conversations, messages, agent_steps."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    """An uploaded file and the state of its conversion to markdown.

    parse_status moves pending -> parsing -> ready | failed. Nothing outside
    `parse_document` writes it, and every parse run must end at ready or
    failed — see api/app/core/parsing/pipeline.py.
    """

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
    """Parser output for a document, keyed by `kind` (currently only "markdown").

    Kept in its own table so later artifact kinds — an outline, a chunk index —
    can be added without a schema change.
    """

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
    """A multi-turn Q&A session about one document, optionally holding a sandbox session.

    `sandbox_session_id` is a cache, not the source of truth: if python-vm has
    reaped the session, SessionResolver creates a new one and re-uploads the
    markdown transparently.
    """

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
    """One conversation turn, from either the user or the assistant.

    Ordered by (created_at, id): Postgres now() is the transaction timestamp,
    so messages written in the same transaction share created_at and only the
    id breaks the tie.
    """

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
    """One CodeAct code-execution step recorded while answering a message.

    This is what makes a demo convincing: it shows the code the agent actually
    ran, together with its stdout and stderr.
    """

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
