from __future__ import annotations

import httpx
import pytest

from app.core.parsing.llamaparse import LlamaParseParser, ParserError


def build_parser(handler) -> LlamaParseParser:
    return LlamaParseParser(
        api_key="llx-test",
        poll_interval_seconds=0,
        max_wait_seconds=5,
        transport=httpx.MockTransport(handler),
    )


def test_parse_thanh_cong_tra_ve_markdown(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.headers["authorization"] == "Bearer llx-test"
        if request.url.path.endswith("/parsing/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        if request.url.path.endswith("/parsing/job/job-1"):
            return httpx.Response(200, json={"status": "SUCCESS"})
        if request.url.path.endswith("/result/markdown"):
            return httpx.Response(200, json={"markdown": "# Tiêu đề\n\nnội dung"})
        raise AssertionError(f"đường dẫn lạ: {request.url.path}")

    parser = build_parser(handler)

    result = parser.to_markdown(source, mime_type="application/pdf")

    assert result.markdown == "# Tiêu đề\n\nnội dung"
    assert result.parser_name == "llamaparse"
    assert any(p.endswith("/parsing/upload") for p in seen)


def test_parse_poll_qua_trang_thai_pending(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"x")
    statuses = ["PENDING", "PENDING", "SUCCESS"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/parsing/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        if request.url.path.endswith("/parsing/job/job-1"):
            return httpx.Response(200, json={"status": statuses.pop(0)})
        return httpx.Response(200, json={"markdown": "ok"})

    parser = build_parser(handler)

    assert parser.to_markdown(source).markdown == "ok"
    assert statuses == []


def test_parse_job_loi_thi_nem_parser_error(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/parsing/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(200, json={"status": "ERROR", "error_message": "file hỏng"})

    parser = build_parser(handler)

    with pytest.raises(ParserError, match="file hỏng"):
        parser.to_markdown(source)


def test_upload_loi_http_thi_nem_parser_error(tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "sai key"})

    parser = build_parser(handler)

    with pytest.raises(ParserError):
        parser.to_markdown(source)
