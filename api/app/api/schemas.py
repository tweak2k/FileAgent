"""Pydantic schemas for API requests and responses.

These define the HTTP contract the Streamlit UI codes against; see docs/api.md.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    """A document plus its parse state; char_count is 0 until parsing succeeds."""

    id: int
    filename: str
    mime_type: str
    parse_status: str
    parse_error: str | None = None
    char_count: int = 0


class ConversationCreate(BaseModel):
    """Request body for starting a conversation about a document."""

    document_id: int
    title: str | None = None


class ConversationOut(BaseModel):
    """A conversation; sandbox_session_id is null until the first code run."""

    id: int
    document_id: int
    title: str
    sandbox_session_id: str | None = None


class AgentStepOut(BaseModel):
    """One code-execution step, shown in the UI under the assistant reply."""

    step_index: int
    code: str
    stdout: str
    stderr: str
    status: str
    duration_ms: int


class MessageOut(BaseModel):
    """A conversation turn; `steps` is empty for user messages."""

    id: int
    role: str
    content: str
    created_at: datetime
    steps: list[AgentStepOut] = []


class MessageCreate(BaseModel):
    """Request body for asking a question in a conversation."""

    content: str
