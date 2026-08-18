"""Hiện thực Parser gọi LlamaParse (LlamaIndex Cloud) qua REST trực tiếp bằng httpx.

Không dùng SDK `llama-cloud-services` vì nó kéo theo cả `llama-index-core`
rất nặng chỉ để làm một việc là chuyển file sang markdown.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from app.core.parsing.base import ParseResult

LLAMA_CLOUD_BASE_URL = "https://api.cloud.llamaindex.ai"


class ParserError(Exception):
    """Chuyển file sang markdown thất bại."""


class LlamaParseParser:
    """Gọi LlamaParse qua REST, không dùng SDK để khỏi kéo llama-index-core."""

    parser_name = "llamaparse"

    def __init__(
        self,
        api_key: str,
        poll_interval_seconds: float = 2.0,
        max_wait_seconds: float = 600.0,
        base_url: str = LLAMA_CLOUD_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._max_wait_seconds = max_wait_seconds
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120.0,
            transport=transport,
        )

    def to_markdown(self, file_path: Path, mime_type: str | None = None) -> ParseResult:
        """Upload file, chờ job xong rồi lấy kết quả markdown."""
        job_id = self._upload(file_path, mime_type)
        self._wait_for_job(job_id)
        markdown = self._fetch_markdown(job_id)
        return ParseResult(markdown=markdown, parser_name=self.parser_name)

    def _upload(self, file_path: Path, mime_type: str | None) -> str:
        with file_path.open("rb") as handle:
            files = {"file": (file_path.name, handle, mime_type or "application/octet-stream")}
            data = self._request("POST", "/api/v1/parsing/upload", files=files)
        job_id = data.get("id")
        if not job_id:
            raise ParserError(f"LlamaParse không trả job id: {data}")
        return job_id

    def _wait_for_job(self, job_id: str) -> None:
        deadline = time.monotonic() + self._max_wait_seconds
        while True:
            data = self._request("GET", f"/api/v1/parsing/job/{job_id}")
            status = data.get("status", "").upper()
            if status == "SUCCESS":
                return
            if status in {"ERROR", "FAILED", "CANCELED"}:
                raise ParserError(data.get("error_message") or f"Job {job_id} thất bại: {status}")
            if time.monotonic() > deadline:
                raise ParserError(f"Job {job_id} quá thời gian chờ {self._max_wait_seconds}s")
            time.sleep(self._poll_interval_seconds)

    def _fetch_markdown(self, job_id: str) -> str:
        data = self._request("GET", f"/api/v1/parsing/job/{job_id}/result/markdown")
        return data.get("markdown", "")

    def _request(self, method: str, path: str, files: dict | None = None) -> dict:
        try:
            response = self._client.request(method, path, files=files)
        except httpx.HTTPError as exc:
            raise ParserError(f"Không gọi được LlamaParse: {exc}") from exc
        if response.status_code >= 400:
            raise ParserError(f"LlamaParse trả về {response.status_code}: {response.text[:500]}")
        return response.json()
