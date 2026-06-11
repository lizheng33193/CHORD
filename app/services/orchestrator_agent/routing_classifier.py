"""Lightweight LLM-assisted routing refinement for ambiguous NL requests."""

from __future__ import annotations

from typing import Any

from app.services.orchestrator_agent.request_understanding import build_request_understanding
from app.services.orchestrator_agent.schemas import KnownIntent, NormalizedRequest


_ROUTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "answer_from_workspace",
                "profile_uid",
                "profile_batch",
                "query_data_then_profile",
                "run_trace",
                "general_chat",
            ],
        },
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["intent", "confidence", "reason"],
}


def refine_normalized_request(
    client,
    *,
    prompt: str,
    session,
    normalized_request: NormalizedRequest,
) -> NormalizedRequest:
    if not _should_refine(prompt, session, normalized_request):
        return normalized_request

    fallback_result = {
        "intent": normalized_request.intent,
        "confidence": 0.0,
        "reason": "fallback_to_deterministic_router",
    }
    llm_prompt = (
        "你是用户画像聊天路由分类器。请只在以下 intent 中选择一个：\n"
        "- answer_from_workspace: 只读追问，复用当前已有画像结果回答\n"
        "- profile_uid: 分析单个 UID\n"
        "- profile_batch: 分析多个 UID\n"
        "- query_data_then_profile: 先取数筛 UID，再画像\n"
        "- run_trace: 明确轨迹分析\n"
        "- general_chat: 普通对话，不应触发画像/取数\n\n"
        "高风险规则：\n"
        "1. 没有 UID 且没有当前画像上下文时，不要把普通总结/讨论判成 answer_from_workspace。\n"
        "2. 只有在明确要筛选一批用户时，才能判成 query_data_then_profile。\n"
        "3. 有 UID 且明显要求分析用户时，优先 profile_uid/profile_batch。\n\n"
        f"当前 prompt: {prompt}\n"
        f"deterministic_intent: {normalized_request.intent}\n"
        f"uids: {normalized_request.uids}\n"
        f"focus: {(normalized_request.request_understanding.focus if normalized_request.request_understanding else [])}\n"
        f"has_workspace_context: {_has_workspace_context(session)}\n"
    )
    generated = client.generate_structured(
        skill_name="orchestrator_routing_classifier",
        prompt=llm_prompt,
        fallback_result=fallback_result,
        response_schema=_ROUTING_SCHEMA,
        route_key="orchestrator_agent.routing_classifier",
    )
    structured = generated.get("structured_result", fallback_result) or fallback_result
    intent = structured.get("intent", normalized_request.intent)
    confidence = float(structured.get("confidence", 0.0) or 0.0)
    if intent not in {
        "answer_from_workspace",
        "profile_uid",
        "profile_batch",
        "query_data_then_profile",
        "run_trace",
        "general_chat",
    }:
        return normalized_request
    if confidence < 0.7:
        return normalized_request
    if intent == "answer_from_workspace" and not (_has_workspace_context(session) or normalized_request.uids):
        return normalized_request.model_copy(update={
            "intent": "general_chat",
            "read_only": False,
            "request_understanding": build_request_understanding(
                prompt=prompt,
                intent="general_chat",
                uids=[],
                focus=list((normalized_request.request_understanding.focus if normalized_request.request_understanding else []) or []),
                trace_days=normalized_request.trace_days,
            ),
        })
    updated_intent: KnownIntent = intent
    return normalized_request.model_copy(update={
        "intent": updated_intent,
        "read_only": updated_intent == "answer_from_workspace",
        "request_understanding": build_request_understanding(
            prompt=prompt,
            intent=updated_intent,
            uids=list(normalized_request.uids),
            focus=list((normalized_request.request_understanding.focus if normalized_request.request_understanding else []) or []),
            trace_days=normalized_request.trace_days,
        ),
    })


def _should_refine(prompt: str, session, normalized_request: NormalizedRequest) -> bool:
    lowered = str(prompt or "").lower()
    focus = list((normalized_request.request_understanding.focus if normalized_request.request_understanding else []) or [])
    if normalized_request.intent == "query_data_then_profile" and normalized_request.query_request:
        return False
    if normalized_request.intent == "general_chat" and any(item in focus for item in ("summary", "why", "comparison", "customer_script")):
        return _has_workspace_context(session) or bool(normalized_request.uids)
    if normalized_request.intent == "query_data_then_profile" and not any(keyword in lowered for keyword in ("用户列表", "uid列表", "cohort", "批量", "流失用户")):
        return True
    return False


def _has_workspace_context(session) -> bool:
    snapshot = getattr(session, "active_entities", {}).get("workspace_snapshot") if session else None
    if isinstance(snapshot, dict) and snapshot.get("results"):
        return True
    tool_calls = getattr(session, "tool_calls", []) or []
    return any(
        getattr(record, "tool_name", None) in {"run_profile", "run_trace"}
        and getattr(record, "status", None) == "done"
        for record in tool_calls
    )
