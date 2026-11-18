"""SQLAlchemy engine/session plumbing."""

from __future__ import annotations

from typing import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """Request-scoped session: commit on success, roll back on error."""
    with request.app.state.session_factory() as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise

