"""parse_uid_file — UID 文件解析；防路径穿越 + 去重去空白。"""

from __future__ import annotations

import re

from app.core.config import settings
from app.services.orchestrator_agent.schemas import (
    ParseUidFileInput, ParseUidFileOutput,
)

_UID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_BASE = "data/id_files"


def parse_uid_file(input_data: ParseUidFileInput) -> ParseUidFileOutput:
    """Parse UID file under data/id_files/. 防路径穿越 + 去重去空白。"""
    base = (settings.project_root / _BASE).resolve()
    target = (settings.project_root / input_data.file_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise PermissionError(
            f"file_path must be under {_BASE}: got {input_data.file_path}"
        )
    if not target.exists():
        raise FileNotFoundError(f"UID file not found: {target}")
    seen: set[str] = set()
    uids: list[str] = []
    duplicates = 0
    with open(target, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or not _UID_REGEX.match(line):
                continue
            if line in seen:
                duplicates += 1
                continue
            seen.add(line)
            uids.append(line)
    return ParseUidFileOutput(
        uids=uids, source_path=str(target), duplicates_removed=duplicates,
    )
