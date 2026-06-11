"""Phase 1 Task 1.3 — tools/memory.py four-class 路径 + 后兼容 V1 minimal 单测。

monkeypatch 走 `tools.memory._project_root` helper（Errata E2）—
不能直接 monkeypatch settings.project_root（pydantic v2 @property non-declared field）。
"""

from __future__ import annotations

from app.services.orchestrator_agent.schemas import (
    MemoryReadInput,
    MemoryWriteInput,
)
from app.services.orchestrator_agent.tools.memory import (
    memory_read,
    memory_write,
    read_all_categories,
)


def test_legacy_flat_key_still_works():
    out = memory_write(
        MemoryWriteInput(
            key="legacy_key",
            value="参考入口：https://example.com/legacy_key.md",
        )
    )
    assert out.ok is True
    assert out.path.endswith("memory.sqlite3")
    read_out = memory_read(MemoryReadInput(key_pattern="legacy_key"))
    assert any(item["content"] == "参考入口：https://example.com/legacy_key.md" for item in read_out.items)


def test_four_class_write_creates_jsonl():
    out = memory_write(
        MemoryWriteInput(
            key="mx/sess_001/user/20260505T140000",
            value="用户偏好中文输出",
        )
    )
    assert out.ok is True
    assert out.path.endswith("memory.sqlite3")


def test_four_class_read_returns_items():
    memory_write(
        MemoryWriteInput(
            key="mx/sess_002/feedback/20260505T140100",
            value="纠正：以后请使用项目符号",
        )
    )
    out = memory_read(MemoryReadInput(key_pattern="mx/sess_002/feedback/anything"))
    assert len(out.items) == 1
    assert out.items[0]["content"] == "纠正：以后请使用项目符号"
    assert out.items[0]["category"] == "feedback"
    assert out.items[0]["source"] == "memory_tool"
    assert out.items[0]["metadata"]["legacy_key"] == "mx/sess_002/feedback/20260505T140100"


def test_read_all_categories_aggregates_4_classes():
    memory_write(MemoryWriteInput(key="mx/sA/user/01", value="用户偏好中文输出"))
    memory_write(MemoryWriteInput(key="mx/sA/feedback/01", value="纠正：以后不要使用表情"))
    memory_write(MemoryWriteInput(key="mx/sA/project/01", value="项目事实：当前项目使用 SQLite 记忆"))
    memory_write(MemoryWriteInput(key="mx/sA/reference/01", value="参考入口：https://example.com/reference.md"))
    items = read_all_categories("mx", "sA")
    contents = {it["content"] for it in items}
    assert contents == {
        "用户偏好中文输出",
        "纠正：以后不要使用表情",
        "项目事实：当前项目使用 SQLite 记忆",
        "参考入口：https://example.com/reference.md",
    }
    cats = {it["category"] for it in items}
    assert cats == {"preference", "feedback", "project", "reference"}


def test_country_isolation():
    memory_write(MemoryWriteInput(key="mx/shared/user/01", value="用户偏好墨西哥中文输出"))
    th_items = read_all_categories("th", "shared")
    assert th_items == []
    mx_items = read_all_categories("mx", "shared")
    assert any(it["content"] == "用户偏好墨西哥中文输出" for it in mx_items)


def test_session_isolation():
    memory_write(MemoryWriteInput(key="mx/sA/user/01", value="用户偏好 A session 中文输出"))
    memory_write(MemoryWriteInput(key="mx/sB/user/01", value="用户偏好 B session 中文输出"))
    a_items = read_all_categories("mx", "sA")
    b_items = read_all_categories("mx", "sB")
    a_contents = {it["content"] for it in a_items}
    b_contents = {it["content"] for it in b_items}
    assert "用户偏好 A session 中文输出" in a_contents
    assert "用户偏好 A session 中文输出" not in b_contents
    assert "用户偏好 B session 中文输出" in b_contents
    assert "用户偏好 B session 中文输出" not in a_contents


def test_multiple_writes_append_to_jsonl():
    memory_write(MemoryWriteInput(key="mx/sess_log/user/01", value="用户偏好第一条中文输出"))
    memory_write(MemoryWriteInput(key="mx/sess_log/feedback/02", value="纠正：第二条以后不要表情"))
    memory_write(MemoryWriteInput(key="mx/sess_log/project/03", value="项目事实：第三条已确认"))
    out = memory_read(MemoryReadInput(key_pattern="mx/sess_log/user/x"))
    contents = {it["content"] for it in out.items}
    assert contents == {"用户偏好第一条中文输出"}


def test_invalid_category_falls_back_to_legacy():
    out = memory_write(
        MemoryWriteInput(
            key="mx/sess_x/UNKNOWN/01",
            value="参考入口：https://example.com/fallback.md",
        )
    )
    assert out.ok is True
    assert out.path.endswith("memory.sqlite3")
