"""Hiện thực SandboxClient gọi HTTP tới microservice python-vm."""

from __future__ import annotations

import base64

import httpx

from app.core.sandbox.exceptions import (
    SandboxCapacityError,
    SandboxError,
    SandboxSessionNotFound,
    SandboxUnavailable,
)
from app.core.sandbox.models import ExecutionResult, SandboxFile


class HttpSandboxClient:
    """Gọi python-vm qua HTTP. Xem README của python-vm cho hợp đồng API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: int = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds + 15,
            transport=transport,
        )

    def create_session(self, files: list[SandboxFile]) -> str:
        payload = {
            "files": [
                {
                    "path": f.path,
                    "content_base64": base64.b64encode(f.content.encode()).decode(),
                    "size_bytes": len(f.content.encode()),
                }
                for f in files
            ]
        }
        data = self._request("POST", "/sessions", json=payload)
        return data["session_id"]

    def execute(self, session_id: str, code: str) -> ExecutionResult:
        data = self._request(
            "POST",
            f"/sessions/{session_id}/execute",
            json={"code": code, "timeout_seconds": self._timeout_seconds},
        )
        return ExecutionResult(
            status=data.get("status", "failed"),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            timed_out=bool(data.get("timed_out", False)),
            duration_ms=int(data.get("duration_ms", 0)),
        )

    def close_session(self, session_id: str) -> None:
        try:
            self._request("DELETE", f"/sessions/{session_id}")
        except SandboxSessionNotFound:
            return

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            response = self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise SandboxUnavailable(f"Không gọi được sandbox: {exc}") from exc

        if response.status_code == 404:
            raise SandboxSessionNotFound(path)
        if response.status_code == 429:
            raise SandboxCapacityError("Sandbox đã hết slot session")
        if response.status_code >= 400:
            raise SandboxError(f"Sandbox trả về {response.status_code}: {response.text[:500]}")

        if not response.content:
            return {}
        return response.json()
