"""Declarative base shared by every ORM model.

Alembic's autogenerate reads `Base.metadata`, so every model module must be
imported before a migration is generated (see api/alembic/env.py).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""
