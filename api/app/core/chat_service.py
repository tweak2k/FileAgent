"""Ghép lịch sử hội thoại, sandbox session và CodeActAgent thành một lượt trả lời."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.agent.codeact import AgentStepRecord, CodeActAgent
from app.core.agent.prompts import build_document_context
from app.core.llm.base import LLMClient
from app.core.parsing.pipeline import read_markdown
from app.core.sandbox.base import SandboxClient
from app.core.sandbox.resolver import SessionResolver
from app.db.models import AgentStep, Conversation, Message

DOCUMENT_HEAD_LINES = 30


class ChatService:
    """Ghép lịch sử hội thoại, sandbox session và agent thành một lượt trả lời."""

    def __init__(self, db: Session, llm: LLMClient, sandbox: SandboxClient, max_steps: int) -> None:
        self._db = db
        self._resolver = SessionResolver(client=sandbox, db=db)
        self._agent = CodeActAgent(llm=llm, max_steps=max_steps)

    def build_history(self, conversation: Conversation) -> list[dict[str, str]]:
        """Lấy lịch sử hội thoại theo (created_at, id) tăng dần, chỉ role user/assistant."""
        return [
            {"role": m.role, "content": m.content}
            for m in conversation.messages
            if m.role in {"user", "assistant"}
        ]

    def answer(self, conversation: Conversation, question: str) -> Message:
        markdown = read_markdown(conversation.document)

        # Lịch sử phải chụp TRƯỚC khi thêm câu hỏi mới, vì agent tự nối câu hỏi ở cuối.
        history = self.build_history(conversation)

        # Ghi và commit câu hỏi của người dùng ngay, trước khi gọi agent — để
        # câu hỏi không mất nếu agent lỗi giữa chừng.
        user_message = Message(conversation_id=conversation.id, role="user", content=question)
        self._db.add(user_message)
        self._db.commit()
        self._db.refresh(conversation)

        document_context = build_document_context(
            filename=conversation.document.filename,
            char_count=len(markdown),
            head="\n".join(markdown.splitlines()[:DOCUMENT_HEAD_LINES]),
        )

        steps: list[AgentStepRecord] = []
        try:
            result = self._agent.run(
                question=question,
                document_context=document_context,
                history=history,
                executor=lambda code: self._resolver.run_code(conversation, markdown, code),
                steps_sink=steps,
            )
        except Exception as exc:
            # Agent lỗi giữa lượt (LLM hết retry, sandbox mất kết nối ở một
            # bước sau...): các bước code TRƯỚC đó đã thực sự chạy trong
            # sandbox rồi, không được để mất — và câu hỏi người dùng (đã lưu
            # ở trên) không được để mồ côi, vì không có API xoá message nên
            # nó sẽ nằm mãi trong prompt của mọi lượt về sau nếu
            # build_history() thấy hai user liên tiếp.
            self._record_failed_turn(conversation, steps, exc)
            raise
        finally:
            # Nếu sandbox session vừa được tạo (SessionResolver._create chỉ
            # flush, không commit) rồi một bước SAU đó ném lỗi (LLM hết retry,
            # sandbox mất kết nối ở lần execute kế tiếp...), sandbox_session_id
            # (và assistant message lỗi ghi ở except phía trên, nếu có) phải
            # được commit ở đây trước khi exception bay lên. Nếu không,
            # get_db() sẽ rollback khi request kết thúc, Postgres quên mất
            # session vừa tạo trong khi session thật vẫn còn sống trên
            # python-vm — mồ côi cho tới khi reaper dọn, tốn một slot.
            self._db.commit()

        assistant_message = Message(
            conversation_id=conversation.id, role="assistant", content=result.answer
        )
        self._db.add(assistant_message)
        self._db.flush()
        self._persist_steps(assistant_message.id, result.steps)
        self._db.commit()
        self._db.refresh(assistant_message)
        return assistant_message

    def _record_failed_turn(
        self, conversation: Conversation, steps: list[AgentStepRecord], exc: Exception
    ) -> None:
        """Ghi lại các bước agent đã chạy xong cộng một assistant message báo lỗi.

        Gọi khi agent.run() ném exception giữa lượt. Chỉ add/flush — việc
        commit do khối `finally` ở answer() lo, chung với commit
        sandbox_session_id.
        """
        error_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=f"Lượt trả lời này gặp lỗi hạ tầng và không hoàn tất: {exc}",
        )
        self._db.add(error_message)
        self._db.flush()
        self._persist_steps(error_message.id, steps)

    def _persist_steps(self, message_id: int, steps: list[AgentStepRecord]) -> None:
        for step in steps:
            self._db.add(
                AgentStep(
                    message_id=message_id,
                    step_index=step.step_index,
                    code=step.code,
                    stdout=step.stdout,
                    stderr=step.stderr,
                    status=step.status,
                    duration_ms=step.duration_ms,
                )
            )

    def reset_sandbox(self, conversation: Conversation) -> None:
        self._resolver.reset(conversation)
        self._db.commit()
