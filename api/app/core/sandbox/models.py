"""Kiểu dữ liệu trao đổi với sandbox python-vm."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxFile:
    """Một file văn bản sẽ được upload vào workspace của session sandbox."""

    path: str
    content: str


@dataclass(frozen=True)
class ExecutionResult:
    """Kết quả chuẩn hoá của một lần thực thi code trong sandbox."""

    status: str
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int

    @property
    def failed(self) -> bool:
        """True nếu lần thực thi không kết thúc ở trạng thái completed."""
        return self.status != "completed"
