"""Shared interface for parsers that turn a file into markdown."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParseResult:
    """Outcome of converting one file to markdown."""

    markdown: str
    parser_name: str


class Parser(Protocol):
    """Contract every parser must satisfy — LlamaParse today, anything else later."""

    def to_markdown(self, file_path: Path, mime_type: str | None = None) -> ParseResult: ...
