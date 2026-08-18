"""Vòng lặp CodeActAgent: reason -> code -> exec -> observe.

Ý tưởng: tài liệu có thể rất dài nên không nhét toàn bộ vào context của LLM.
Thay vào đó, agent tự viết code Python để đọc/tìm/cắt phần mình cần trong
`document.md` nằm sẵn ở sandbox. Mỗi lượt LLM trả về một block ```python thì
code đó được chạy qua `executor`, rồi stdout/stderr được đưa lại làm quan sát
cho lượt kế tiếp. Khi LLM trả lời không kèm code, đó là câu trả lời cuối.

`CodeActAgent` chỉ biết `executor` là một callable — không biết gì về sandbox
hay database, nên test được bằng hàm Python thường.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.agent.prompts import (
    STEP_LIMIT_NOTICE,
    build_observation,
    build_system_prompt,
)
from app.core.llm.base import LLMClient
from app.core.sandbox.models import ExecutionResult

# Lấy block ```python, ```py hoặc ``` trần đầu tiên trong text.
CODE_BLOCK_PATTERN = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class AgentStepRecord:
    """Ghi lại một bước reason-code-exec-observe đã thực hiện."""

    step_index: int
    code: str
    stdout: str
    stderr: str
    status: str
    duration_ms: int


@dataclass
class AgentRunResult:
    """Kết quả cuối cùng của một lượt chạy agent."""

    answer: str
    steps: list[AgentStepRecord] = field(default_factory=list)
    hit_step_limit: bool = False


def extract_code(text: str) -> str | None:
    """Lấy block ```python (hoặc ```py, hoặc ``` trần) đầu tiên trong text.

    Trả về None nếu không có block nào, hoặc block đó rỗng.
    """
    match = CODE_BLOCK_PATTERN.search(text)
    if match is None:
        return None
    code = match.group(1).strip()
    return code or None


class CodeActAgent:
    """Điều phối vòng lặp reason -> code -> exec -> observe với một LLM và một executor."""

    def __init__(self, llm: LLMClient, max_steps: int) -> None:
        self._llm = llm
        self._max_steps = max_steps

    def run(
        self,
        question: str,
        document_context: str,
        history: list[dict[str, str]],
        executor: Callable[[str], ExecutionResult],
        steps_sink: list[AgentStepRecord] | None = None,
    ) -> AgentRunResult:
        """Chạy vòng lặp cho tới khi LLM trả lời không kèm code, hoặc chạm max_steps.

        Thứ tự message: system prompt -> document context -> lịch sử hội thoại
        -> câu hỏi hiện tại (luôn là message cuối cùng khi gọi LLM lần đầu).

        `steps_sink`, nếu truyền vào, là list do caller sở hữu và sẽ được nối
        thêm ngay khi mỗi bước hoàn tất — không đợi `run()` trả về. Nhờ vậy,
        nếu LLM hoặc executor ném lỗi giữa vòng lặp, caller vẫn đọc được các
        bước đã thực sự chạy xong trước đó (xem ChatService.answer).
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "system", "content": document_context},
            *[{"role": m["role"], "content": m["content"]} for m in history],
            {"role": "user", "content": question},
        ]

        steps: list[AgentStepRecord] = steps_sink if steps_sink is not None else []
        last_text = ""

        for step_index in range(self._max_steps):
            last_text = self._llm.complete(messages)
            code = extract_code(last_text)

            if code is None:
                return AgentRunResult(answer=last_text, steps=steps, hit_step_limit=False)

            result = executor(code)
            steps.append(
                AgentStepRecord(
                    step_index=step_index,
                    code=code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    status=result.status,
                    duration_ms=result.duration_ms,
                )
            )
            messages.append({"role": "assistant", "content": last_text})
            messages.append(
                {
                    "role": "user",
                    "content": build_observation(result.stdout, result.stderr, result.timed_out),
                }
            )

        return AgentRunResult(
            answer=self._summarise_on_limit(last_text),
            steps=steps,
            hit_step_limit=True,
        )

    def _summarise_on_limit(self, last_text: str) -> str:
        """Dựng câu trả lời khi chạm max_steps: bỏ block code còn sót, thêm ghi chú chưa hoàn tất."""
        stripped = CODE_BLOCK_PATTERN.sub("", last_text).strip()
        base = stripped or "Chưa tìm ra câu trả lời trong giới hạn số bước cho phép."
        return base + STEP_LIMIT_NOTICE
