"""SandboxClient implementation talking HTTP to the python-vm microservice.

python-vm runs outside this project's docker compose, so the only coupling is
this HTTP contract. User-facing error text stays in Vietnamese; comments and
docstrings are English.
"""

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
    """Calls python-vm over HTTP. See the python-vm README for the API contract."""

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
            # Deliberately wider than the sandbox's own limit, so python-vm gets
            # to report status="timeout" itself instead of the HTTP call dying first.
            timeout=timeout_seconds + 15,
            transport=transport,
        )

    def create_session(self, files: list[SandboxFile]) -> str:
        """Create a stateful session with the given files uploaded into its workspace."""
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
        """Run code inside an existing session; variables persist across calls."""
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
        """Close a session, treating "already gone" as success.

        A 404 means python-vm's reaper got there first, which is the outcome
        we wanted anyway. Every other error still propagates.
        """
        try:
            self._request("DELETE", f"/sessions/{session_id}")
        except SandboxSessionNotFound:
            return

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        """Send one request, mapping python-vm's status codes onto sandbox exceptions."""
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
