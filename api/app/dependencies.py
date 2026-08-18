"""The single place where Settings is wired into the real clients.

Parser, SandboxClient and LLMClient are constructed here and nowhere else, so
swapping a provider touches exactly one file. These are FastAPI dependencies,
which tests replace through `app.dependency_overrides`.

Each client is cached for the process lifetime: they hold an httpx connection
pool that is meant to be reused across requests.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.core.llm.openai_compat import OpenAICompatibleClient
from app.core.parsing.llamaparse import LlamaParseParser
from app.core.sandbox.client import HttpSandboxClient


@lru_cache(maxsize=1)
def _parser() -> LlamaParseParser:
    """Build the LlamaParse parser from settings, once per process."""
    return LlamaParseParser(api_key=get_settings().llama_cloud_api_key)


@lru_cache(maxsize=1)
def _sandbox_client() -> HttpSandboxClient:
    """Build the python-vm HTTP client from settings, once per process."""
    settings = get_settings()
    return HttpSandboxClient(
        base_url=settings.sandbox_base_url,
        api_key=settings.sandbox_api_key,
        timeout_seconds=settings.sandbox_timeout_seconds,
    )


@lru_cache(maxsize=1)
def _llm_client() -> OpenAICompatibleClient:
    """Build the OpenAI-compatible LLM client from settings, once per process."""
    settings = get_settings()
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
    )


def get_parser() -> LlamaParseParser:
    """FastAPI dependency yielding the shared parser."""
    return _parser()


def get_sandbox_client() -> HttpSandboxClient:
    """FastAPI dependency yielding the shared sandbox client."""
    return _sandbox_client()


def get_llm_client() -> OpenAICompatibleClient:
    """FastAPI dependency yielding the shared LLM client."""
    return _llm_client()
