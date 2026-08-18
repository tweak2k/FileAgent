"""Route hội thoại: tạo, liệt kê, gửi câu hỏi, reset sandbox, xoá."""

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
from app.db.models import Conversation, Document
from app.db.session import get_db
from app.dependencies import get_llm_client, get_sandbox_client

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _to_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        document_id=conversation.document_id,
        title=conversation.title,
        sandbox_session_id=conversation.sandbox_session_id,
    )


def _message_out(message: object) -> MessageOut:
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
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại")
    return conversation


def _build_service(db: Session, llm: LLMClient, sandbox: SandboxClient) -> ChatService:
    return ChatService(db=db, llm=llm, sandbox=sandbox, max_steps=get_settings().agent_max_steps)


@router.post("", status_code=201, response_model=ConversationOut)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> ConversationOut:
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
    statement = select(Conversation).order_by(Conversation.id.desc())
    if document_id is not None:
        statement = statement.where(Conversation.document_id == document_id)
    return [_to_out(c) for c in db.scalars(statement).all()]


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: int, db: Session = Depends(get_db)) -> list[MessageOut]:
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
    conversation = _get_conversation(conversation_id, db)
    service = _build_service(db, llm, sandbox)

    try:
        message = service.answer(conversation, payload.content)
    except SandboxCapacityError as exc:
        raise HTTPException(status_code=503, detail=f"Sandbox quá tải: {exc}") from exc
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=f"Sandbox không dùng được: {exc}") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Lỗi gọi LLM: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _message_out(message)


@router.post("/{conversation_id}/reset-sandbox", status_code=204, response_class=Response)
def reset_sandbox(
    conversation_id: int,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> Response:
    conversation = _get_conversation(conversation_id, db)
    _build_service(db, llm, sandbox).reset_sandbox(conversation)
    return Response(status_code=204)


@router.delete("/{conversation_id}", status_code=204, response_class=Response)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    sandbox: SandboxClient = Depends(get_sandbox_client),
) -> Response:
    conversation = _get_conversation(conversation_id, db)
    _build_service(db, llm, sandbox).reset_sandbox(conversation)
    db.delete(conversation)
    db.commit()
    return Response(status_code=204)
