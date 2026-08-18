"""SQLAlchemy engine and session management for the application."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return the single sessionmaker, building the engine from Settings.database_url."""
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a Session that closes when the request ends.

    Closing rolls back anything not yet committed, which is why code that must
    survive a mid-request failure commits explicitly (see ChatService.answer).
    """
    factory = get_session_factory()
    with factory() as session:
        yield session
