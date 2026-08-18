"""Pydantic schema cho request/response của API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    parse_status: str
    parse_error: str | None = None
    char_count: int = 0


class ConversationCreate(BaseModel):
    document_id: int
    title: str | None = None


class ConversationOut(BaseModel):
    id: int
    document_id: int
    title: str
    sandbox_session_id: str | None = None


class AgentStepOut(BaseModel):
    step_index: int
    code: str
    stdout: str
    stderr: str
    status: str
    duration_ms: int


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    steps: list[AgentStepOut] = []


class MessageCreate(BaseModel):
    content: str
