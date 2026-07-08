"""Shadow-only vector indexing helpers for Orchestrator memory."""

from .embedding_text import build_memory_embedding_text
from .faiss_store import MemoryFaissStore
from .provider import (
    DeterministicMemoryEmbeddingProvider,
    MemoryEmbeddingProvider,
    build_memory_embedding_provider,
)
from .schemas import (
    MemoryEmbeddingTextResult,
    MemoryShadowCandidate,
    MemoryShadowFilteredCandidate,
    MemoryShadowSearchResult,
    MemoryVectorIndexEntry,
    MemoryVectorManifest,
    MemoryVectorMetadata,
    MemoryVectorRecord,
    MemoryVectorSearchResult,
    MemoryVectorSyncReport,
    MemoryVectorSyncResult,
    MemoryVectorSyncState,
)

__all__ = [
    "DeterministicMemoryEmbeddingProvider",
    "MemoryEmbeddingProvider",
    "MemoryEmbeddingTextResult",
    "MemoryFaissStore",
    "MemoryShadowCandidate",
    "MemoryShadowFilteredCandidate",
    "MemoryShadowSearchResult",
    "MemoryVectorIndexEntry",
    "MemoryVectorManifest",
    "MemoryVectorMetadata",
    "MemoryVectorRecord",
    "MemoryVectorSearchResult",
    "MemoryVectorSyncReport",
    "MemoryVectorSyncResult",
    "MemoryVectorSyncState",
    "build_memory_embedding_provider",
    "build_memory_embedding_text",
]
