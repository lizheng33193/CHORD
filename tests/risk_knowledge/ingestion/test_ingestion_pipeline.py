from __future__ import annotations

import pytest

from app.knowledge_base.repositories.memory import (
    InMemoryKnowledgeDocumentRepository,
    InMemoryKnowledgeIngestJobRepository,
)
from app.knowledge_base.schemas import (
    DocumentVersionStatus,
    IngestJobStatus,
    PermissionScope,
    SourceType,
)
from app.knowledge_base.services.document_service import DocumentService
from app.knowledge_base.services.ingest_job_service import IngestJobService
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.errors import SwxyParserExecutionError
from app.risk_knowledge.ingestion.ingestion_pipeline import SwxyIngestionPipeline
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter


def _setup_document_service() -> tuple[InMemoryKnowledgeDocumentRepository, DocumentService]:
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
    service.create_document_version(
        version_id="risk_guide_202607",
        doc_id="risk_guide",
        kb_id="risk_domain_knowledge",
        version="2026-07",
        file_hash="sha256:test",
        file_uri="knowledge/risk/risk_guide.pdf",
        parser_version=None,
        chunker_version=None,
        embedding_model=None,
        embedding_dim=None,
        index_name=None,
    )
    return repo, service


def _setup_job_service() -> tuple[InMemoryKnowledgeIngestJobRepository, IngestJobService]:
    repo = InMemoryKnowledgeIngestJobRepository()
    service = IngestJobService(repo)
    service.create_job(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        job_id="job_1",
    )
    return repo, service


def _context() -> IngestionContext:
    return IngestionContext(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        job_id="job_1",
        file_path="/tmp/risk_guide.pdf",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
    )


def test_pipeline_success_transitions_version_and_job_to_parsed() -> None:
    doc_repo, document_service = _setup_document_service()
    job_repo, job_service = _setup_job_service()
    adapter = SwxyParserAdapter(chunker=lambda **_kwargs: [{"content_with_weight": "贷后风险识别是指...", "page_num_int": 12}])
    pipeline = SwxyIngestionPipeline(
        adapter=adapter,
        document_service=document_service,
        ingest_job_service=job_service,
    )

    parsed = pipeline.parse_document(_context())

    version = doc_repo.get_version("risk_guide_202607")
    job = job_repo.get("job_1")
    assert parsed.raw_chunks[0].raw_content == "贷后风险识别是指..."
    assert version is not None
    assert job is not None
    assert version.status == DocumentVersionStatus.PARSED
    assert job.status == IngestJobStatus.PARSED


def test_pipeline_failure_marks_failed_without_overriding_original_error() -> None:
    doc_repo, document_service = _setup_document_service()
    job_repo, job_service = _setup_job_service()
    adapter = SwxyParserAdapter(chunker=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("parser boom")))
    pipeline = SwxyIngestionPipeline(
        adapter=adapter,
        document_service=document_service,
        ingest_job_service=job_service,
    )

    with pytest.raises(SwxyParserExecutionError) as exc_info:
        pipeline.parse_document(_context())

    version = doc_repo.get_version("risk_guide_202607")
    job = job_repo.get("job_1")
    assert "parser boom" in str(exc_info.value)
    assert version is not None
    assert job is not None
    assert version.status == DocumentVersionStatus.FAILED
    assert job.status == IngestJobStatus.FAILED
    assert job.error_message is not None


def test_pipeline_best_effort_failed_marking_preserves_original_error() -> None:
    _, document_service = _setup_document_service()
    _, job_service = _setup_job_service()
    adapter = SwxyParserAdapter(chunker=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("parser boom")))
    original_transition = document_service.transition_version

    def _transition_then_break(version_id: str, next_status: DocumentVersionStatus):
        result = original_transition(version_id, next_status)
        if next_status == DocumentVersionStatus.FAILED:
            raise RuntimeError("failed marking broke")
        return result

    document_service.transition_version = _transition_then_break  # type: ignore[method-assign]
    pipeline = SwxyIngestionPipeline(
        adapter=adapter,
        document_service=document_service,
        ingest_job_service=job_service,
    )

    with pytest.raises(SwxyParserExecutionError) as exc_info:
        pipeline.parse_document(_context())

    assert "parser boom" in str(exc_info.value)
