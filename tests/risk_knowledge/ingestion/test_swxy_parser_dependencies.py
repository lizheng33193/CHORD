from __future__ import annotations

from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter


def test_swxy_parser_adapter_imports() -> None:
    adapter = SwxyParserAdapter()
    assert isinstance(adapter, SwxyParserAdapter)


def test_swxy_default_chunker_loads() -> None:
    adapter = SwxyParserAdapter()

    chunker = adapter._load_default_chunker()

    assert callable(chunker)
