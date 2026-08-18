"""Client HTTP gọi sang API backend (Task 8, 9).

UI không import gì từ `api/app` — mọi giao tiếp đi qua đây, để sau này
đổi UI khác không ảnh hưởng tới core.
"""

from __future__ import annotations

import httpx


class ApiError(Exception):
    """API trả về lỗi hoặc không gọi được.

    `status_code` là mã HTTP trả về (None nếu lỗi xảy ra trước khi có phản
    hồi, vd. không kết nối được tới API) — để nơi gọi phân biệt được, ví dụ
    503 (sandbox không dùng được) cần gợi ý khác với các lỗi khác.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Bọc httpx.Client để gọi các endpoint của backend qua HTTP."""

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        # timeout rất rộng vì một lượt chat có thể chạy nhiều bước code trong sandbox
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=600.0, transport=transport
        )

    def health(self) -> bool:
        """Kiểm tra API còn sống. Không ném lỗi — trả False nếu không kết nối được."""
        try:
            return self._client.get("/health").status_code == 200
        except httpx.HTTPError:
            return False

    def upload_document(self, name: str, data: bytes, mime: str) -> dict:
        return self._request("POST", "/documents", files={"file": (name, data, mime)})

    def list_documents(self) -> list[dict]:
        return self._request("GET", "/documents")

    def get_document(self, document_id: int) -> dict:
        return self._request("GET", f"/documents/{document_id}")

    def create_conversation(self, document_id: int) -> dict:
        return self._request("POST", "/conversations", json={"document_id": document_id})

    def list_conversations(self, document_id: int) -> list[dict]:
        return self._request("GET", "/conversations", params={"document_id": document_id})

    def list_messages(self, conversation_id: int) -> list[dict]:
        return self._request("GET", f"/conversations/{conversation_id}/messages")

    def send_message(self, conversation_id: int, content: str) -> dict:
        return self._request(
            "POST", f"/conversations/{conversation_id}/messages", json={"content": content}
        )

    def reset_sandbox(self, conversation_id: int) -> None:
        self._request("POST", f"/conversations/{conversation_id}/reset-sandbox")

    def _request(self, method: str, path: str, **kwargs):
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
