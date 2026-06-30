from __future__ import annotations

import pytest

from app.knowledge_base.errors import InvalidKnowledgeBaseStateTransition
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
    PermissionScope,
    SourceType,
)
from app.knowledge_base.services.document_service import DocumentService
from app.knowledge_base.services.ingest_job_service import IngestJobService
from app.knowledge_base.services.knowledge_base_service import KnowledgeBaseService


def test_default_kb_creation_is_idempotent() -> None:
    service = KnowledgeBaseService(InMemoryKnowledgeBaseRepository())

    first = service.ensure_default_risk_domain_knowledge_base()
    second = service.ensure_default_risk_domain_knowledge_base()

    assert first == second
    assert len(service.list_knowledge_bases()) == 1


def test_register_document_records_metadata_only() -> None:
    service = DocumentService(InMemoryKnowledgeDocumentRepository())

    document = service.register_document(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        permission_scope=PermissionScope.INTERNAL,
    )

    assert document.current_version_id is None
    assert document.status == DocumentStatus.INACTIVE


def test_create_document_version_starts_parsed() -> None:
    repo = InMemoryKnowledgeDocumentRepository()
    service = DocumentService(repo)
    service.register_document(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        permission_scope=PermissionScope.INTERNAL,
    )

    version = service.create_document_version(
        version_id="risk_guide_202606",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-06",
        file_hash="sha256:test",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy_deepdoc_v1",
        chunker_version="m2d_chunker_v1",
        embedding_model="text-embedding-v3",
        embedding_dim=1024,
        index_name="chord_m2d_risk_knowledge_v1",
    )

    assert version.status == DocumentVersionStatus.PARSED


def test_activate_version_updates_current_version_and_deprecates_sibling() -> None:
    repo = InMemoryKnowledgeDocumentRepository()
    service = DocumentService(repo)
    service.register_document(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        permission_scope=PermissionScope.INTERNAL,
    )
    first = service.create_document_version(
        version_id="risk_guide_202605",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-05",
        file_hash="sha256:v1",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy_deepdoc_v1",
        chunker_version="m2d_chunker_v1",
        embedding_model="text-embedding-v3",
        embedding_dim=1024,
        index_name="chord_m2d_risk_knowledge_v1",
    )
    second = service.create_document_version(
        version_id="risk_guide_202606",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-06",
        file_hash="sha256:v2",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy_deepdoc_v1",
        chunker_version="m2d_chunker_v1",
        embedding_model="text-embedding-v3",
        embedding_dim=1024,
        index_name="chord_m2d_risk_knowledge_v1",
    )
    repo.update_version(first.model_copy(update={"status": DocumentVersionStatus.INDEXED}))
    repo.update_version(second.model_copy(update={"status": DocumentVersionStatus.INDEXED}))

    service.activate_version(first.version_id)
    activated = service.activate_version(second.version_id)

    document = repo.get_document("risk_guide")
    older = repo.get_version(first.version_id)

    assert activated.status == DocumentVersionStatus.ACTIVE
    assert document is not None
    assert document.current_version_id == second.version_id
    assert document.status == DocumentStatus.ACTIVE
    assert older is not None
    assert older.status == DocumentVersionStatus.INDEXED


def test_deprecate_version_updates_version_status() -> None:
    repo = InMemoryKnowledgeDocumentRepository()
    service = DocumentService(repo)
    service.register_document(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        permission_scope=PermissionScope.INTERNAL,
    )
    version = service.create_document_version(
        version_id="risk_guide_202606",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-06",
        file_hash="sha256:test",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy_deepdoc_v1",
        chunker_version="m2d_chunker_v1",
        embedding_model="text-embedding-v3",
        embedding_dim=1024,
        index_name="chord_m2d_risk_knowledge_v1",
    )
    repo.update_version(version.model_copy(update={"status": DocumentVersionStatus.INDEXED}))
    service.activate_version(version.version_id)

    deprecated = service.deprecate_version(version.version_id)

    assert deprecated.status == DocumentVersionStatus.DEPRECATED


def test_transition_version_updates_status_without_touching_document_pointer() -> None:
    repo = InMemoryKnowledgeDocumentRepository()
    service = DocumentService(repo)
    service.register_document(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        doc_title="智能风控指南",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
        source_uri="knowledge/risk/risk_guide.pdf",
        permission_scope=PermissionScope.INTERNAL,
    )
    version = service.create_document_version(
        version_id="risk_guide_202606",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-06",
        file_hash="sha256:test",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version="swxy_deepdoc_v1",
        chunker_version="m2d_chunker_v1",
        embedding_model="text-embedding-v3",
        embedding_dim=1024,
        index_name="chord_m2d_risk_knowledge_v1",
    )

    indexing = service.transition_version(version.version_id, DocumentVersionStatus.INDEXING)
    parsed = service.transition_version(version.version_id, DocumentVersionStatus.INDEXED)
    document = repo.get_document("risk_guide")

    assert indexing.status == DocumentVersionStatus.INDEXING
    assert parsed.status == DocumentVersionStatus.INDEXED
    assert document is not None
    assert document.current_version_id is None


def test_create_job_starts_pending() -> None:
    service = IngestJobService(InMemoryKnowledgeIngestJobRepository())

    job = service.create_job(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202606",
        job_id="job_1",
    )

    assert job.status == IngestJobStatus.PENDING
    assert job.current_step == IngestStep.QUEUED


def test_transition_job_enforces_lifecycle() -> None:
    service = IngestJobService(InMemoryKnowledgeIngestJobRepository())
    job = service.create_job(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202606",
        job_id="job_1",
    )

    moved = service.transition_job(job.job_id, IngestJobStatus.RUNNING)
    assert moved.status == IngestJobStatus.RUNNING
    assert moved.current_step == IngestStep.LOCK_ACQUIRED

    with pytest.raises(InvalidKnowledgeBaseStateTransition):
        service.transition_job(job.job_id, IngestJobStatus.PENDING)


def test_fail_job_sets_failed_state_and_error_message() -> None:
    service = IngestJobService(InMemoryKnowledgeIngestJobRepository())
    job = service.create_job(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202606",
        job_id="job_1",
    )

    failed = service.fail_job(job.job_id, "parse failed")

    assert failed.status == IngestJobStatus.FAILED
    assert failed.current_step == IngestStep.FAILED
    assert failed.error_message == "parse failed"
