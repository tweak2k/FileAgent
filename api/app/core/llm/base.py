"""Protocol chung cho mọi LLM client, để agent không phụ thuộc vào provider cụ thể."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Giao diện tối thiểu mà agent cần: gửi messages, nhận về nội dung trả lời."""

    def complete(self, messages: list[dict[str, str]]) -> str: ...
