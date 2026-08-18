"""Adapter for any OpenAI-compatible endpoint (OpenRouter, Cerebras, Groq, vLLM...).

User-facing error text stays in Vietnamese: it surfaces through the API and
the UI to Vietnamese-speaking users. Comments and docstrings are English.
"""

from __future__ import annotations

import time

from openai import OpenAI

MAX_ATTEMPTS = 3


class LLMError(Exception):
    """The LLM call failed even after retrying."""


class OpenAICompatibleClient:
    """Adapter for any OpenAI-compatible endpoint: OpenRouter, Cerebras, Groq, vLLM...

    Switching provider is a matter of changing LLM_BASE_URL, LLM_MODEL and
    LLM_API_KEY — no agent code is involved.
    """

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
        """Call chat completion, retrying on network/5xx errors, then raise LLMError.

        Three attempts in total, with exponential backoff between them. The
        original error is chained onto LLMError so the cause is not lost.
        """
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                )
                return completion.choices[0].message.content or ""
            except Exception as exc:  # every provider raises its own type; no common base class
                last_error = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(self._backoff_seconds * (2**attempt))
        raise LLMError(f"Gọi LLM thất bại sau {MAX_ATTEMPTS} lần: {last_error}") from last_error
