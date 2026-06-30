from __future__ import annotations

from app.risk_knowledge.metadata.content_hash import build_content_hash, normalize_content_for_hash


def test_normalize_content_for_hash_normalizes_line_endings_and_whitespace() -> None:
    assert normalize_content_for_hash(" A \r\n B ") == "A\nB"


def test_build_content_hash_treats_normalized_equivalents_as_same() -> None:
    assert build_content_hash(" A \r\n B ") == build_content_hash("A\nB")


def test_build_content_hash_preserves_empty_lines() -> None:
    assert build_content_hash("A\n\nB") != build_content_hash("A\nB")
