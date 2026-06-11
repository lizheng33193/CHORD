"""Phase 5 Task 5.2 — 同 session 写后能读，跨 session 读不到 (Plan 10 v3.2 验收)。

依赖 tests/orchestrator_agent/conftest.py 的 autouse fixture 把 _project_root 指向 tmp_path。
"""

from __future__ import annotations

import pytest

from app.services.orchestrator_agent.context_fit import load_session_memories
from app.services.orchestrator_agent.schemas import MemoryWriteInput
from app.services.orchestrator_agent.tools.memory import memory_write


@pytest.mark.timeout(2)
def test_same_session_recall_isolated_per_session():
    write_out = memory_write(MemoryWriteInput(
        key="mx/sess_A/user/20260506T100000_0",
        value="用户偏好中文输出",
    ))
    assert write_out.ok

    same = load_session_memories(session_id="sess_A", country="mx")
    assert "用户偏好中文输出" in same
    assert "## 历史记忆" in same
    assert "### preference" in same

    other = load_session_memories(session_id="sess_B", country="mx")
    assert other == ""
