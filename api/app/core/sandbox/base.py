"""Protocol describing the contract of a sandbox client."""

from __future__ import annotations

from typing import Protocol

from app.core.sandbox.models import ExecutionResult, SandboxFile


class SandboxClient(Protocol):
    """Contract for creating sessions, running code, and closing sandbox sessions."""

    def create_session(self, files: list[SandboxFile]) -> str: ...

    def execute(self, session_id: str, code: str) -> ExecutionResult: ...

    def close_session(self, session_id: str) -> None: ...
