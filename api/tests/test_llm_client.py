from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.core.llm.openai_compat import LLMError, OpenAICompatibleClient


@dataclass
class FakeChoiceMessage:
    content: str


@dataclass
class FakeChoice:
    message: FakeChoiceMessage


@dataclass
class FakeCompletion:
    choices: list[FakeChoice]


@dataclass
class FakeCompletions:
    responses: list[object] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeOpenAI:
    def __init__(self, responses: list[object]) -> None:
        self.completions = FakeCompletions(responses=responses)
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_complete_tra_ve_noi_dung_va_gui_dung_model():
    fake = FakeOpenAI([FakeCompletion(choices=[FakeChoice(FakeChoiceMessage("xin chào"))])])
    client = OpenAICompatibleClient(
        base_url="https://x.test/v1", api_key="k", model="vendor/model", max_tokens=100, client=fake
    )

    answer = client.complete([{"role": "user", "content": "hi"}])

    assert answer == "xin chào"
    call = fake.completions.calls[0]
    assert call["model"] == "vendor/model"
    assert call["max_tokens"] == 100
    assert call["messages"] == [{"role": "user", "content": "hi"}]


def test_complete_retry_hai_lan_roi_thanh_cong():
    fake = FakeOpenAI(
        [
            RuntimeError("mạng lỗi"),
            RuntimeError("mạng lỗi"),
            FakeCompletion(choices=[FakeChoice(FakeChoiceMessage("ok"))]),
        ]
    )
    client = OpenAICompatibleClient(
        base_url="https://x.test/v1",
        api_key="k",
        model="m",
        max_tokens=10,
        client=fake,
        backoff_seconds=0,
    )

    assert client.complete([{"role": "user", "content": "hi"}]) == "ok"
    assert len(fake.completions.calls) == 3


def test_complete_that_bai_qua_so_lan_retry_thi_nem_llm_error():
    fake = FakeOpenAI([RuntimeError("x"), RuntimeError("x"), RuntimeError("x")])
    client = OpenAICompatibleClient(
        base_url="https://x.test/v1",
        api_key="k",
        model="m",
        max_tokens=10,
        client=fake,
        backoff_seconds=0,
    )

    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "hi"}])
