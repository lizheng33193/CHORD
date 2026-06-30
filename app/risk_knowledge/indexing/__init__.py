"""FAISS indexing foundation for M2D-8."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "FaissIndexError",
    "FaissManifestMismatchError",
    "FaissUnavailableError",
    "FaissIndexStore",
    "build_faiss_fingerprint",
]


def __getattr__(name: str) -> Any:
    if name in {"FaissIndexError", "FaissManifestMismatchError", "FaissUnavailableError"}:
        module = import_module("app.risk_knowledge.indexing.errors")
        return getattr(module, name)
    if name in {"FaissIndexStore", "build_faiss_fingerprint"}:
        module = import_module("app.risk_knowledge.indexing.faiss_store")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
