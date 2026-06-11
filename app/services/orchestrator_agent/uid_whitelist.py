"""UID format whitelist per country (业务正确性层；安全层在工具入口)."""

from __future__ import annotations

import re

# V1 占位规则；业务方确认后调整
_PATTERNS = {
    "th": re.compile(r"^[a-zA-Z0-9_-]{8,32}$"),
    "mx": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "co": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "pe": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "cl": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "br": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
}


def validate_uid(uid: str, country: str) -> bool:
    pat = _PATTERNS.get(country)
    if pat is None:
        return False
    return bool(pat.match(uid))
