"""Embedding text builder for M6A shadow memory vectors."""

from __future__ import annotations

import hashlib
from typing import Any

from .schemas import MemoryEmbeddingTextResult


_SENSITIVE_KEYS = {
    "api_key",
    "access_token",
    "token",
    "password",
    "secret",
    "authorization",
}
_BLOCKED_METADATA_KEYS = {"raw_sql", "raw_citations"}
_DEFAULT_MAX_CHARS = 2000


def build_memory_embedding_text(
    memory_record: dict[str, Any],
    *,
    max_chars: int | None = None,
) -> MemoryEmbeddingTextResult:
    status = str(memory_record.get("status") or "").strip().lower()
    if status != "active":
        return MemoryEmbeddingTextResult(
            text="",
            skipped=True,
            reason="inactive_memory",
            content_hash=None,
            embedding_text_hash=None,
        )

    content = str(memory_record.get("content") or "").strip()
    if not content:
        return MemoryEmbeddingTextResult(
            text="",
            skipped=True,
            reason="empty_content",
            content_hash=None,
            embedding_text_hash=None,
        )

    metadata = dict(memory_record.get("metadata") or memory_record.get("metadata_json") or {})
    safe_metadata = _safe_metadata_items(metadata)
    tags = [str(item).strip() for item in list(memory_record.get("tags") or []) if str(item).strip()]

    lines = [
        f"Category: {str(memory_record.get('category') or 'reference').strip() or 'reference'}",
        f"Memory type: {str(memory_record.get('memory_type') or 'semantic').strip() or 'semantic'}",
        f"Source: {str(memory_record.get('source') or 'memory').strip() or 'memory'}",
    ]
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    lines.append("Content:")
    lines.append(content)
    if safe_metadata:
        lines.append("Metadata summary:")
        lines.extend(f"{key}={value}" for key, value in safe_metadata)

    text = "\n".join(lines).strip()
    text = _truncate_text(text, max_chars=max_chars or _DEFAULT_MAX_CHARS)

    return MemoryEmbeddingTextResult(
        text=text,
        skipped=False,
        reason=None,
        content_hash=_sha256(content),
        embedding_text_hash=_sha256(_normalize(text)),
    )


def _safe_metadata_items(metadata: dict[str, Any]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for key, value in sorted(metadata.items()):
        normalized_key = str(key or "").strip().lower()
        if not normalized_key:
            continue
        if normalized_key in _BLOCKED_METADATA_KEYS:
            continue
        if any(marker in normalized_key for marker in _SENSITIVE_KEYS):
            continue
        if isinstance(value, (dict, list, tuple, set)):
            continue
        text_value = str(value).strip()
        if not text_value:
            continue
        items.append((str(key), text_value))
    return items


def _truncate_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _normalize(text: str) -> str:
    return " ".join(str(text or "").split())


def _sha256(text: str) -> str:
    return f"sha256:{hashlib.sha256(str(text).encode('utf-8')).hexdigest()}"
