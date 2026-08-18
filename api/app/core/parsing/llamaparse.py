"""Parser implementation calling LlamaParse (LlamaIndex Cloud) over plain REST via httpx.

The `llama-cloud-services` SDK is deliberately avoided: it drags in the whole
of `llama-index-core` just to do one job, converting a file to markdown.

User-facing error text stays in Vietnamese; comments and docstrings are English.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from app.core.parsing.base import ParseResult

LLAMA_CLOUD_BASE_URL = "https://api.cloud.llamaindex.ai"


class ParserError(Exception):
    """Converting the file to markdown failed.

    Every failure mode collapses into this one type — upload rejected, job
    reported ERROR, polling timed out, host unreachable — because the caller
    (`parse_document`) only needs to know the parse failed and why.
    """


class LlamaParseParser:
    """Talks to LlamaParse over REST: upload, poll the job, fetch the markdown."""

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
        """Upload the file, wait for the job to finish, then fetch the markdown result."""
        job_id = self._upload(file_path, mime_type)
        self._wait_for_job(job_id)
        markdown = self._fetch_markdown(job_id)
        return ParseResult(markdown=markdown, parser_name=self.parser_name)

    def _upload(self, file_path: Path, mime_type: str | None) -> str:
        """POST the file as multipart and return the job id LlamaParse assigns."""
        with file_path.open("rb") as handle:
            files = {"file": (file_path.name, handle, mime_type or "application/octet-stream")}
            data = self._request("POST", "/api/v1/parsing/upload", files=files)
        job_id = data.get("id")
        if not job_id:
            raise ParserError(f"LlamaParse không trả job id: {data}")
        return job_id

    def _wait_for_job(self, job_id: str) -> None:
        """Poll the job until SUCCESS, raising ParserError on failure or timeout.

        Each iteration checks the status first and the deadline second, so the
        job always gets one final status read before the timeout can fire.
        """
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
        """Fetch the finished job's markdown output."""
        data = self._request("GET", f"/api/v1/parsing/job/{job_id}/result/markdown")
        return data.get("markdown", "")

    def _request(self, method: str, path: str, files: dict | None = None) -> dict:
        """Send one request, mapping transport and HTTP errors onto ParserError."""
        try:
            response = self._client.request(method, path, files=files)
        except httpx.HTTPError as exc:
            raise ParserError(f"Không gọi được LlamaParse: {exc}") from exc
        if response.status_code >= 400:
            raise ParserError(f"LlamaParse trả về {response.status_code}: {response.text[:500]}")
        return response.json()
