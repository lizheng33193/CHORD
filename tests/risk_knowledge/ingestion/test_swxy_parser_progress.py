from __future__ import annotations

from app.knowledge_base.schemas import SourceType
from app.risk_knowledge.ingestion.context import IngestionContext
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter


def test_swxy_parser_adapter_reports_pdf_progress_messages() -> None:
    events: list[tuple[float | None, str]] = []

    def _fake_chunker(*, filename, binary, from_page, to_page, callback):
        callback(0.1, "Start to parse.")
        callback(msg="OCR started")
        callback(0.63, "Layout analysis (2.31s)")
        callback(0.65, "Table analysis (0.52s)")
        callback(0.67, "Text merged (0.20s)")
        return [
            {
                "content_with_weight": "风险知识内容",
                "page_num_int": 12,
                "chunk_type": "paragraph",
            }
        ]

    adapter = SwxyParserAdapter(chunker=_fake_chunker)
    parsed = adapter.parse(
        IngestionContext(
            kb_id="risk_domain_knowledge",
            doc_id="risk_guide",
            version_id="risk_guide_v1",
            job_id="idxjob_1",
            file_path="/tmp/risk_guide.pdf",
            doc_name="risk_guide.pdf",
            source_type=SourceType.PDF,
        ),
        progress_callback=lambda progress, message: events.append((progress, message)),
    )

    assert parsed.raw_chunks[0].page_start == 12
    assert events == [
        (0.1, "Start to parse."),
        (None, "OCR started"),
        (0.63, "Layout analysis (2.31s)"),
        (0.65, "Table analysis (0.52s)"),
        (0.67, "Text merged (0.20s)"),
    ]
