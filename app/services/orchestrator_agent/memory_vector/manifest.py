"""Manifest helpers for memory vector stores."""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import MemoryVectorManifest


def load_manifest(path: Path) -> MemoryVectorManifest:
    return MemoryVectorManifest(**json.loads(path.read_text(encoding="utf-8")))


def save_manifest(path: Path, manifest: MemoryVectorManifest) -> None:
    path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
