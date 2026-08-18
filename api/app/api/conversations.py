"""Conversation routes: create, list, ask a question, reset the sandbox, delete.

User-facing error text stays in Vietnamese; comments and docstrings are English.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AgentStepOut,
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
)
from app.config import get_settings
from app.core.chat_service import ChatService
from app.core.llm.base import LLMClient
from app.core.llm.openai_compat import LLMError
from app.core.sandbox.base import SandboxClient
from app.core.sandbox.exceptions import SandboxCapacityError, SandboxError
from app.db.models import Conversation, Document, Message
from app.db.session import get_db
from app.dependencies import get_llm_client, get_sandbox_client

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _to_out(conversation: Conversation) -> ConversationOut:
    """Map a Conversation row onto the API schema."""
    return ConversationOut(
        id=conversation.id,
        document_id=conversation.document_id,
        title=conversation.title,
        sandbox_session_id=conversation.sandbox_session_id,
    )


def _message_out(message: Message) -> MessageOut:
    """Map a Message row and its agent steps onto the API schema."""
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        steps=[
            AgentStepOut(
                step_index=s.step_index,
                code=s.code,
                stdout=s.stdout,
                stderr=s.stderr,
                status=s.status,
                duration_ms=s.duration_ms,
            )
            for s in message.steps
        ],
    )


def _get_conversation(conversation_id: int, db: Session) -> Conversation:
    """Load a conversation or raise 404."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    return conversation


def _build_service(db: Session, llm: LLMClient, sandbox: SandboxClient) -> ChatService:
    """Assemble a ChatService for this request, reading max_steps from settings."""
    return ChatService(db=db, llm=llm, sandbox=sandbox, max_steps=get_settings().agent_max_steps)


def _raise_for_service_error(exc: Exception) -> None:
    """Map a ChatService error onto an HTTPException, shared by every route calling it.

    Order matters: SandboxCapacityError is a subclass of SandboxError, so it
    must be checked first or the 429-derived case would never be reached.
    Anything unrecognised is re-raised untouched.
    """
    if isinstance(exc, SandboxCapacityError):
        raise HTTPException(status_code=503, detail=f"Sandbox quá tải: {exc}") from exc
    if isinstance(exc, SandboxError):
        raise HTTPException(status_code=503, detail=f"Sandbox không dùng được: {exc}") from exc
    if isinstance(exc, LLMError):
        raise HTTPException(status_code=502, detail=f"Lỗi gọi LLM: {exc}") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post("", status_code=201, response_model=ConversationOut)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> ConversationOut:
    """Start a conversation about a document, refusing documents that are not ready."""
    document = db.get(Document, payload.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    if document.parse_status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Tài liệu chưa sẵn sàng (trạng thái: {document.parse_status})",
        )

    conversation = Conversation(
        document_id=document.id, title=payload.title or f"Hỏi đáp — {document.filename}"
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _to_out(conversation)


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    document_id: int | None = None, db: Session = Depends(get_db)
) -> list[ConversationOut]:
    """List conversations, newest first, optionally filtered to one document."""
    statement = select(Conversation).order_by(Conversation.id.desc())
    if document_id is not None:
        statement = statement.where(Conversation.document_id == document_id)
    return [_to_out(c) for c in db.scalars(statement).all()]


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: int, db: Session = Depends(get_db)) -> list[MessageOut]:
    """Return the full conversation history in order, each reply with its steps."""
    conversation = _get_conversation(conversation_id, db)
    return [_message_out(m) for m in conversation.messages]


@router.post("/{conversation_id}/messages", response_model=MessageOut)
def post_message(
    conversation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> MessageOut:
    """Ask a question and return the assistant's reply once the agent finishes.

    Synchronous by design: one turn can take several sandbox round trips, and
    the UI shows a spinner until it completes.
    """
    conversation = _get_conversation(conversation_id, db)
    service = _build_service(db, llm, sandbox)

    try:
        message = service.answer(conversation, payload.content)
    except (SandboxError, LLMError, ValueError) as exc:
        _raise_for_service_error(exc)

    return _message_out(message)


@router.post("/{conversation_id}/reset-sandbox", status_code=204, response_class=Response)
def reset_sandbox(
    conversation_id: int,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> Response:
    """Drop the conversation's sandbox session so the next turn starts from a clean one."""
    conversation = _get_conversation(conversation_id, db)
    try:
        _build_service(db, llm, sandbox).reset_sandbox(conversation)
    except (SandboxError, LLMError, ValueError) as exc:
        _raise_for_service_error(exc)
    return Response(status_code=204)


@router.delete("/{conversation_id}", status_code=204, response_class=Response)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> Response:
    """Delete a conversation, best-effort closing its sandbox session first."""
    conversation = _get_conversation(conversation_id, db)
    try:
        _build_service(db, llm, sandbox).reset_sandbox(conversation)
    except SandboxError:
        # Failing to close the sandbox session must NOT block the delete.
        # The session is only a cache (see SessionResolver's docstring): an
        # orphan left behind is collected by python-vm's reaper. Postgres is
        # the source of truth, and it is exactly the row we are deleting here,
        # so there is nothing to roll back.
        pass
    db.delete(conversation)
    db.commit()
    return Response(status_code=204)
