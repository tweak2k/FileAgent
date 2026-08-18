"""Ties conversation history, the sandbox session and the CodeAct agent into one turn."""

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
    """Ties conversation history, the sandbox session and the agent into one turn."""

    def __init__(self, db: Session, llm: LLMClient, sandbox: SandboxClient, max_steps: int) -> None:
        self._db = db
        self._resolver = SessionResolver(client=sandbox, db=db)
        self._agent = CodeActAgent(llm=llm, max_steps=max_steps)

    def build_history(self, conversation: Conversation) -> list[dict[str, str]]:
        """Return the conversation ordered by (created_at, id), user/assistant roles only."""
        return [
            {"role": m.role, "content": m.content}
            for m in conversation.messages
            if m.role in {"user", "assistant"}
        ]

    def answer(self, conversation: Conversation, question: str) -> Message:
        """Run one full turn: build the prompt, drive the agent, persist the outcome."""
        markdown = read_markdown(conversation.document)

        # History must be captured BEFORE the new question is stored, because
        # the agent appends the current question itself.
        history = self.build_history(conversation)

        # Store and commit the user's question immediately, before calling the
        # agent, so the question survives an agent failure mid-turn.
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
            # The agent failed mid-turn (LLM out of retries, sandbox lost on a
            # later step...). The earlier code steps really did run inside the
            # sandbox, so they must not be lost — and the user question stored
            # above must not be left orphaned: there is no delete-message API,
            # so a dangling user message would sit in the prompt of every
            # later turn once build_history() sees two user roles in a row.
            self._record_failed_turn(conversation, steps, exc)
            raise
        finally:
            # If the sandbox session was just created (SessionResolver._create
            # only flushes, never commits) and a LATER step raises (LLM out of
            # retries, sandbox lost on the next execute...), sandbox_session_id
            # — plus the failure message written in the except branch above,
            # if any — has to be committed here before the exception escapes.
            # Otherwise get_db() rolls back at the end of the request, Postgres
            # forgets the session while the real one is still alive on
            # python-vm: orphaned until the reaper collects it, wasting a slot.
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
        """Persist the steps that did run, plus an assistant message noting the failure.

        Called when agent.run() raises mid-turn. Only adds and flushes — the
        commit is handled by the `finally` block in answer(), together with the
        sandbox_session_id commit.
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
        """Write one agent_steps row per executed step, attached to the given message."""
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
        """Close the conversation's sandbox session and forget its id."""
        self._resolver.reset(conversation)
        self._db.commit()
