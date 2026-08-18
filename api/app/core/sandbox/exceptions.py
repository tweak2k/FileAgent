"""Các exception dùng khi giao tiếp với sandbox python-vm."""

from __future__ import annotations


class SandboxError(Exception):
    """Lỗi hạ tầng khi làm việc với sandbox."""


class SandboxSessionNotFound(SandboxError):
    """Session không còn tồn tại (đã bị reap)."""


class SandboxCapacityError(SandboxError):
    """Sandbox hết slot session."""


class SandboxUnavailable(SandboxError):
    """Không kết nối được tới sandbox."""
