"""Tests for the python-vm HTTP client and its status-code to exception mapping."""

from __future__ import annotations

import base64

import httpx
import pytest

from app.core.sandbox.client import HttpSandboxClient
from app.core.sandbox.exceptions import (
    SandboxCapacityError,
    SandboxSessionNotFound,
    SandboxUnavailable,
)
from app.core.sandbox.models import SandboxFile


def build_client(handler) -> HttpSandboxClient:
    transport = httpx.MockTransport(handler)
    return HttpSandboxClient(
        base_url="http://sandbox.test",
        api_key="secret",
        timeout_seconds=30,
        transport=transport,
    )


def test_create_session_gui_file_base64_va_bearer_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"session_id": "sess_1"})

    client = build_client(handler)

    session_id = client.create_session([SandboxFile(path="document.md", content="# Xin chào")])

    assert session_id == "sess_1"
    assert captured["url"] == "http://sandbox.test/sessions"
    assert captured["auth"] == "Bearer secret"
    assert base64.b64encode("# Xin chào".encode()).decode() in captured["body"]


def test_execute_tra_ve_ket_qua_chuan_hoa():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://sandbox.test/sessions/sess_1/execute"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "stdout": "42\n",
                "stderr": "",
                "timed_out": False,
                "duration_ms": 15,
            },
        )

    client = build_client(handler)

    result = client.execute("sess_1", "print(42)")

    assert result.status == "completed"
    assert result.stdout == "42\n"
    assert result.timed_out is False
    assert result.duration_ms == 15


def test_execute_404_nem_session_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "session not found"})

    client = build_client(handler)

    with pytest.raises(SandboxSessionNotFound):
        client.execute("sess_die", "print(1)")


def test_create_session_429_nem_capacity_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "session limit reached"})

    client = build_client(handler)

    with pytest.raises(SandboxCapacityError):
        client.create_session([])


def test_khong_ket_noi_duoc_nem_sandbox_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = build_client(handler)

    with pytest.raises(SandboxUnavailable):
        client.create_session([])


def test_close_session_bo_qua_404():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(404)

    client = build_client(handler)

    client.close_session("sess_die")  # không được ném lỗi
