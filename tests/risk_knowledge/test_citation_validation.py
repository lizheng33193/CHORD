from __future__ import annotations

from app.risk_knowledge.qa.citation_validation import CitationValidator
from app.risk_knowledge.service.schemas import EvidenceTraceItem, RenderedCitation


def test_citation_validator_blocks_missing_citation_ids() -> None:
    result = CitationValidator().validate(
        citations=[],
        evidence_trace=[],
        used_citation_ids=[],
    )

    assert result.passed is False
    assert any(item.code == "RISK_QA_CITATION_MISSING" for item in result.blockers)


def test_citation_validator_blocks_non_risk_source() -> None:
    result = CitationValidator().validate(
        citations=[
            RenderedCitation(
                citation_id="cite_1",
                label="[1] bad source",
                document_id="risk_doc",
                version_id="v1",
                chunk_id="chunk_1",
                evidence_id="ev_1",
            )
        ],
        evidence_trace=[
            EvidenceTraceItem(
                evidence_id="ev_1",
                source_type="data_knowledge",
                document_id="risk_doc",
                document_version="v1",
                chunk_id="chunk_1",
                evidence_text="bad source",
            )
        ],
        used_citation_ids=["cite_1"],
    )

    assert result.passed is False
    assert any(item.code == "RISK_QA_CITATION_INVALID_SOURCE" for item in result.blockers)
