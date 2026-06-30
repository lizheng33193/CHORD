from __future__ import annotations

import os

import pytest


def require_real_embedding_provider_smoke() -> None:
    if os.getenv("CHORD_RUN_REAL_EMBEDDING_TESTS") != "1":
        pytest.skip("set CHORD_RUN_REAL_EMBEDDING_TESTS=1 to run real embedding smoke")
    if not os.getenv("DASHSCOPE_API_KEY"):
        pytest.skip("set DASHSCOPE_API_KEY to run DashScope embedding smoke")
    if os.getenv("RISK_KNOWLEDGE_EMBEDDING_PROVIDER") != "dashscope":
        pytest.skip("set RISK_KNOWLEDGE_EMBEDDING_PROVIDER=dashscope to run DashScope embedding smoke")
