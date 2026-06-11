"""Utilities for validating uid inputs across API entrypoints."""

from __future__ import annotations

import re


UID_PATTERN = re.compile(r"^\d{18}$")


def is_valid_uid(uid: str | None) -> bool:
    """Return whether the uid matches the project's 18-digit rule."""
    return bool(uid and UID_PATTERN.fullmatch(str(uid).strip()))


def normalize_uid(uid: str | None) -> str:
    """Trim uid input into a normalized string."""
    return str(uid or "").strip()


def validate_uid_or_raise(uid: str | None, *, field_name: str = "uid") -> str:
    """Normalize and validate a uid, raising ValueError on mismatch."""
    normalized = normalize_uid(uid)
    if not is_valid_uid(normalized):
        raise ValueError(f"`{field_name}` must be an 18-digit numeric uid.")
    return normalized
