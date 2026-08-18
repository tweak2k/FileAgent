"""Điểm khởi tạo ứng dụng FastAPI."""

from __future__ import annotations

from fastapi import FastAPI

from app.api import health


def create_app() -> FastAPI:
    """Tạo và cấu hình instance FastAPI cho ứng dụng."""
    app = FastAPI(title="File Understanding API", version="0.1.0")
    app.include_router(health.router)
    return app


app = create_app()
