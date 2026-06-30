"""Lifecycle-aware parser/chunker ingestion pipeline for M2D-6."""

from __future__ import annotations

import logging

from app.knowledge_base.schemas import DocumentVersionStatus, IngestJobStatus
from app.knowledge_base.services.document_service import DocumentService
from app.knowledge_base.services.ingest_job_service import IngestJobService
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.errors import RiskKnowledgeIngestionError
from app.risk_knowledge.ingestion.schemas import ParsedDocument
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter

logger = logging.getLogger(__name__)


class SwxyIngestionPipeline:
    def __init__(
        self,
        *,
        adapter: SwxyParserAdapter,
        document_service: DocumentService,
        ingest_job_service: IngestJobService,
    ) -> None:
        self._adapter = adapter
        self._document_service = document_service
        self._ingest_job_service = ingest_job_service

    def parse_document(self, context: IngestionContext) -> ParsedDocument:
        try:
            self._ingest_job_service.transition_job(context.job_id, IngestJobStatus.RUNNING)
            parsed = self._adapter.parse(context)
            self._document_service.transition_version(context.version_id, DocumentVersionStatus.PARSED)
            self._ingest_job_service.transition_job(context.job_id, IngestJobStatus.COMPLETED)
            return parsed
        except Exception as exc:
            self._best_effort_mark_failed(context, exc)
            if isinstance(exc, RiskKnowledgeIngestionError):
                raise
            raise RiskKnowledgeIngestionError(f"M2D-6 ingestion pipeline failed: {exc}") from exc

    def _best_effort_mark_failed(self, context: IngestionContext, original_exc: Exception) -> None:
        try:
            self._document_service.transition_version(context.version_id, DocumentVersionStatus.FAILED)
        except Exception as exc:
            logger.warning("best-effort version failed marking failed version_id=%s error=%s", context.version_id, exc)
        try:
            self._ingest_job_service.fail_job(context.job_id, str(original_exc))
        except Exception as exc:
            logger.warning("best-effort job failed marking failed job_id=%s error=%s", context.job_id, exc)
