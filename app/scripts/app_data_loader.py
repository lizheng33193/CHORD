"""Load app data for one uid from repository."""

from __future__ import annotations

from typing import Any

from app.repositories.base import BaseUserRepository


def load_app_data(repository: BaseUserRepository, uid: str) -> dict[str, Any]:
    """Read app data and always return a dictionary."""
    return repository.get_app_data(uid) or {}

