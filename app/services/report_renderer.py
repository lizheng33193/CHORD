"""Render markdown reports from structured results."""

from __future__ import annotations

from typing import Any


def render_agent_report(
    agent_title: str,
    uid: str,
    summary: str,
    structured_result: dict[str, Any],
) -> str:
    """Render a compact markdown report for one skill output."""
    status = structured_result.get("status", "ok")
    tags = structured_result.get("tags", [])
    tags_text = ", ".join(str(tag) for tag in tags) if tags else "-"
    model_trace = (
        structured_result.get("model_trace", {})
        if isinstance(structured_result.get("model_trace"), dict)
        else {}
    )
    llm_status = "LLM 推理完成" if model_trace.get("used_llm") else "规则降级结果"
    fallback_reason = str(model_trace.get("fallback_reason", "") or "")
    fallback_line = f"- Fallback Reason: `{fallback_reason}`\n" if fallback_reason else ""

    return (
        f"## {agent_title}\n\n"
        f"- UID: `{uid}`\n"
        f"- Status: `{status}`\n"
        f"- LLM Status: `{llm_status}`\n"
        f"- Summary: {summary}\n"
        f"- Tags: {tags_text}\n"
        f"{fallback_line}"
    )
