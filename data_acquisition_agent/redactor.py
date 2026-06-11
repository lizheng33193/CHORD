"""L1 credential redaction. See Design Doc §7.1."""

from __future__ import annotations

import re
from pathlib import Path


PATTERNS = [
    (re.compile(r"""\bhost\s*=\s*['"](?:\d{1,3}\.){3}\d{1,3}['"]"""), "host='<DB_HOST>'"),
    (re.compile(r"\bport\s*=\s*\d{2,6}\b"), "port=<DB_PORT>"),
    (re.compile(r"""\buser\s*=\s*['"]e_[A-Za-z0-9_]*['"]"""), "user='<DB_USER>'"),
    (re.compile(r"""\bpassword\s*=\s*['"][^'"]*['"]"""), "password='<DB_PASSWORD>'"),
    (re.compile(r"""\bdatabase\s*=\s*['"]dm_[A-Za-z0-9_]*['"]"""), "database='<DB_NAME>'"),
    (re.compile(r"""\btoken\s*=\s*['"][^'"]+['"]"""), "token='<TOKEN>'"),
    (re.compile(r"""\bapi_key\s*=\s*['"][^'"]+['"]"""), "api_key='<API_KEY>'"),
    (re.compile(r"""\baccess_token\s*=\s*['"][^'"]+['"]"""), "access_token='<ACCESS_TOKEN>'"),
    (re.compile(r"""\bsecret\s*=\s*['"][^'"]+['"]"""), "secret='<SECRET>'"),
    (re.compile(r"""\bkey\s*=\s*['"][^'"]+['"]"""), "key='<KEY>'"),
    (re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+"), "Authorization: Bearer <BEARER_TOKEN>"),
]


def redact(text: str) -> tuple[str, int]:
    hits = 0
    for pat, repl in PATTERNS:
        text, n = pat.subn(repl, text)
        hits += n
    return text, hits


def redact_file(path: str) -> tuple[str, int]:
    return redact(Path(path).read_text(encoding="utf-8"))
