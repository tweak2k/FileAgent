"""Data types exchanged with the python-vm sandbox."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxFile:
    """A text file to upload into the sandbox session's workspace."""

    path: str
    content: str


@dataclass(frozen=True)
class ExecutionResult:
    """Normalised outcome of one code execution inside the sandbox."""

    status: str
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
