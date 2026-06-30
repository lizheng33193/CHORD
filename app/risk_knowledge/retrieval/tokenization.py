"""Tokenizer helpers for M2D-10 BM25 retrieval."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokenize_for_bm25(text: str) -> list[str]:
    normalized = (text or "").lower()
    tokens: list[str] = []
    tokens.extend(_WORD_RE.findall(normalized))

    cjk_chars = [char for char in normalized if _is_cjk(char)]
    tokens.extend(cjk_chars)
    tokens.extend(
        cjk_chars[index] + cjk_chars[index + 1]
        for index in range(len(cjk_chars) - 1)
    )
    return tokens


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return 0x4E00 <= codepoint <= 0x9FFF
