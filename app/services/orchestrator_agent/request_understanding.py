"""User-visible route summaries for orchestrator visible execution."""

from __future__ import annotations

from app.services.orchestrator_agent.schemas import KnownIntent, RequestUnderstanding


_ROUTE_LABELS: dict[KnownIntent, str] = {
    "answer_from_workspace": "已有画像追问",
    "profile_uid": "单 UID 画像分析",
    "profile_batch": "批量画像分析",
    "need_clarification": "需要补充条件",
    "clarify_data_request": "需要澄清数据任务类型",
    "create_data_agent_run": "创建 Data Agent SQL 审核任务",
    "query_data_then_profile": "先取数后画像",
    "run_trace": "轨迹分析",
    "general_chat": "通用 Agent 对话",
}

_ROUTE_REASONS: dict[KnownIntent, str] = {
    "answer_from_workspace": "当前问题聚焦于已有画像结果的解释、比较或改写，优先复用证据回答。",
    "profile_uid": "用户请求需要执行画像流程，并检查本地数据是否完整。",
    "profile_batch": "当前请求涉及多个 UID，需要批量检查数据并执行画像。",
    "need_clarification": "当前请求明显是 cohort 取数意图，但缺少国家或时间范围，需先补充条件。",
    "clarify_data_request": "当前请求涉及数据查询，但尚未明确是继续普通画像对话，还是创建需要人工审核的 SQL 任务。",
    "create_data_agent_run": "当前请求明确要求通过 Data Agent 创建 SQL 审核任务，需进入受控的 SQL HITL 桥接路径。",
    "query_data_then_profile": "当前请求需要先查询目标 UID，再决定是否补数并执行画像。",
    "run_trace": "用户显式请求轨迹/路径分析，优先进入 trace 链路。",
    "general_chat": "当前问题不匹配确定性画像、取数或轨迹路径，进入通用 Agent 模式。",
}


def build_request_understanding(
    *,
    prompt: str,
    intent: KnownIntent,
    uids: list[str],
    focus: list[str],
    trace_days: int = 7,
    missing_slots: list[str] | None = None,
    clarification_prompt: str | None = None,
    candidate_defaults: dict | None = None,
) -> RequestUnderstanding:
    normalized_focus = _normalize_focus(focus, prompt)
    return RequestUnderstanding(
        intent=intent,
        route_label=_ROUTE_LABELS[intent],
        rewritten_goal=_build_rewritten_goal(prompt, intent, uids, normalized_focus, trace_days),
        focus=normalized_focus,
        requires_tools=intent in {"profile_uid", "profile_batch", "query_data_then_profile", "run_trace", "create_data_agent_run"},
        route_reason=_ROUTE_REASONS[intent],
        answer_mode=_answer_mode_for(intent),
        missing_slots=list(missing_slots or []),
        clarification_prompt=clarification_prompt,
        candidate_defaults=dict(candidate_defaults or {}),
    )


def _normalize_focus(focus: list[str], prompt: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in focus:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    if ordered:
        return ordered
    compact = str(prompt or "").strip()
    if compact:
        return ["summary"]
    return []


def _answer_mode_for(intent: KnownIntent) -> str:
    if intent == "answer_from_workspace":
        return "workspace_evidence_answer"
    if intent == "general_chat":
        return "general_chat"
    return "tool_execution"


def _build_rewritten_goal(
    prompt: str,
    intent: KnownIntent,
    uids: list[str],
    focus: list[str],
    trace_days: int,
) -> str:
    if intent == "answer_from_workspace":
        if "why" in focus and "customer_script" in focus:
            return "基于当前已有画像结果，解释高流失风险并改写为客服话术"
        if "comparison" in focus:
            count = len(uids) if uids else "当前"
            return f"基于当前已有画像结果，比较 {count} 个用户的关键差异"
        if "why" in focus:
            return "基于当前已有画像结果，解释当前关键风险或结论"
        if "customer_script" in focus:
            return "基于当前已有画像结果，改写为可直接使用的客服话术"
        return "基于当前已有画像结果，总结当前用户画像"
    if intent == "profile_uid":
        uid = uids[0] if uids else "目标 UID"
        if "rerun" in focus:
            return f"重新执行 UID {uid} 的画像分析并输出最新结论"
        return f"执行 UID {uid} 的画像分析"
    if intent == "profile_batch":
        return f"执行 {len(uids)} 个 UID 的批量画像分析"
    if intent == "query_data_then_profile":
        return "先查询目标 UID，再补齐缺失数据并执行画像"
    if intent == "need_clarification":
        return "补充 cohort 查询所需条件后继续执行取数与画像"
    if intent == "clarify_data_request":
        return "先澄清是继续普通画像对话，还是创建 SQL 审核任务"
    if intent == "create_data_agent_run":
        return "创建一个需要人工审核的 Data Agent SQL 任务"
    if intent == "run_trace":
        uid = uids[0] if uids else "目标 UID"
        return f"执行 UID {uid} 最近 {trace_days} 天的行为轨迹分析"
    return "进入通用 Agent 模式回答当前问题"
