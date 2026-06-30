"""Repository interfaces and in-memory implementations for M2D knowledge-base skeleton."""

from app.knowledge_base.repositories.interfaces import (
    KnowledgeBaseRepository,
    KnowledgeDocumentRepository,
    KnowledgeIngestJobRepository,
)
from app.knowledge_base.repositories.memory import (
    InMemoryKnowledgeBaseRepository,
    InMemoryKnowledgeDocumentRepository,
    InMemoryKnowledgeIngestJobRepository,
)

__all__ = [
    "InMemoryKnowledgeBaseRepository",
    "InMemoryKnowledgeDocumentRepository",
    "InMemoryKnowledgeIngestJobRepository",
    "KnowledgeBaseRepository",
    "KnowledgeDocumentRepository",
    "KnowledgeIngestJobRepository",
]
