"""Route quản lý tài liệu: upload, liệt kê, xem trạng thái parse."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import DocumentOut
from app.config import get_settings
from app.core.parsing.base import Parser
from app.core.parsing.pipeline import parse_document
from app.db.models import Document
from app.db.session import get_db, get_session_factory
from app.dependencies import get_parser

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_out(document: Document) -> DocumentOut:
    markdown = [a for a in document.artifacts if a.kind == "markdown"]
    return DocumentOut(
        id=document.id,
        filename=document.filename,
        mime_type=document.mime_type,
        parse_status=document.parse_status,
        parse_error=document.parse_error,
        char_count=max((a.char_count for a in markdown), default=0),
    )


@router.post("", status_code=201, response_model=DocumentOut)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    parser: Parser = Depends(get_parser),
) -> DocumentOut:
    """Lưu file xuống đĩa, tạo bản ghi document rồi đẩy job parse chạy nền.

    Trả về document_id ngay, không chờ parser (LlamaParse có thể mất vài phút).
    """
    settings = get_settings()

    document = Document(
        filename=file.filename or "unnamed",
        mime_type=file.content_type or "application/octet-stream",
        source_path="",
    )
    db.add(document)
    db.flush()

    target_dir = settings.uploads_dir / str(document.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / document.filename
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    document.source_path = str(target)
    document.size_bytes = target.stat().st_size
    db.commit()

    background_tasks.add_task(
        parse_document,
        document_id=document.id,
        session_factory=get_session_factory(),
        parser=parser,
        artifacts_dir=settings.artifacts_dir,
    )
    return _to_out(document)


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    documents = db.scalars(select(Document).order_by(Document.id.desc())).all()
    return [_to_out(d) for d in documents]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)) -> DocumentOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    db.refresh(document)
    return _to_out(document)
