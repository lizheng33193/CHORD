from __future__ import annotations

import pytest

from app.knowledge_base.schemas import SourceType
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.errors import (
    EmptyParsedDocumentError,
    SwxyParserExecutionError,
    SwxyParserUnavailableError,
)
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter


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


def test_adapter_normalizes_swxy_dict_output() -> None:
    adapter = SwxyParserAdapter(
        chunker=lambda **_kwargs: [
            {
                "content_with_weight": "贷后风险识别是指...",
                "page_num_int": 12,
                "position_int": [1, 2, 3, 4],
                "top_int": 100,
                "title": "贷后风险识别",
                "docnm_kwd": "risk_guide.pdf",
            }
        ]
    )

    parsed = adapter.parse(_context())

    assert parsed.parser_name == "swxy"
    assert parsed.raw_chunks[0].raw_content == "贷后风险识别是指..."
    assert parsed.raw_chunks[0].page_start == 12
    assert parsed.raw_chunks[0].page_end == 12
    assert parsed.raw_chunks[0].position == {"position_int": [1, 2, 3, 4], "top_int": 100}
    assert parsed.raw_chunks[0].source_metadata["docnm_kwd"] == "risk_guide.pdf"


def test_adapter_uses_text_fallback_priority() -> None:
    adapter = SwxyParserAdapter(
        chunker=lambda **_kwargs: [
            {"content": "content fallback"},
            {"text": "text fallback"},
            {"page_content": "page content fallback"},
        ]
    )

    parsed = adapter.parse(_context())

    assert [chunk.raw_content for chunk in parsed.raw_chunks] == [
        "content fallback",
        "text fallback",
        "page content fallback",
    ]


def test_adapter_skips_empty_chunks_and_raises_when_nothing_remains() -> None:
    adapter = SwxyParserAdapter(chunker=lambda **_kwargs: [{"title": "empty"}, {"page_num_int": 3}])

    with pytest.raises(EmptyParsedDocumentError):
        adapter.parse(_context())


def test_adapter_raises_when_loader_unavailable() -> None:
    adapter = SwxyParserAdapter()

    def _broken_loader():
        raise SwxyParserUnavailableError("missing parser")

    adapter._load_default_chunker = _broken_loader  # type: ignore[method-assign]

    with pytest.raises(SwxyParserUnavailableError):
        adapter.parse(_context())


def test_adapter_wraps_parser_execution_errors() -> None:
    def _boom(**_kwargs):
        raise RuntimeError("parser exploded")

    adapter = SwxyParserAdapter(chunker=_boom)

    with pytest.raises(SwxyParserExecutionError):
        adapter.parse(_context())
