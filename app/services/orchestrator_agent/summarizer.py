"""LLM-based summarization for compression (Plan 10 Phase 2).

全走 ModelClient.generate_structured，路由 memory.summarizer。
"""
from __future__ import annotations

from typing import Any

from app.core.model_client import ModelClient


SUMMARY_TEMPLATE = """请对以下对话历史生成结构化摘要（输出 JSON，唯一字段 summary 为中文贯串文本）：

## 对话历史
{messages}

## 摘要模板（填入 summary 字段中）
### Goal（用户的原始目标）
### Decisions（已做的关键决策）
### Facts（确认的 UID / 订单号 / 关键数据）
### Pending（进行中或被阻塞的事项）
### Next（下一步计划）

要求：总长 2000-5000 tokens；不丢任何 UID/订单号/金额；保持原对话语种。

## 输出严格 JSON
{{"summary": "<在这里按上述模板贯串成 1 个连续的中文文本>"}}
"""

ITERATIVE_TEMPLATE = """以下是已有摘要：

{existing_summary}

以下是后续新对话：

{new_messages}

请在已有摘要基础上**修订**（不是重写），保留所有 Goal/UID/关键数据。
输出严格 JSON：
{{"summary": "<修订后的完整摘要贯串文本>"}}
"""

_SUMMARY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

_FALLBACK_SUMMARY = {"summary": "[摘要不可用：模型调用失败，原始消息保留使用]"}


def _extract_summary(generated: dict[str, Any]) -> str:
    payload = generated.get("structured_result", _FALLBACK_SUMMARY)
    if not isinstance(payload, dict):
        return _FALLBACK_SUMMARY["summary"]
    return str(payload.get("summary", _FALLBACK_SUMMARY["summary"]))


def format_messages(messages: list) -> str:
    out: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            m = m.model_dump()
        role = m.get("role", "?")
        content = str(m.get("content", ""))[:500]
        out.append(f"[{role}] {content}")
    return "\n".join(out)


def summarize_messages(
    messages: list,
    client: ModelClient | None = None,
) -> str:
    client = client or ModelClient()
    msg_text = format_messages(messages)
    prompt = SUMMARY_TEMPLATE.format(messages=msg_text)
    result = client.generate_structured(
        skill_name="memory_summarizer",
        prompt=prompt,
        fallback_result=_FALLBACK_SUMMARY,
        response_schema=_SUMMARY_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    return _extract_summary(result)


def iterative_summarize(
    existing: str,
    new_messages: list,
    client: ModelClient | None = None,
) -> str:
    client = client or ModelClient()
    msg_text = format_messages(new_messages)
    prompt = ITERATIVE_TEMPLATE.format(existing_summary=existing, new_messages=msg_text)
    result = client.generate_structured(
        skill_name="memory_summarizer",
        prompt=prompt,
        fallback_result={"summary": existing},
        response_schema=_SUMMARY_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    return _extract_summary(result)
