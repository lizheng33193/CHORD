"""Deterministic content normalization and hashing helpers for M2D-7."""

from __future__ import annotations

import hashlib


def normalize_content_for_hash(content: str) -> str:
    normalized_newlines = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [line.strip() for line in normalized_newlines.split("\n")]
    return "\n".join(normalized_lines).strip()


def build_content_hash(content: str) -> str:
    normalized = normalize_content_for_hash(content)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
