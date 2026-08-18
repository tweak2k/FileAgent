"""HTTP client for the backend API.

The UI imports nothing from `api/app` — every call goes through this module,
so replacing the UI later leaves the core untouched. User-facing error text
stays in Vietnamese; comments and docstrings are English.
"""

from __future__ import annotations

import httpx


class ApiError(Exception):
    """The API returned an error, or could not be reached at all.

    `status_code` is the HTTP status (None when the failure happened before a
    response existed, e.g. connection refused), so callers can react to
    specific cases — a 503 from a dead sandbox deserves different advice than
    a generic failure.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Thin wrapper over httpx.Client covering every backend endpoint the UI needs."""

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        # Very wide timeout: one chat turn can run several code steps in the sandbox.
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=600.0, transport=transport
        )

    def health(self) -> bool:
        """Check whether the API is up. Never raises — returns False if unreachable."""
        try:
            return self._client.get("/health").status_code == 200
        except httpx.HTTPError:
            return False

    def upload_document(self, name: str, data: bytes, mime: str) -> dict:
        """Upload a file and get back the created document, still unparsed."""
        return self._request("POST", "/documents", files={"file": (name, data, mime)})

    def list_documents(self) -> list[dict]:
        """List every document with its current parse status."""
        return self._request("GET", "/documents")

    def get_document(self, document_id: int) -> dict:
        """Fetch one document — used to poll while parsing runs."""
        return self._request("GET", f"/documents/{document_id}")

    def create_conversation(self, document_id: int) -> dict:
        """Start a conversation about a document that has finished parsing."""
        return self._request("POST", "/conversations", json={"document_id": document_id})

    def list_conversations(self, document_id: int) -> list[dict]:
        """List the conversations belonging to one document."""
        return self._request("GET", "/conversations", params={"document_id": document_id})

    def list_messages(self, conversation_id: int) -> list[dict]:
        """Fetch the full history of a conversation, each reply with its steps."""
        return self._request("GET", f"/conversations/{conversation_id}/messages")

    def send_message(self, conversation_id: int, content: str) -> dict:
        """Ask a question and block until the agent produces its reply."""
        return self._request(
            "POST", f"/conversations/{conversation_id}/messages", json={"content": content}
        )

    def reset_sandbox(self, conversation_id: int) -> None:
        """Drop the conversation's sandbox session so the next turn starts clean."""
        self._request("POST", f"/conversations/{conversation_id}/reset-sandbox")

    def _request(self, method: str, path: str, **kwargs):
        """Send one request, turning failures into ApiError and 204s into None."""
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"Không gọi được API: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
            raise ApiError(str(detail), status_code=response.status_code)

        if not response.content:
            return None
        return response.json()
