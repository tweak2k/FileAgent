"""Adapter cho mọi endpoint tương thích OpenAI (OpenRouter, Cerebras, Groq, vLLM...)."""

from __future__ import annotations

import time

from openai import OpenAI

MAX_ATTEMPTS = 3


class LLMError(Exception):
    """Gọi LLM thất bại sau khi đã retry."""


class OpenAICompatibleClient:
    """Adapter cho mọi endpoint OpenAI-compatible: OpenRouter, Cerebras, Groq, vLLM..."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int,
        client=None,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._client = client or OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._backoff_seconds = backoff_seconds

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Gọi chat completion, retry khi lỗi mạng/5xx, ném LLMError nếu vẫn thất bại."""
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                )
                return completion.choices[0].message.content or ""
            except Exception as exc:  # provider nào cũng ném kiểu riêng, không có lớp cha chung
                last_error = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(self._backoff_seconds * (2**attempt))
        raise LLMError(f"Gọi LLM thất bại sau {MAX_ATTEMPTS} lần: {last_error}") from last_error
