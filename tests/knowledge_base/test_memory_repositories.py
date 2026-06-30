from __future__ import annotations

import pytest

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
from app.knowledge_base.repositories.memory import (
    InMemoryKnowledgeBaseRepository,
    InMemoryKnowledgeDocumentRepository,
    InMemoryKnowledgeIngestJobRepository,
)
from app.knowledge_base.schemas import (
    DocumentStatus,
    DocumentVersionStatus,
    IngestJobStatus,
    IngestStep,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeBaseType,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestJob,
    PermissionScope,
    SourceType,
)


def _build_kb() -> KnowledgeBase:
    return KnowledgeBase(
        kb_id="risk_domain_knowledge",
        kb_name="风控领域知识库",
        kb_type=KnowledgeBaseType.RISK_DOMAIN,
        description="Risk-domain document knowledge base for M2D.",
        status=KnowledgeBaseStatus.ACTIVE,
        index_alias="chord_m2d_risk_knowledge_active",
    )


def _build_document(*, current_version_id: str | None = None, status: DocumentStatus = DocumentStatus.INACTIVE) -> KnowledgeDocument:
    return KnowledgeDocument(
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        current_version_id=current_version_id,
        status=status,
        permission_scope=PermissionScope.INTERNAL,
    )


def _build_version(version_id: str, *, status: DocumentVersionStatus = DocumentVersionStatus.UPLOADED) -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion(
        version_id=version_id,
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version=version_id.removeprefix("risk_guide_"),
        file_hash=f"sha256:{version_id}",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy_deepdoc_v1",
        chunker_version="m2d_chunker_v1",
        embedding_model="text-embedding-v3",
        embedding_dim=1024,
        index_name="chord_m2d_risk_knowledge_v1",
        status=status,
    )


def _build_job(job_id: str, *, status: IngestJobStatus = IngestJobStatus.UPLOADED, step: IngestStep = IngestStep.UPLOADED) -> KnowledgeIngestJob:
    return KnowledgeIngestJob(
        job_id=job_id,
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202606",
        status=status,
        current_step=step,
        error_message=None,
    )


def test_kb_memory_repository_supports_create_get_list_update() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    kb = _build_kb()

    repo.create(kb)
    updated = kb.model_copy(update={"description": "updated"})
    repo.update(updated)

    assert repo.get(kb.kb_id) == updated
    assert repo.list() == [updated]


def test_kb_memory_repository_duplicate_and_missing_update_are_explicit() -> None:
    repo = InMemoryKnowledgeBaseRepository()
    kb = _build_kb()
    repo.create(kb)

    with pytest.raises(DuplicateKnowledgeBaseError):
        repo.create(kb)
    with pytest.raises(KnowledgeBaseNotFoundError):
        repo.update(_build_kb().model_copy(update={"kb_id": "missing"}))
    assert repo.get("missing") is None


def test_document_memory_repository_supports_document_and_version_crud() -> None:
    repo = InMemoryKnowledgeDocumentRepository()
    document = _build_document()
    version = _build_version("risk_guide_202606")

    repo.create_document(document)
    repo.create_version(version)

    updated_document = document.model_copy(update={"status": DocumentStatus.ACTIVE})
    updated_version = version.model_copy(update={"status": DocumentVersionStatus.ACTIVE})
    repo.update_document(updated_document)
    repo.update_version(updated_version)

    assert repo.get_document(document.doc_id) == updated_document
    assert repo.list_documents(document.kb_id) == [updated_document]
    assert repo.get_version(version.version_id) == updated_version
    assert repo.list_versions(document.doc_id) == [updated_version]


def test_document_memory_repository_duplicate_and_missing_update_are_explicit() -> None:
    repo = InMemoryKnowledgeDocumentRepository()
    document = _build_document()
    version = _build_version("risk_guide_202606")
    repo.create_document(document)
    repo.create_version(version)

    with pytest.raises(DuplicateKnowledgeDocumentError):
        repo.create_document(document)
    with pytest.raises(DuplicateKnowledgeDocumentVersionError):
        repo.create_version(version)
    with pytest.raises(KnowledgeDocumentNotFoundError):
        repo.update_document(document.model_copy(update={"doc_id": "missing"}))
    with pytest.raises(KnowledgeDocumentVersionNotFoundError):
        repo.update_version(version.model_copy(update={"version_id": "missing"}))
    assert repo.get_document("missing") is None
    assert repo.get_version("missing") is None


def test_job_memory_repository_supports_create_get_list_update() -> None:
    repo = InMemoryKnowledgeIngestJobRepository()
    job = _build_job("job_1")
    repo.create(job)

    updated = job.model_copy(update={"status": IngestJobStatus.PARSING, "current_step": IngestStep.PARSING})
    repo.update(updated)

    assert repo.get(job.job_id) == updated
    assert repo.list_by_version(job.version_id) == [updated]


def test_job_memory_repository_duplicate_and_missing_update_are_explicit() -> None:
    repo = InMemoryKnowledgeIngestJobRepository()
    job = _build_job("job_1")
    repo.create(job)

    with pytest.raises(DuplicateKnowledgeIngestJobError):
        repo.create(job)
    with pytest.raises(KnowledgeIngestJobNotFoundError):
        repo.update(job.model_copy(update={"job_id": "missing"}))
    assert repo.get("missing") is None
