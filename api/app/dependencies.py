"""Nơi duy nhất nối Settings vào các client thật: Parser, SandboxClient, LLMClient.

Đây là các FastAPI dependency, ghi đè được trong test bằng `app.dependency_overrides`.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.core.llm.openai_compat import OpenAICompatibleClient
from app.core.parsing.llamaparse import LlamaParseParser
from app.core.sandbox.client import HttpSandboxClient


@lru_cache(maxsize=1)
def _parser() -> LlamaParseParser:
    return LlamaParseParser(api_key=get_settings().llama_cloud_api_key)


@lru_cache(maxsize=1)
def _sandbox_client() -> HttpSandboxClient:
    settings = get_settings()
    return HttpSandboxClient(
        base_url=settings.sandbox_base_url,
        api_key=settings.sandbox_api_key,
        timeout_seconds=settings.sandbox_timeout_seconds,
    )


@lru_cache(maxsize=1)
def _llm_client() -> OpenAICompatibleClient:
    settings = get_settings()
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
    )


def get_parser() -> LlamaParseParser:
    return _parser()


def get_sandbox_client() -> HttpSandboxClient:
    return _sandbox_client()


def get_llm_client() -> OpenAICompatibleClient:
    return _llm_client()
