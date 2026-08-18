"""Smoke tests requiring the compose stack and python-vm to be running."""

from __future__ import annotations

import os

import httpx
import pytest

API_URL = os.getenv("SMOKE_API_URL", "http://localhost:8000")
SANDBOX_URL = os.getenv("SMOKE_SANDBOX_URL", "http://localhost:8081")

pytestmark = pytest.mark.integration


def test_api_health_song():
    response = httpx.get(f"{API_URL}/health", timeout=10)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sandbox_python_vm_song():
    response = httpx.get(f"{SANDBOX_URL}/health", timeout=10)

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_danh_sach_tai_lieu_goi_duoc():
    response = httpx.get(f"{API_URL}/documents", timeout=30)

    assert response.status_code == 200
    assert isinstance(response.json(), list)
