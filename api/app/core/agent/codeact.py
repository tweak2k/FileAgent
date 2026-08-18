"""CodeAct agent loop: reason -> code -> exec -> observe.

The idea: a document can be very long, so we never push its full text into
the LLM context. Instead the agent writes Python code to read, search and
slice the parts it needs from `document.md`, which already sits in the
sandbox workspace. Whenever the LLM replies with a ```python block, that
code runs through `executor` and its stdout/stderr comes back as the
observation for the next turn. A reply without a code block is the final
answer.

`CodeActAgent` only knows `executor` as a callable — it knows nothing about
the sandbox or the database, which makes it testable with a plain Python
function.
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

# Matches the first ```python, ```py or bare ``` block in a piece of text.
CODE_BLOCK_PATTERN = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class AgentStepRecord:
    """One completed reason-code-exec-observe step."""

    step_index: int
    code: str
    stdout: str
    stderr: str
    status: str
    duration_ms: int


@dataclass
class AgentRunResult:
    """Final outcome of a single agent run."""

    answer: str
    steps: list[AgentStepRecord] = field(default_factory=list)
    hit_step_limit: bool = False


def extract_code(text: str) -> str | None:
    """Return the first ```python (or ```py, or bare ```) block in the text.

    Returns None when there is no block at all, or when the block is empty.
    """
    match = CODE_BLOCK_PATTERN.search(text)
    if match is None:
        return None
    code = match.group(1).strip()
    return code or None


class CodeActAgent:
    """Drives the reason -> code -> exec -> observe loop over an LLM and an executor."""

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
        """Loop until the LLM answers without code, or until max_steps is reached.

        Message order: system prompt -> document context -> conversation
        history -> current question (always the last message on the first LLM
        call).

        `steps_sink`, when provided, is a caller-owned list appended to as soon
        as each step completes — not when `run()` returns. That way, if the LLM
        or the executor raises mid-loop, the caller can still read the steps
        that actually ran (see ChatService.answer).
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
        """Build the answer when max_steps is hit: drop leftover code blocks, append the notice."""
        stripped = CODE_BLOCK_PATTERN.sub("", last_text).strip()
        base = stripped or "Chưa tìm ra câu trả lời trong giới hạn số bước cho phép."
        return base + STEP_LIMIT_NOTICE
