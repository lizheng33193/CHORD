from __future__ import annotations

import pytest


def test_query_normalizer_trims_and_lowercases() -> None:
    from app.risk_knowledge.retrieval.query_normalizer import QueryNormalizer

    assert QueryNormalizer(max_query_chars=32).normalize("  Loan Risk  ") == "loan risk"


def test_query_normalizer_rejects_empty_query() -> None:
    from app.risk_knowledge.retrieval.errors import InvalidRetrievalQueryError
    from app.risk_knowledge.retrieval.query_normalizer import QueryNormalizer

    with pytest.raises(InvalidRetrievalQueryError):
        QueryNormalizer(max_query_chars=32).normalize("   ")


def test_query_normalizer_rejects_too_long_query() -> None:
    from app.risk_knowledge.retrieval.errors import InvalidRetrievalQueryError
    from app.risk_knowledge.retrieval.query_normalizer import QueryNormalizer

    with pytest.raises(InvalidRetrievalQueryError):
        QueryNormalizer(max_query_chars=4).normalize("12345")
