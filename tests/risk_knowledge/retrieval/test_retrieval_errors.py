from __future__ import annotations

import pytest


def test_retrieval_query_rejects_empty_query() -> None:
    from app.risk_knowledge.retrieval.schemas import RetrievalQuery

    with pytest.raises(Exception):
        RetrievalQuery(query="", kb_id="risk_domain_knowledge")
