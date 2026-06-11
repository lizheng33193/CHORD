"""Phase 3 Task 3.2 — memory_flush 单测 (Plan 10 v3.2).

mock generate_structured 返 dict 包装；monkeypatch tools.memory._project_root
（autouse fixture 在 tests/orchestrator_agent/conftest.py 中已设置）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.orchestrator_agent.memory_flush import memory_flush
from app.services.orchestrator_agent.tools.memory import read_all_categories


@pytest.mark.timeout(2)
def test_flush_writes_extracted_facts():
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "user": ["用户偏好中文"],
            "feedback": ["不要使用表情"],
            "project": ["UID 123 已确认"],
            "reference": [],
        },
    }
    out = memory_flush(
        messages=[{"role": "user", "content": "我偏好中文，不要表情，UID 123"}],
        session_id="sess_flush",
        country="mx",
        client=mock_client,
    )
    assert out["status"] == "ok"
    assert out["written"]["user"] == 1
    assert out["written"]["feedback"] == 1
    assert out["written"]["project"] == 1
    assert out["written"]["reference"] == 0

    items = read_all_categories("mx", "sess_flush")
    contents = {it["content"] for it in items}
    assert "用户偏好中文" in contents
    assert "不要使用表情" in contents
    assert "UID 123 已确认" in contents


@pytest.mark.timeout(2)
def test_flush_model_unavailable_fallback_does_not_raise():
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = {
        "status": "model_unavailable",
        "structured_result": {
            "user": [],
            "feedback": [],
            "project": [],
            "reference": [],
        },
    }
    out = memory_flush(
        messages=[{"role": "user", "content": "anything"}],
        session_id="sess_unavailable",
        country="mx",
        client=mock_client,
    )
    assert out["status"] == "model_unavailable"
    assert out["written"] == {"user": 0, "feedback": 0, "project": 0, "reference": 0}
    items = read_all_categories("mx", "sess_unavailable")
    assert items == []
