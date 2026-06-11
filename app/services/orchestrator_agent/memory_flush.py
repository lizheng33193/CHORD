"""Memory Flush — extract key facts before compression (Plan 10 Phase 3).

走 ModelClient.generate_structured，路由 memory.summarizer。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.core.model_client import ModelClient
from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import (
    DEFAULT_PROJECT_ID,
    DEFAULT_USER_ID,
    SQLiteMemoryStore,
    memory_write_enabled,
)

from .summarizer import format_messages

logger = logging.getLogger(__name__)


FLUSH_PROMPT = """从以下对话中提取关键事实，分类输出 JSON：

## 对话
{messages}

## 输出严格 JSON
{{
  "user": ["用户偏好/身份相关，最多 5 条"],
  "feedback": ["用户对 Agent 的纠正/反馈，最多 5 条"],
  "project": ["项目进展/已做决策，最多 5 条"],
  "reference": ["外部资源链接/工具入口，最多 5 条"]
}}

要求：宁缺毋滥，只提取真正重要的；空类返回 []。
"""


_FLUSH_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user": {"type": "array", "items": {"type": "string"}},
        "feedback": {"type": "array", "items": {"type": "string"}},
        "project": {"type": "array", "items": {"type": "string"}},
        "reference": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["user", "feedback", "project", "reference"],
}


_FALLBACK_FLUSH: dict[str, Any] = {
    "user": [],
    "feedback": [],
    "project": [],
    "reference": [],
}


def memory_flush(
    messages: list,
    session_id: str,
    country: str = "mx",
    user_id: str | None = None,
    project_id: str | None = None,
    client: ModelClient | None = None,
    store: SQLiteMemoryStore | None = None,
) -> dict:
    client = client or ModelClient()
    msg_text = format_messages(messages)
    prompt = FLUSH_PROMPT.format(messages=msg_text)
    result = client.generate_structured(
        skill_name="memory_flush",
        prompt=prompt,
        fallback_result=_FALLBACK_FLUSH,
        response_schema=_FLUSH_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    status = result.get("status", "ok")
    extracted = result.get("structured_result", _FALLBACK_FLUSH)
    if not isinstance(extracted, dict):
        extracted = _FALLBACK_FLUSH

    written = {"user": 0, "feedback": 0, "project": 0, "reference": 0}
    if status == "ok" and memory_write_enabled():
        store = store or SQLiteMemoryStore()
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        for category in written:
            items = extracted.get(category, [])
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items):
                if not isinstance(item, str) or not item:
                    continue
                decision = build_memory_record(
                    content=item,
                    category=category,
                    user_id=user_id or DEFAULT_USER_ID,
                    project_id=project_id or DEFAULT_PROJECT_ID,
                    session_id=session_id,
                    country=country,
                    scope="user",
                    memory_type="semantic",
                    source="memory_flush",
                    metadata={"flush_id": f"{ts}_{idx}"},
                )
                if decision.redaction_hits > 0:
                    logger.warning(
                        "memory_flush 检出凭据并脱敏 session=%s category=%s hits=%d",
                        session_id,
                        category,
                        decision.redaction_hits,
                    )
                if decision.accepted and decision.record:
                    store.add(decision.record)
                    written[category] += 1

    return {"status": status, "written": written, "extracted": extracted}
