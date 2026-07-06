"""Deterministic dedupe helpers for M4-2 memory writes."""

from __future__ import annotations

import hashlib
import re
from typing import Any


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_memory_content(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "").strip().lower())


def build_memory_dedupe_key(candidate: Any) -> str:
    raw = "|".join(
        [
            _value(getattr(candidate, "memory_source_type", None)),
            _value(getattr(candidate, "authority_level", None)),
            str(getattr(candidate, "user_id", "") or ""),
            str(getattr(candidate, "project_id", "") or ""),
            str(getattr(candidate, "country", "") or ""),
            str(getattr(candidate, "source_run_id", "") or ""),
            str(getattr(candidate, "source_artifact_id", "") or ""),
            normalize_memory_content(str(getattr(candidate, "content", "") or "")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _value(item: Any) -> str:
    value = getattr(item, "value", item)
    return str(value or "")
