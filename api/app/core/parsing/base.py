"""Giao diện chung cho các parser chuyển file sang markdown."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParseResult:
    """Kết quả chuyển một file sang markdown."""

    markdown: str
    parser_name: str


class Parser(Protocol):
    """Hợp đồng mà mọi parser (LlamaParse hoặc parser khác sau này) phải tuân theo."""

    def to_markdown(self, file_path: Path, mime_type: str | None = None) -> ParseResult: ...
