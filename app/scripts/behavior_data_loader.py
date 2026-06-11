"""Load behavior data for one uid from repository."""

from __future__ import annotations

from typing import Any

from app.repositories.base import BaseUserRepository
from app.core.logger import get_logger


logger = get_logger(__name__)


def load_behavior_data(repository: BaseUserRepository, uid: str) -> dict[str, Any]:
    """Read behavior data and always return a dictionary."""
    payload = repository.get_behavior_data(uid) or {}
    if isinstance(payload, dict) and str(payload.get("data_status", "")).strip().lower() == "invalid":
        logger.warning(
            "Behavior data invalid for uid=%s source=%s reason=%s",
            uid,
            payload.get("source_file", ""),
            payload.get("load_error", "invalid_payload"),
        )
        return {}
    return payload
