"""Tests for the CodeAct loop: code extraction, observations, and the step limit."""

from __future__ import annotations

from app.core.agent.codeact import CodeActAgent, extract_code
from app.core.sandbox.models import ExecutionResult
from tests.fakes import FakeLLMClient

DOC_CONTEXT = "File: hsmt.pdf, 1000 ký tự"


def ok(stdout: str) -> ExecutionResult:
    return ExecutionResult(
        status="completed", stdout=stdout, stderr="", timed_out=False, duration_ms=5
    )


def test_extract_code_lay_block_python():
    text = "Tôi sẽ đọc file.\n\n```python\nprint(1)\n```\n\nXong."

    assert extract_code(text) == "print(1)"


def test_extract_code_tra_none_khi_khong_co_block():
    assert extract_code("Đây là câu trả lời cuối cùng.") is None


def test_agent_tra_loi_ngay_khi_llm_khong_sinh_code():
    llm = FakeLLMClient(responses=["Tài liệu nói về gói thầu số 33."])
    agent = CodeActAgent(llm=llm, max_steps=8)

    result = agent.run(
        question="Gói thầu số mấy?",
        document_context=DOC_CONTEXT,
        history=[],
        executor=lambda code: ok(""),
    )

    assert result.answer == "Tài liệu nói về gói thầu số 33."
    assert result.steps == []
    assert result.hit_step_limit is False


def test_agent_chay_code_roi_dua_stdout_vao_luot_ke_tiep():
    llm = FakeLLMClient(
        responses=[
            "Để tôi đếm.\n\n```python\nprint(len(open('document.md').read()))\n```",
            "Tài liệu dài 4200 ký tự.",
        ]
    )
    agent = CodeActAgent(llm=llm, max_steps=8)
    executed: list[str] = []

    def executor(code: str) -> ExecutionResult:
        executed.append(code)
        return ok("4200\n")

    result = agent.run(
        question="Tài liệu dài bao nhiêu?",
        document_context=DOC_CONTEXT,
        history=[],
        executor=executor,
    )

    assert executed == ["print(len(open('document.md').read()))"]
    assert result.answer == "Tài liệu dài 4200 ký tự."
    assert len(result.steps) == 1
    assert result.steps[0].stdout == "4200\n"
    assert result.steps[0].step_index == 0

    observation = llm.calls[1][-1]
    assert observation["role"] == "user"
    assert "4200" in observation["content"]


def test_agent_dua_stderr_vao_observation_de_tu_sua():
    llm = FakeLLMClient(
        responses=[
            "```python\nopen('sai.md')\n```",
            "```python\nopen('document.md')\n```",
            "Đã đọc được file.",
        ]
    )
    agent = CodeActAgent(llm=llm, max_steps=8)

    def executor(code: str) -> ExecutionResult:
        if "sai.md" in code:
            return ExecutionResult(
                status="failed",
                stdout="",
                stderr="FileNotFoundError: sai.md",
                timed_out=False,
                duration_ms=3,
            )
        return ok("ok")

    result = agent.run(
        question="Đọc file", document_context=DOC_CONTEXT, history=[], executor=executor
    )

    assert result.answer == "Đã đọc được file."
    assert len(result.steps) == 2
    assert result.steps[0].status == "failed"
    assert "FileNotFoundError" in llm.calls[1][-1]["content"]


def test_agent_dung_khi_cham_max_steps():
    llm = FakeLLMClient(responses=["```python\nprint(1)\n```"] * 3)
    agent = CodeActAgent(llm=llm, max_steps=3)

    result = agent.run(
        question="q", document_context=DOC_CONTEXT, history=[], executor=lambda code: ok("1")
    )

    assert result.hit_step_limit is True
    assert len(result.steps) == 3
    assert "chưa hoàn tất" in result.answer.lower()


def test_agent_nap_lich_su_hoi_thoai_vao_prompt():
    llm = FakeLLMClient(responses=["Câu trả lời."])
    agent = CodeActAgent(llm=llm, max_steps=8)
    history = [
        {"role": "user", "content": "Câu hỏi lượt trước"},
        {"role": "assistant", "content": "Trả lời lượt trước"},
    ]

    agent.run(
        question="Câu hỏi lượt này",
        document_context=DOC_CONTEXT,
        history=history,
        executor=lambda code: ok(""),
    )

    messages = llm.calls[0]
    assert messages[0]["role"] == "system"
    contents = [m["content"] for m in messages]
    assert "Câu hỏi lượt trước" in contents
    assert "Trả lời lượt trước" in contents
    assert contents.index("Câu hỏi lượt trước") < contents.index("Câu hỏi lượt này")
    assert messages[-1]["content"] == "Câu hỏi lượt này"
