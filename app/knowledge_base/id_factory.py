"""Deterministic ID helpers for the M2D knowledge-base skeleton."""

from __future__ import annotations

import re


_NON_ID_CHARS = re.compile(r"[^a-z0-9]+")


def normalize_id_part(value: str) -> str:
    normalized = _NON_ID_CHARS.sub("_", value.strip().lower()).strip("_")
    return normalized or "item"


def build_doc_id(doc_title: str, file_hash: str | None = None) -> str:
    base = normalize_id_part(doc_title)
    if not file_hash:
        return base
    suffix = normalize_id_part(file_hash.replace("sha256:", ""))[:8]
    return f"{base}_{suffix}" if suffix else base


def build_version_id(doc_id: str, version: str) -> str:
    return f"{normalize_id_part(doc_id)}_{normalize_id_part(version)}"


def build_chunk_id(version_id: str, chunk_order: int) -> str:
    return f"{normalize_id_part(version_id)}_chunk_{chunk_order:06d}"


def build_ingest_job_id(version_id: str) -> str:
    return f"ingest_{normalize_id_part(version_id)}"
