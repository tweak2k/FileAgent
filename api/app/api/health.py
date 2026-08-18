"""Liveness endpoint used by compose healthchecks and by the UI on startup."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the service is up. Does not touch the database."""
    return {"status": "ok", "service": "file-understanding-api"}
