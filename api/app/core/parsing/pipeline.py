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
    Toàn bộ phần thân sau khi đặt parse_status="parsing" — gọi parser, ghi
    file markdown, ghi bản ghi DocumentArtifact — đều nằm trong một
    try/except chung: bất kỳ lỗi nào (parser lỗi, hết đĩa, không có quyền
    ghi, lỗi DB...) đều phải kết thúc ở parse_status="failed", vì không có
    ai bắt exception của job nền cả — để lọt ra ngoài thì document sẽ kẹt
    vĩnh viễn ở trạng thái "parsing".
    """
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.parse_status = "parsing"
        db.commit()

        try:
            result = parser.to_markdown(Path(document.source_path), document.mime_type)

            artifacts_dir.mkdir(parents=True, exist_ok=True)
            target = artifacts_dir / f"{document_id}.md"
            target.write_text(result.markdown, encoding="utf-8")

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
        except Exception as exc:
            # Session có thể đang ở trạng thái lỗi nếu chính db.commit() ở
            # trên vừa thất bại (vd. lỗi ràng buộc DB) — phải rollback
            # trước khi commit lại, nếu không sẽ dính PendingRollbackError.
            db.rollback()
            document.parse_status = "failed"
            document.parse_error = str(exc)[:2000]
            db.commit()


def read_markdown(document: Document) -> str:
    """Đọc nội dung markdown artifact mới nhất của document.

    Ném ValueError nếu document chưa có artifact markdown nào.
    """
    artifacts = [a for a in document.artifacts if a.kind == "markdown"]
    if not artifacts:
        raise ValueError(f"Tài liệu {document.id} chưa có artifact markdown")
    latest = max(artifacts, key=lambda a: a.id)
    return Path(latest.content_path).read_text(encoding="utf-8")
