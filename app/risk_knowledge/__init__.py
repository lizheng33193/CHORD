"""Risk-domain knowledge runtime boundaries for M2D."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "RiskEvidence",
    "RiskEvidenceScore",
    "EvidenceUsage",
    "MetadataBuildResult",
    "EvidenceBuildResult",
    "PersistedChunkRecord",
    "PersistedChunkBatchResult",
    "PersistedEmbeddingRecord",
    "PersistedEmbeddingBatchResult",
]


def __getattr__(name: str) -> Any:
    if name in {
        "RiskEvidence",
        "RiskEvidenceScore",
        "EvidenceUsage",
        "MetadataBuildResult",
        "EvidenceBuildResult",
    }:
        module = import_module("app.risk_knowledge.schemas")
        return getattr(module, name)
    if name in {
        "PersistedChunkRecord",
        "PersistedChunkBatchResult",
        "PersistedEmbeddingRecord",
        "PersistedEmbeddingBatchResult",
    }:
        module = import_module("app.risk_knowledge.persistence.schemas")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
