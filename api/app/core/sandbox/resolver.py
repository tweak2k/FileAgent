from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.sandbox.base import SandboxClient
from app.core.sandbox.exceptions import SandboxSessionNotFound
from app.core.sandbox.models import ExecutionResult, SandboxFile
from app.db.models import Conversation

WORKSPACE_DOCUMENT_PATH = "document.md"


class SessionResolver:
    """Sandbox session là cache, không phải nguồn sự thật.

    Nguồn sự thật là Postgres. Nếu session đã bị reaper của python-vm dọn,
    ta tạo lại và upload lại markdown — người dùng không cần biết.
    """

    def __init__(self, client: SandboxClient, db: Session) -> None:
        self._client = client
        self._db = db

    def ensure(self, conversation: Conversation, markdown: str) -> str:
        if conversation.sandbox_session_id:
            return conversation.sandbox_session_id
        return self._create(conversation, markdown)

    def run_code(self, conversation: Conversation, markdown: str, code: str) -> ExecutionResult:
        session_id = self.ensure(conversation, markdown)
        try:
            return self._client.execute(session_id, code)
        except SandboxSessionNotFound:
            session_id = self._create(conversation, markdown)
            return self._client.execute(session_id, code)

    def reset(self, conversation: Conversation) -> None:
        if conversation.sandbox_session_id:
            self._client.close_session(conversation.sandbox_session_id)
        conversation.sandbox_session_id = None
        conversation.sandbox_session_created_at = None
        self._db.flush()

    def _create(self, conversation: Conversation, markdown: str) -> str:
        session_id = self._client.create_session(
            [SandboxFile(path=WORKSPACE_DOCUMENT_PATH, content=markdown)]
        )
        conversation.sandbox_session_id = session_id
        conversation.sandbox_session_created_at = datetime.now(timezone.utc)
        self._db.flush()
        return session_id
