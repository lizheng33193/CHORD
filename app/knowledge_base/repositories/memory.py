"""In-memory repositories for validating the M2D knowledge-base skeleton."""

from __future__ import annotations

from app.knowledge_base.errors import (
    DuplicateKnowledgeBaseError,
    DuplicateKnowledgeDocumentError,
    DuplicateKnowledgeDocumentVersionError,
    DuplicateKnowledgeIngestJobError,
    KnowledgeBaseNotFoundError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentVersionNotFoundError,
    KnowledgeIngestJobNotFoundError,
)
from app.knowledge_base.schemas import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestJob,
    KnowledgeIngestJobRuntimeState,
)


class InMemoryKnowledgeBaseRepository:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeBase] = {}

    def create(self, kb: KnowledgeBase) -> KnowledgeBase:
        if kb.kb_id in self._items:
            raise DuplicateKnowledgeBaseError(f"knowledge base already exists: {kb.kb_id}")
        self._items[kb.kb_id] = kb
        return kb

    def get(self, kb_id: str) -> KnowledgeBase | None:
        return self._items.get(kb_id)

    def list(self) -> list[KnowledgeBase]:
        return list(self._items.values())

    def update(self, kb: KnowledgeBase) -> KnowledgeBase:
        if kb.kb_id not in self._items:
            raise KnowledgeBaseNotFoundError(f"knowledge base not found: {kb.kb_id}")
        self._items[kb.kb_id] = kb
        return kb


class InMemoryKnowledgeDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, KnowledgeDocument] = {}
        self._versions: dict[str, KnowledgeDocumentVersion] = {}

    def create_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        if document.doc_id in self._documents:
            raise DuplicateKnowledgeDocumentError(f"document already exists: {document.doc_id}")
        self._documents[document.doc_id] = document
        return document

    def get_document(self, doc_id: str) -> KnowledgeDocument | None:
        return self._documents.get(doc_id)

    def list_documents(self, kb_id: str) -> list[KnowledgeDocument]:
        return [document for document in self._documents.values() if document.kb_id == kb_id]

    def update_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        if document.doc_id not in self._documents:
            raise KnowledgeDocumentNotFoundError(f"document not found: {document.doc_id}")
        self._documents[document.doc_id] = document
        return document

    def create_version(self, version: KnowledgeDocumentVersion) -> KnowledgeDocumentVersion:
        if version.doc_id not in self._documents:
            raise KnowledgeDocumentNotFoundError(f"document not found: {version.doc_id}")
        if version.version_id in self._versions:
            raise DuplicateKnowledgeDocumentVersionError(f"document version already exists: {version.version_id}")
        self._versions[version.version_id] = version
        return version

    def get_version(self, version_id: str) -> KnowledgeDocumentVersion | None:
        return self._versions.get(version_id)

    def list_versions(self, doc_id: str) -> list[KnowledgeDocumentVersion]:
        return [version for version in self._versions.values() if version.doc_id == doc_id]

    def update_version(self, version: KnowledgeDocumentVersion) -> KnowledgeDocumentVersion:
        if version.version_id not in self._versions:
            raise KnowledgeDocumentVersionNotFoundError(f"document version not found: {version.version_id}")
        self._versions[version.version_id] = version
        return version


class InMemoryKnowledgeIngestJobRepository:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeIngestJob] = {}

    def create(self, job: KnowledgeIngestJob) -> KnowledgeIngestJob:
        if job.job_id in self._items:
            raise DuplicateKnowledgeIngestJobError(f"ingest job already exists: {job.job_id}")
        self._items[job.job_id] = job
        return job

    def get(self, job_id: str) -> KnowledgeIngestJob | None:
        return self._items.get(job_id)

    def update(self, job: KnowledgeIngestJob) -> KnowledgeIngestJob:
        if job.job_id not in self._items:
            raise KnowledgeIngestJobNotFoundError(f"ingest job not found: {job.job_id}")
        self._items[job.job_id] = job
        return job

    def list_by_version(self, version_id: str) -> list[KnowledgeIngestJob]:
        return [job for job in self._items.values() if job.version_id == version_id]


class InMemoryKnowledgeIngestJobRuntimeStateRepository:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeIngestJobRuntimeState] = {}

    def get(self, job_id: str) -> KnowledgeIngestJobRuntimeState | None:
        return self._items.get(job_id)

    def upsert(self, state: KnowledgeIngestJobRuntimeState) -> KnowledgeIngestJobRuntimeState:
        self._items[state.job_id] = state
        return state
