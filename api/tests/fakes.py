"""Shared fakes for the three protocol boundaries, used across the test suite."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.sandbox.exceptions import SandboxSessionNotFound
from app.core.sandbox.models import ExecutionResult, SandboxFile


@dataclass
class FakeSandboxClient:
    """Fake sandbox: counts session creations and can force a session to be "reaped".

    Put a session id into `dead_sessions` and the next execute() on it raises
    SandboxSessionNotFound, exactly as python-vm does after its reaper runs.
    """

    created_sessions: list[list[SandboxFile]] = field(default_factory=list)
    closed_sessions: list[str] = field(default_factory=list)
    executed: list[tuple[str, str]] = field(default_factory=list)
    dead_sessions: set[str] = field(default_factory=set)
    stdout_queue: list[str] = field(default_factory=list)
    _counter: int = 0

    def create_session(self, files: list[SandboxFile]) -> str:
        self._counter += 1
        self.created_sessions.append(files)
        return f"sess_{self._counter}"

    def execute(self, session_id: str, code: str) -> ExecutionResult:
        if session_id in self.dead_sessions:
            raise SandboxSessionNotFound(session_id)
        self.executed.append((session_id, code))
        stdout = self.stdout_queue.pop(0) if self.stdout_queue else ""
        return ExecutionResult(
            status="completed", stdout=stdout, stderr="", timed_out=False, duration_ms=1
        )

    def close_session(self, session_id: str) -> None:
        self.closed_sessions.append(session_id)


@dataclass
class FakeLLMClient:
    """Fake LLM: returns scripted responses in order and records every call.

    `calls` holds the exact message list passed on each turn, which is how the
    multi-turn tests assert on prompt contents and ordering.
    """

    responses: list[str] = field(default_factory=list)
    calls: list[list[dict[str, str]]] = field(default_factory=list)

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append([dict(m) for m in messages])
        if not self.responses:
            raise AssertionError("FakeLLMClient hết response nhưng vẫn bị gọi")
        return self.responses.pop(0)
