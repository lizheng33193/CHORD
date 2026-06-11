"""Phase 2 Task 2.5 — 4 级压缩 unit test (Plan 10 v3.2).

走真实 OrchestratorMessage + ToolCallRecord Pydantic 模型，不构造 dict。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.orchestrator_agent.memory_manager import (
    align_tool_pairs,
    compress_level_1,
    compress_level_2,
    compress_level_3,
)
from app.services.orchestrator_agent.schemas import (
    OrchestratorMessage,
    ToolCallRecord,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user(content: str) -> OrchestratorMessage:
    return OrchestratorMessage(role="user", content=content, timestamp=_now())


def _assistant(content: str) -> OrchestratorMessage:
    return OrchestratorMessage(role="assistant", content=content, timestamp=_now())


def _tool(content: str, tool_call_id: str) -> OrchestratorMessage:
    return OrchestratorMessage(
        role="tool",
        content=content,
        tool_call_id=tool_call_id,
        timestamp=_now(),
    )


def _record(
    tool_name: str,
    tool_call_id: str,
    input_: dict,
    output: dict | None = None,
) -> ToolCallRecord:
    return ToolCallRecord(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        input=input_,
        output=output,
        status="done" if output is not None else "running",
        started_at=_now(),
        finished_at=_now() if output is not None else None,
    )


def test_l1_truncates_old_tool_messages():
    msgs = [
        _user("q1"),
        _tool("x" * 500, "tc1"),
        _user("q2"),
        _tool("y" * 500, "tc2"),
        _user("q3"),
        _tool("z" * 500, "tc3"),
        _user("q4"),
        _user("q5"),
        _tool("w" * 500, "tc4"),
        _user("q6"),
        _assistant("final"),
    ]
    compress_level_1(msgs)
    assert "已裁剪" in msgs[1].content
    assert "已裁剪" in msgs[3].content
    assert msgs[-3].content == "w" * 500


def test_l2_dedupes_repeated_tool_calls_via_tool_call_records():
    same_input = {"country": "mx", "request": "查个人"}
    same_output = {"uids": [1, 2, 3]}
    records = [
        _record("query_data", "tc1", same_input, same_output),
        _record("query_data", "tc2", same_input, same_output),
        _record("query_data", "tc3", same_input, same_output),
    ]
    msgs = [
        _user("q"),
        _tool('{"uids": [1, 2, 3]}', "tc1"),
        _user("q"),
        _tool('{"uids": [1, 2, 3]}', "tc2"),
        _user("q"),
        _tool('{"uids": [1, 2, 3]}', "tc3"),
        _user("q4"),
        _user("q5"),
        _user("q6"),
        _user("q7"),
        _user("q8"),
    ]
    compress_level_2(msgs, records)
    deduped = [m for m in msgs if m.role == "tool" and "去重" in m.content]
    assert len(deduped) >= 1


def test_l2_skips_recent_tool_within_tail_protect():
    same_input = {"x": 1}
    same_output = {"y": 2}
    records = [
        _record("query_data", "tc_old", same_input, same_output),
        _record("query_data", "tc_new", same_input, same_output),
    ]
    msgs = [
        _user("q"),
        _tool("old", "tc_old"),
        _user("q1"),
        _user("q2"),
        _user("q3"),
        _user("q4"),
        _tool("new", "tc_new"),
    ]
    compress_level_2(msgs, records)
    new_msg = next(m for m in msgs if m.tool_call_id == "tc_new")
    assert new_msg.content == "new"


def test_align_tool_pairs_drops_orphan_leading_tool():
    msgs = [
        _tool("orphan", "tc_x"),
        _user("q"),
        _assistant("a"),
    ]
    cleaned = align_tool_pairs(msgs)
    assert cleaned[0].role == "user"
    assert len(cleaned) == 2


def test_l3_summarizes_middle_with_head_protect_1():
    captured: dict = {}

    def fake_summarize(dicts: list[dict]) -> str:
        captured["count"] = len(dicts)
        return "FAKE_SUMMARY"

    msgs = [
        _user("first user"),
        _tool("r1", "tc1"),
        _user("q1"),
        _tool("r2", "tc2"),
        _user("q2"),
        _user("q3"),
        _user("q4"),
        _user("q5"),
        _user("q6"),
        _user("q7"),
    ]
    out = compress_level_3(msgs, fake_summarize)
    assert out[0].content == "first user"
    assert any("FAKE_SUMMARY" in str(m.content) for m in out)
    assert out[-1].content == "q7"
    assert captured.get("count", 0) > 0
