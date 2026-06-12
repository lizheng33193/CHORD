"""Database helpers for auth domain models."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Auth declarative base."""


_ENGINE: Engine | None = None
_SESSIONMAKER: sessionmaker[Session] | None = None
_ENGINE_URL: str | None = None


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


def get_auth_engine() -> Engine:
    global _ENGINE, _ENGINE_URL

    url = settings.resolved_auth_database_url
    if _ENGINE is None or _ENGINE_URL != url:
        if _ENGINE is not None:
            _ENGINE.dispose()
        _ENGINE = create_engine(url, **_engine_kwargs(url))
        _ENGINE_URL = url
    return _ENGINE


def _get_sessionmaker() -> sessionmaker[Session]:
    global _SESSIONMAKER

    if _SESSIONMAKER is None:
        _SESSIONMAKER = sessionmaker(bind=get_auth_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
    return _SESSIONMAKER


def AuthSessionLocal() -> Session:
    return _get_sessionmaker()()


def reset_auth_engine() -> None:
    global _ENGINE, _SESSIONMAKER, _ENGINE_URL

    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSIONMAKER = None
    _ENGINE_URL = None


def ensure_auth_database() -> None:
    url = make_url(settings.resolved_auth_database_url)
    if not str(url.drivername).startswith("mysql"):
        return
    database = url.database
    admin_url = url.set(database=None)
    engine = create_engine(admin_url.render_as_string(hide_password=False), **_engine_kwargs(str(admin_url)))
    try:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    finally:
        engine.dispose()


def create_auth_schema() -> None:
    ensure_auth_database()
    from app.auth import models  # noqa: F401
    from app.data_agent import models as data_agent_models  # noqa: F401

    Base.metadata.create_all(bind=get_auth_engine())


def get_db() -> Generator[Session, None, None]:
    db = AuthSessionLocal()
    try:
        yield db
    finally:
        db.close()
