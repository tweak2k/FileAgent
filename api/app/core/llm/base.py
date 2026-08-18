"""Shared protocol for every LLM client, so the agent stays provider-agnostic."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """The minimum the agent needs: send messages, get the reply text back."""

    def complete(self, messages: list[dict[str, str]]) -> str: ...
