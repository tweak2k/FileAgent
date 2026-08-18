"""Tests for the UI's HTTP client, driven by httpx.MockTransport (no real network)."""

from __future__ import annotations

import httpx
import pytest

from ui.api_client import ApiClient, ApiError


def build_client(handler) -> ApiClient:
    return ApiClient(base_url="http://api.test", transport=httpx.MockTransport(handler))


def test_health_tra_true_khi_api_song():
    client = build_client(lambda r: httpx.Response(200, json={"status": "ok"}))

    assert client.health() is True


def test_health_tra_false_khi_khong_ket_noi_duoc():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert build_client(handler).health() is False


def test_upload_document_gui_multipart():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.read()
        return httpx.Response(201, json={"id": 7, "filename": "a.pdf"})

    result = build_client(handler).upload_document("a.pdf", b"data", "application/pdf")

    assert result["id"] == 7
    assert captured["path"] == "/documents"
    assert b"a.pdf" in captured["body"]


def test_send_message_tra_ve_message():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/conversations/3/messages"
        return httpx.Response(200, json={"id": 9, "role": "assistant", "content": "ok", "steps": []})

    result = build_client(handler).send_message(3, "câu hỏi")

    assert result["content"] == "ok"


def test_loi_http_nem_api_error_kem_thong_diep():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "Sandbox không dùng được"})

    with pytest.raises(ApiError, match="Sandbox không dùng được") as exc_info:
        build_client(handler).send_message(1, "q")

    # The UI needs status_code so it can single out 503 and suggest checking python-vm.
    assert exc_info.value.status_code == 503


def test_loi_mang_nem_api_error_khong_co_status_code():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiError) as exc_info:
        build_client(handler).send_message(1, "q")

    assert exc_info.value.status_code is None
