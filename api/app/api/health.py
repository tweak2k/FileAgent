"""Endpoint kiểm tra tình trạng hoạt động của service."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Trả về trạng thái service, dùng cho health check."""
    return {"status": "ok", "service": "file-understanding-api"}
