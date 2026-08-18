"""Tests for prompt building, especially observation truncation."""

from __future__ import annotations

from app.core.agent.prompts import OBSERVATION_MAX_CHARS, build_observation


def test_build_observation_khong_cat_khi_ngan():
    result = build_observation("kết quả ngắn", "", timed_out=False)

    assert "kết quả ngắn" in result
    assert "cắt bớt" not in result


def test_build_observation_cat_bot_stdout_qua_dai():
    """A long print() must be truncated, or the whole document lands in the next
    prompt and the provider is likely to answer 400."""
    stdout = "x" * (OBSERVATION_MAX_CHARS + 5000)

    result = build_observation(stdout, "", timed_out=False)

    assert "cắt bớt" in result
    assert len(result) < len(stdout)
    assert stdout not in result


def test_build_observation_cat_bot_stderr_qua_dai():
    stderr = "e" * (OBSERVATION_MAX_CHARS + 5000)

    result = build_observation("", stderr, timed_out=False)

    assert "cắt bớt" in result
    assert stderr not in result
