"""Job nền chuyển file đã upload sang markdown và ghi artifact."""

from __future__ import annotations

from pathlib import Path

from app.core.parsing.base import Parser
from app.db.models import Document, DocumentArtifact


def parse_document(
    document_id: int,
    session_factory,
    parser: Parser,
    artifacts_dir: Path,
) -> None:
    """Job nền: chuyển file sang markdown rồi ghi artifact.

    Mở session DB riêng vì chạy sau khi request đã trả về (BackgroundTasks).
    Mọi exception từ parser đều bị bắt và ghi vào parse_status/parse_error
    thay vì để bay lên, vì không có ai bắt exception của job nền cả.
    """
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.parse_status = "parsing"
        db.commit()

        try:
            result = parser.to_markdown(Path(document.source_path), document.mime_type)
        except Exception as exc:
            document.parse_status = "failed"
            document.parse_error = str(exc)[:2000]
            db.commit()
            return

        artifacts_dir.mkdir(parents=True, exist_ok=True)
        target = artifacts_dir / f"{document_id}.md"
        target.write_text(result.markdown)

        db.add(
            DocumentArtifact(
                document_id=document.id,
                kind="markdown",
                content_path=str(target),
                char_count=len(result.markdown),
                parser_name=result.parser_name,
            )
        )
        document.parse_status = "ready"
        document.parse_error = None
        db.commit()


def read_markdown(document: Document) -> str:
    """Đọc nội dung markdown artifact mới nhất của document.

    Ném ValueError nếu document chưa có artifact markdown nào.
    """
    artifacts = [a for a in document.artifacts if a.kind == "markdown"]
    if not artifacts:
        raise ValueError(f"Tài liệu {document.id} chưa có artifact markdown")
    latest = max(artifacts, key=lambda a: a.id)
    return Path(latest.content_path).read_text()
