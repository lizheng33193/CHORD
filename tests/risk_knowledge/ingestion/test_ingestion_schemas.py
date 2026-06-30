from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.knowledge_base.schemas import SourceType
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.schemas import ParsedDocument, RawParsedChunk, SourceDocumentRef


def test_ingestion_context_can_be_created() -> None:
    context = IngestionContext(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        job_id="job_1",
        file_path="/tmp/risk_guide.pdf",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
    )

    assert context.parser_name == "swxy"


def test_source_document_ref_can_be_created() -> None:
    source = SourceDocumentRef(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        file_path="/tmp/risk_guide.pdf",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
    )

    assert source.source_type == SourceType.PDF


def test_raw_parsed_chunk_and_parsed_document_can_be_created() -> None:
    source = SourceDocumentRef(
        kb_id="risk_domain_knowledge",
        doc_id="risk_guide",
        version_id="risk_guide_202607",
        file_path="/tmp/risk_guide.pdf",
        doc_name="risk_guide.pdf",
        source_type=SourceType.PDF,
    )
    chunk = RawParsedChunk(
        chunk_order=1,
        raw_content="贷后风险识别是指...",
        chunk_type="paragraph",
        section_title="贷后风险识别",
        section_path=["智能风控指南", "贷后管理"],
        page_start=12,
        page_end=12,
    )
    parsed = ParsedDocument(
        source=source,
        parser_name="swxy",
        parser_version="naive-v1",
        raw_chunks=[chunk],
    )

    assert parsed.raw_chunks[0].raw_content == "贷后风险识别是指..."


def test_raw_parsed_chunk_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError):
        RawParsedChunk(chunk_order=0, raw_content="x")

    with pytest.raises(ValidationError):
        RawParsedChunk(chunk_order=1, raw_content="")


def test_models_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        IngestionContext(
            kb_id="risk_domain_knowledge",
            doc_id="risk_guide",
            version_id="risk_guide_202607",
            job_id="job_1",
            file_path="/tmp/risk_guide.pdf",
            doc_name="risk_guide.pdf",
            source_type=SourceType.PDF,
            extra_field="boom",
        )
