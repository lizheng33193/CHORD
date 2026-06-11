"""INDEX.md parser for knowledge base routing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

from data_acquisition_agent.knowledge_base import COUNTRY_DIR_MAP
from data_acquisition_agent.manifest import REPO_ROOT, resolve_knowledge_namespace


class IndexEntry(TypedDict):
    file: str
    title: str
    keywords: list[str]
    usage_hint: str
    token_estimate: int
    always_inject: bool


def _resolve_index_path(country: str) -> Path:
    namespace = resolve_knowledge_namespace(country)
    if namespace == "local_dev":
        return REPO_ROOT / "data_acquisition_agent/configs/local_dev/INDEX.md"
    cn = COUNTRY_DIR_MAP.get(namespace)
    if cn is None:
        return REPO_ROOT / "__nonexistent__/INDEX.md"
    return REPO_ROOT / f"data_acquisition_agent/demo0/各国数据知识库汇总/{cn}/INDEX.md"


def parse_index_md(country: str) -> list[IndexEntry]:
    index_path = _resolve_index_path(country)
    if not index_path.exists():
        return []

    content = index_path.read_text(encoding="utf-8")
    entries: list[IndexEntry] = []
    sections = re.split(r"\n## ", content)

    for sec in sections[1:]:
        lines = sec.splitlines()
        entry: IndexEntry = {
            "file": "",
            "title": "",
            "keywords": [],
            "usage_hint": "",
            "token_estimate": 0,
            "always_inject": False,
        }
        for line in lines[1:]:
            line_stripped = line.strip()
            if line_stripped.startswith("- **path**:"):
                entry["file"] = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.startswith("- **title**:"):
                entry["title"] = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.startswith("- **keywords**:"):
                kw_str = line_stripped.split(":", 1)[1].strip().strip("[]")
                entry["keywords"] = [
                    k.strip().strip("\"'")
                    for k in re.split(r"[,，]", kw_str)
                    if k.strip()
                ]
            elif line_stripped.startswith("- **usage_hint**:"):
                entry["usage_hint"] = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.startswith("- **token_estimate**:"):
                entry["token_estimate"] = int(line_stripped.split(":", 1)[1].strip())
            elif line_stripped.startswith("- **always_inject**:"):
                entry["always_inject"] = "true" in line_stripped.lower()

        if entry["file"]:
            entries.append(entry)

    return entries
