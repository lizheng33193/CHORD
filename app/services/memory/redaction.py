"""Narrow secret detection for M4-2 write gating."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRedactionResult:
    content: str
    redacted: bool
    rejected: bool
    reason: str | None = None
    findings: tuple[str, ...] = ()


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("password", re.compile(r"password\s*=\s*\S+", re.IGNORECASE)),
    ("secret", re.compile(r"secret\s*=\s*\S+", re.IGNORECASE)),
    ("api_key", re.compile(r"api_key\s*=\s*\S+", re.IGNORECASE)),
    ("token", re.compile(r"token\s*=\s*\S+", re.IGNORECASE)),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b")),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=]{8,}\b", re.IGNORECASE)),
    ("google_ai", re.compile(r"AIza[0-9A-Za-z_\-]{8,}")),
    ("private_key", re.compile(r"BEGIN PRIVATE KEY", re.IGNORECASE)),
)


def redact_memory_content(content: str) -> MemoryRedactionResult:
    findings = tuple(name for name, pattern in _PATTERNS if pattern.search(str(content or "")))
    if findings:
        return MemoryRedactionResult(
            content=str(content or ""),
            redacted=False,
            rejected=True,
            reason="secret-like content detected",
            findings=findings,
        )
    return MemoryRedactionResult(content=str(content or ""), redacted=False, rejected=False)
