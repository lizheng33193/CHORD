from __future__ import annotations

import pytest

from app.risk_knowledge.ingestion.errors import SwxyParserUnavailableError
from app.risk_knowledge.ingestion.swxy_parser_adapter import SwxyParserAdapter


def test_swxy_parser_adapter_imports() -> None:
    adapter = SwxyParserAdapter()
    assert isinstance(adapter, SwxyParserAdapter)


def test_swxy_default_chunker_loads_or_reports_missing_optional_dependency() -> None:
    adapter = SwxyParserAdapter()

    try:
        chunker = adapter._load_default_chunker()
    except SwxyParserUnavailableError as exc:
        assert "vendored SWXY chunker" in str(exc)
        assert "tika" in str(exc)
    else:
        assert callable(chunker)
