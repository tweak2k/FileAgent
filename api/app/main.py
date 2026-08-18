"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from app.api import conversations, documents, health


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="File Understanding API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(conversations.router)
    return app


app = create_app()
