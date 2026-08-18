"""Protocol mô tả hợp đồng của một sandbox client."""

from __future__ import annotations

from typing import Protocol

from app.core.sandbox.models import ExecutionResult, SandboxFile


class SandboxClient(Protocol):
    """Hợp đồng client để tạo session, chạy code, và đóng session sandbox."""

    def create_session(self, files: list[SandboxFile]) -> str: ...

    def execute(self, session_id: str, code: str) -> ExecutionResult: ...

    def close_session(self, session_id: str) -> None: ...
