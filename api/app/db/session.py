"""Quản lý engine và session SQLAlchemy dùng cho toàn ứng dụng."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Trả về sessionmaker duy nhất, tạo engine từ database_url trong Settings."""
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield một Session và tự đóng khi request kết thúc."""
    factory = get_session_factory()
    with factory() as session:
        yield session
