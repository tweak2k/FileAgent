"""Background job converting an uploaded file to markdown, plus artifact readback."""

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
    """Background job: convert the file to markdown and record the artifact.

    Opens its own DB session because it runs after the request has already
    returned (FastAPI BackgroundTasks).

    Everything after parse_status is set to "parsing" — the parser call, the
    markdown write, the DocumentArtifact insert — sits inside one try/except.
    Any failure (parser error, disk full, permission denied, DB error) must
    end at parse_status="failed", because nothing catches an exception raised
    by a background job: letting one escape would leave the document stuck at
    "parsing" forever.
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
            # The session may already be in a failed state if the db.commit()
            # above is what raised (e.g. a constraint violation), so roll back
            # before committing again — otherwise this hits PendingRollbackError.
            db.rollback()
            document.parse_status = "failed"
            document.parse_error = str(exc)[:2000]
            db.commit()


def read_markdown(document: Document) -> str:
    """Read the document's most recent markdown artifact.

    Raises ValueError when the document has no markdown artifact yet — the
    chat layer maps that onto HTTP 409.
    """
    artifacts = [a for a in document.artifacts if a.kind == "markdown"]
    if not artifacts:
        raise ValueError(f"Tài liệu {document.id} chưa có artifact markdown")
    latest = max(artifacts, key=lambda a: a.id)
    return Path(latest.content_path).read_text(encoding="utf-8")
