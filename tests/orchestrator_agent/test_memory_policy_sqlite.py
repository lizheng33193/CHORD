from __future__ import annotations

import pytest

from app.services.orchestrator_agent.memory_policy import (
    build_memory_record,
    classify_user_memory_content,
)


@pytest.mark.timeout(2)
def test_policy_redacts_sensitive_fragment_but_keeps_useful_memory():
    decision = build_memory_record(
        content="用户偏好中文输出，token='abc123' 不应该明文保存",
        category="preference",
    )
    assert decision.accepted
    assert decision.record is not None
    assert "abc123" not in decision.record.content
    assert "<TOKEN>" in decision.record.content


@pytest.mark.timeout(2)
def test_policy_rejects_standalone_secret():
    decision = build_memory_record(
        content="password='super-secret'",
        category="reference",
    )
    assert decision.accepted is False
    assert decision.reason == "standalone_secret"


@pytest.mark.timeout(2)
def test_policy_rejects_low_value_or_bad_category():
    assert build_memory_record(content="ok", category="preference").accepted is False
    assert build_memory_record(content="useful content", category="unknown").accepted is False


@pytest.mark.timeout(2)
def test_policy_accepts_strict_whitelist_categories():
    assert build_memory_record(content="请记住：我偏好中文输出", category="preference").accepted
    assert build_memory_record(content="纠正：以后不要使用表情符号", category="feedback").accepted
    assert build_memory_record(content="项目事实：当前项目使用 SQLite 长期记忆", category="project").accepted
    assert build_memory_record(content="参考入口：https://example.com/spec.md", category="reference").accepted


@pytest.mark.timeout(2)
def test_policy_rejects_chat_noise_and_assistant_final():
    assert build_memory_record(content="你好", category="task").accepted is False
    assert build_memory_record(content="你是什么模型？", category="task").accepted is False
    decision = build_memory_record(
        content="您好！我是一个用于墨西哥/东南亚用户画像分析平台的编排代理。",
        category="insight",
        source="orchestrator_final",
    )
    assert decision.accepted is False
    assert decision.reason in {"low_value_chat", "category_whitelist"}


@pytest.mark.timeout(2)
def test_policy_applies_same_guards_to_memory_admin_source():
    accepted = build_memory_record(
        content="请记住：我偏好中文输出",
        category="preference",
        source="memory_admin",
    )
    assert accepted.accepted
    assert accepted.record is not None
    assert accepted.record.source == "memory_admin"

    assert build_memory_record(
        content="你好",
        category="preference",
        source="memory_admin",
    ).accepted is False
    assert build_memory_record(
        content="password='super-secret'",
        category="reference",
        source="memory_admin",
    ).accepted is False


@pytest.mark.timeout(2)
def test_policy_classifies_user_text_for_auto_write():
    assert classify_user_memory_content("请记住：我偏好中文输出") == ("preference", "请记住：我偏好中文输出")
    assert classify_user_memory_content("纠正：以后不要使用表情") == ("feedback", "纠正：以后不要使用表情")
    assert classify_user_memory_content("项目事实：当前默认国家是 mx") == ("project", "项目事实：当前默认国家是 mx")
    assert classify_user_memory_content("参考入口：https://example.com/spec.md") == ("reference", "参考入口：https://example.com/spec.md")
    assert classify_user_memory_content("请查询 UID 123 的用户画像") == ("task", "请查询 UID 123 的用户画像")
    assert classify_user_memory_content("你好，你是什么模型？") is None
