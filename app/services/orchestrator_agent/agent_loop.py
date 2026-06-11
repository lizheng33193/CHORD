"""Agent Loop: drive LLM ↔ tools ↔ session for one user prompt.

Phase 3 Task 3.3 — 主循环（含工具 dispatch + budget + consecutive_failures），
**query_data 走普通工具路径**（无 ACK 时序）。

Phase 3 Task 3.4 在本文件追加 ACK 分支特殊处理，工具中 query_data 单独拆开。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from app.core.data_acquisition_capability import (
    data_acquisition_unavailable_message,
    get_data_acquisition_capability,
)
from app.core.model_client import ModelClient
from app.services.orchestrator_agent.data_availability import check_data_availability
from app.services.orchestrator_agent.execution.tool_runner import ToolRunSpec, ToolRunner
from app.services.orchestrator_agent.execution.profile_runner import (
    ProfileRunResult,
    ProfileRunner,
    ProfileRunSpec,
    call_tool_with_optional_progress as _call_tool_with_optional_progress_impl,
    log_run_profile_progress as _log_run_profile_progress_impl,
)
from app.services.orchestrator_agent.execution.repair_runner import (
    RepairPrepare,
    RepairRunResult,
    RepairRunner,
    RepairRunSpec,
)
from app.services.orchestrator_agent.finalization.final_answer_builder import (
    build_known_final_message as _build_known_final_message_impl,
    build_query_only_final_message as _build_query_only_final_message_impl,
)
from app.services.orchestrator_agent.finalization.message_persistence import (
    append_summary_line as _append_summary_line_impl,
    persist_final_message as _persist_final_message_impl,
)
from app.services.orchestrator_agent.flows.base import FlowControlSignal
from app.services.orchestrator_agent.flows.query_data_then_profile import QueryDataThenProfileFlow
from app.services.orchestrator_agent.flows.select_known_flow import select_known_flow
from app.services.orchestrator_agent.loop_context import (
    FlowContext,
    LoopDependencies,
    MemoryFacade,
)
from app.services.orchestrator_agent.planning.availability_summary import (
    availability_summary as _availability_summary_impl,
)
from app.services.orchestrator_agent.planning.plan_builder import (
    apply_clarification_answers as _apply_clarification_answers_impl,
    build_uid_module_plan as _build_uid_module_plan_impl,
    expand_requested_modules as _expand_requested_modules_impl,
    flatten_planned_modules as _flatten_planned_modules_impl,
    group_uid_module_plan as _group_uid_module_plan_impl,
    missing_bucket_counts as _missing_bucket_counts_impl,
    required_buckets_for_request as _required_buckets_for_request_impl,
)
from app.services.orchestrator_agent.repair_profile_data import (
    RepairProfileDataInput,
    execute_repair_query,
    prepare_repair_query,
    repair_profile_data,
)
from app.services.orchestrator_agent.request_understanding import build_request_understanding
from app.services.orchestrator_agent.request_router import normalize_request
from app.services.orchestrator_agent.routing_classifier import refine_normalized_request
from app.services.orchestrator_agent.review_rules import (
    append_data_acquisition_issue as append_data_acquisition_issue_rule,
    build_no_workspace_review,
    build_profile_review as build_profile_review_rule,
    review_step_summary as review_step_summary_rule,
)
from app.services.orchestrator_agent.runtime.cancellation import (
    cancel_requested as _cancel_requested_impl,
    maybe_cancel_run as _maybe_cancel_run_impl,
)
from app.services.orchestrator_agent.runtime.event_recorder import (
    EventRecorder,
    decorate_event as _decorate_event_impl,
    emit_run_status_event as _emit_run_status_event_impl,
    log_internal_run_event as _log_internal_run_event_impl,
    record_run_event as _record_run_event_impl,
)
from app.services.orchestrator_agent.schemas import (
    ConversationTurn,
    DataAvailability,
    ExecutionPlan,
    ExecutionTraceRecord,
    NormalizedRequest,
    OrchestratorMessage,
    OrchestratorSession,
    PendingAckState,
    PendingResolutionState,
    PlanStep,
    ReviewResult,
    TurnRunRecord,
    ToolCallRecord,
)
from app.services.orchestrator_agent.runtime.human_input import HumanInputController
from app.services.orchestrator_agent.runtime.llm_input import build_llm_input
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.session_lifecycle import (
    SessionLifecycle,
    clear_pending_ack as _clear_pending_ack_impl,
    clear_pending_resolution as _clear_pending_resolution_impl,
    create_tool_call_record as _create_tool_call_record_impl,
    create_turn as _create_turn_impl,
    create_turn_run as _create_turn_run_impl,
    find_run as _find_run_impl,
    find_turn as _find_turn_impl,
    find_turn_id_for_run as _find_turn_id_for_run_impl,
    next_event_seq as _next_event_seq_impl,
    open_ack_with_run as _open_ack_with_run_impl,
    open_resolution_with_run as _open_resolution_with_run_impl,
    set_pending_ack as _set_pending_ack_impl,
    set_pending_resolution as _set_pending_resolution_impl,
    set_run_status as _set_run_status_impl,
)
from app.services.orchestrator_agent.runtime.trace_store import (
    TraceStore,
    append_trace_steps as _append_trace_steps_impl,
    build_awaiting_resolution_event as _build_awaiting_resolution_event_impl,
    build_execution_plan_event as _build_execution_plan_event_impl,
    create_execution_trace as _create_execution_trace_impl,
    finalize_trace as _finalize_trace_impl,
    save_trace as _save_trace_impl,
    set_trace_availability as _set_trace_availability_impl,
    set_trace_review as _set_trace_review_impl,
    update_trace_step as _update_trace_step_impl,
)
from app.services.orchestrator_agent.session import (
    clear_run_cancel,
    is_run_cancel_requested,
    mark_run_cancelling,
    request_run_cancel,
)
from app.services.orchestrator_agent.session_store import save_session
from app.services.orchestrator_agent.system_prompt import assemble_system_prompt
from app.services.orchestrator_agent.visible_execution import (
    answer_from_workspace_with_evidence,
    build_workspace_evidence_bundle,
)
from app.services.orchestrator_agent.context_fit import (
    ensure_context_fits, load_session_memories,
    MODEL_MAX_TOKENS_PER_TURN,
)
from app.services.orchestrator_agent.memory_context import (
    apply_identity,
    append_rolling_summary,
    build_retrieved_memory_context,
    maybe_write_task_memory,
)
from app.services.orchestrator_agent.tools import get_tool_registry


LOGGER = logging.getLogger(__name__)
_ORIGINAL_REPAIR_PROFILE_DATA = repair_profile_data

# R7 P0-3 Knowledge 层注入：在首轮 LLM call 前用 keyword regex 从 prompt 中提取 country code，
# 传给 assemble_system_prompt(country) 动态拼接对应 docs/skills/orchestrator/{country}.md。
# V1 只走名字/短码粗粒度匹配，匹不到 → country=None → base prompt 不含国别规则段（LLM 需问用户）。
# R9 P0-1：使用中文字面量而非 unicode escape，避免 \u5893 (墓) 与 \u58a8 (墨) 视觉混淆造成的隐蔽 bug。
_COUNTRY_RE = re.compile(
    r"\b(th|mx|co|pe|cl|br)\b|墨西哥|泰国|哥伦比亚|秘鲁|智利|巴西|"
    r"thailand|mexico|colombia|peru|chile|brazil",
    re.IGNORECASE,
)
_NAME_TO_CODE = {
    "墨西哥": "mx", "mexico": "mx",
    "泰国": "th", "thailand": "th",
    "哥伦比亚": "co", "colombia": "co",
    "秘鲁": "pe", "peru": "pe",
    "智利": "cl", "chile": "cl",
    "巴西": "br", "brazil": "br",
}


def _detect_country(prompt: str) -> str | None:
    """V1 粗粒度提取：keyword + 2-位短码 regex。匹不到返回 None。"""
    m = _COUNTRY_RE.search(prompt)
    if not m:
        return None
    raw = m.group(0).lower()
    return raw if len(raw) == 2 else _NAME_TO_CODE.get(raw)


def _input_schema_for(tool_name: str):
    from app.services.orchestrator_agent import schemas as S
    return {
        "parse_uid_file": S.ParseUidFileInput,
        "run_profile": S.RunProfileInput,
        "run_trace": S.RunTraceInput,
        "query_data": S.QueryDataInput,
        "memory_write": S.MemoryWriteInput,
        "memory_read": S.MemoryReadInput,
    }[tool_name]

# Compatibility alias retained for tests and legacy monkeypatches.
# Real LLM input construction lives in runtime.llm_input.build_llm_input.
_build_llm_input = build_llm_input

# Local rule adapters kept in agent_loop to keep fallback / compatibility
# callsites concise. Primary review/finalization behavior lives in the
# migrated flows plus review/finalization modules.
def _review_step_summary(review: ReviewResult) -> str:
    return review_step_summary_rule(review)

def _build_profile_review(
    availability: DataAvailability,
    uid_modules_run: dict[str, list[str]],
    profile_output: dict[str, Any] | None = None,
    normalized_request: NormalizedRequest | None = None,
) -> ReviewResult:
    return build_profile_review_rule(availability, uid_modules_run, profile_output, normalized_request)


def _append_data_acquisition_issue(
    review: ReviewResult,
    *,
    missing_buckets: list[str],
    blocked: bool,
) -> ReviewResult:
    return append_data_acquisition_issue_rule(
        review,
        missing_buckets=missing_buckets,
        blocked=blocked,
    )


async def execute_query_data_cohort(session: OrchestratorSession, request_text: str, country: str) -> dict[str, Any]:
    """Query cohort UIDs through data_acquisition_agent with session-level cancel semantics."""
    # Compatibility / dependency-injection seam retained for LoopDependencies
    # and monkeypatch-based tests around query preview execution.
    if country != "mx":
        raise ValueError("query_data_then_profile only supports mx in v1")
    from app.services.orchestrator_agent.session import is_query_cancelled
    from app.services.orchestrator_agent.tools.query_data import _ChildAgent

    if is_query_cancelled(session.session_id):
        raise PermissionError("user cancelled in this session")

    child = _ChildAgent(country=country)
    qr = await asyncio.to_thread(child.run_query, request_text)
    return {
        "child": child,
        "sql_text": qr.sql_text,
        "rows_estimated": qr.rows_estimated,
    }


async def _complete_query_data_cohort(
    session: OrchestratorSession,
    child,
    sql_text: str,
) -> dict[str, Any]:
    # Compatibility / dependency-injection seam retained for LoopDependencies
    # and monkeypatch-based tests around query completion.
    execute_out = await asyncio.to_thread(child.execute, sql_text)
    return {
        "uids": list(execute_out.get("uids") or []),
        "rows_actual": int(execute_out.get("rows_actual") or 0),
        "sql_text": sql_text,
        "rows_estimated": int(execute_out.get("rows_estimated") or -1),
    }


def build_loop_dependencies() -> LoopDependencies:
    """Build dependency bag from the current module namespace for monkeypatch compatibility."""

    return LoopDependencies(
        model_client_factory=ModelClient,
        normalize_request=normalize_request,
        refine_normalized_request=refine_normalized_request,
        build_request_understanding=build_request_understanding,
        check_data_availability=check_data_availability,
        get_data_acquisition_capability=get_data_acquisition_capability,
        prepare_repair_query=prepare_repair_query,
        execute_repair_query=execute_repair_query,
        original_repair_profile_data=_ORIGINAL_REPAIR_PROFILE_DATA,
        repair_profile_data=repair_profile_data,
        execute_query_data_cohort=execute_query_data_cohort,
        complete_query_data_cohort=_complete_query_data_cohort,
    )


def _build_memory_facade(
    session: OrchestratorSession,
    detected_country: str | None,
) -> MemoryFacade:
    # Live shell helper: binds scoped memory helpers so migrated flows do not
    # need to know about session identity or default country rules.
    from app.services.orchestrator_agent.tools.memory import (
        memory_read_scoped,
        memory_write_scoped,
    )

    def _write(input_obj):
        return memory_write_scoped(
            input_obj,
            user_id=session.user_id,
            project_id=session.project_id,
            default_country=detected_country or session.country or "mx",
        )

    def _read(input_obj):
        return memory_read_scoped(
            input_obj,
            user_id=session.user_id,
            project_id=session.project_id,
            default_country=detected_country or session.country or "mx",
        )

    return MemoryFacade(
        read=_read,
        write=_write,
        build_context=build_retrieved_memory_context,
        fit_context=ensure_context_fits,
    )


def _promote_workspace_request_to_profile(
    prompt: str,
    normalized_request: NormalizedRequest,
) -> NormalizedRequest:
    promoted_intent = "profile_uid" if len(normalized_request.uids) == 1 else "profile_batch"
    focus = list((normalized_request.request_understanding.focus if normalized_request.request_understanding else []) or [])
    return normalized_request.model_copy(update={
        "intent": promoted_intent,
        "read_only": False,
        "request_understanding": build_request_understanding(
            prompt=prompt,
            intent=promoted_intent,
            uids=normalized_request.uids,
            focus=focus,
            trace_days=normalized_request.trace_days,
        ),
    })


def _clarified_request_from_answers(
    session: OrchestratorSession,
    *,
    prompt: str,
    answers: dict[str, Any],
    detected_country: str | None,
    client: ModelClient,
) -> tuple[str, NormalizedRequest, bool, str, str]:
    country_answer = str((answers or {}).get("country") or "").strip()
    time_window_answer = str((answers or {}).get("time_window") or "").strip()
    auto_profile = (answers or {}).get("auto_profile")
    enriched_prompt = _apply_clarification_answers(prompt, answers)
    clarified_request = normalize_request(enriched_prompt, session, country_answer or detected_country)
    clarified_request = refine_normalized_request(
        client,
        prompt=enriched_prompt,
        session=session,
        normalized_request=clarified_request,
    )
    if clarified_request.intent == "need_clarification":
        clarified_request = clarified_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": country_answer or clarified_request.country or detected_country,
            "query_request": enriched_prompt,
        })
        clarified_request.request_understanding = build_request_understanding(
            prompt=enriched_prompt,
            intent="query_data_then_profile",
            uids=list(clarified_request.uids),
            focus=list((clarified_request.request_understanding.focus if clarified_request.request_understanding else []) or ["cohort"]),
            trace_days=clarified_request.trace_days,
        )
    query_only_after_clarification = (
        clarified_request.intent == "query_data_then_profile"
        and auto_profile is False
    )
    return (
        enriched_prompt,
        clarified_request,
        query_only_after_clarification,
        country_answer,
        time_window_answer,
    )


# Phase 0/1/2 shim bindings: route real execution through extracted modules while
# preserving the historical agent_loop.* monkeypatch surface.
_find_turn = _find_turn_impl
_find_run = _find_run_impl
_find_turn_id_for_run = _find_turn_id_for_run_impl
_create_turn = _create_turn_impl
_create_turn_run = _create_turn_run_impl
_create_tool_call_record = _create_tool_call_record_impl
_set_run_status = _set_run_status_impl
_set_pending_ack = _set_pending_ack_impl
_clear_pending_ack = _clear_pending_ack_impl
_set_pending_resolution = _set_pending_resolution_impl
_clear_pending_resolution = _clear_pending_resolution_impl
_log_internal_run_event = _log_internal_run_event_impl
_open_ack_with_run = _open_ack_with_run_impl
_open_resolution_with_run = _open_resolution_with_run_impl
_next_event_seq = _next_event_seq_impl
_record_run_event = _record_run_event_impl
_decorate_event = _decorate_event_impl
_emit_run_status_event = _emit_run_status_event_impl
_maybe_cancel_run = _maybe_cancel_run_impl
_cancel_requested = _cancel_requested_impl
_create_execution_trace = _create_execution_trace_impl
_save_trace = _save_trace_impl
_set_trace_availability = _set_trace_availability_impl
_append_trace_steps = _append_trace_steps_impl
_update_trace_step = _update_trace_step_impl
_set_trace_review = _set_trace_review_impl
_finalize_trace = _finalize_trace_impl
_build_execution_plan_event = _build_execution_plan_event_impl
_build_awaiting_resolution_event = _build_awaiting_resolution_event_impl
_availability_summary = _availability_summary_impl
_apply_clarification_answers = _apply_clarification_answers_impl
_missing_bucket_counts = _missing_bucket_counts_impl
_expand_requested_modules = _expand_requested_modules_impl
_build_uid_module_plan = _build_uid_module_plan_impl
_group_uid_module_plan = _group_uid_module_plan_impl
_flatten_planned_modules = _flatten_planned_modules_impl
_required_buckets_for_request = _required_buckets_for_request_impl
_build_known_final_message = _build_known_final_message_impl
_build_query_only_final_message = _build_query_only_final_message_impl
_persist_final_message = _persist_final_message_impl
_append_summary_line = _append_summary_line_impl


async def _run_clarification_resume_legacy(
    session: OrchestratorSession,
    *,
    prompt: str,
    normalized_request: NormalizedRequest,
    answers: dict[str, Any],
    detected_country: str | None,
    client: ModelClient,
    ctx: FlowContext | None = None,
    turn_id: str | None = None,
    run_id: str | None = None,
    trace: ExecutionTraceRecord | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    # Temporary clarification fallback seam. QueryDataThenProfileFlow handles
    # the primary clarification resume paths; this remains only when
    # prepare/resume cannot safely continue inside the migrated flow.
    (
        enriched_prompt,
        clarified_request,
        query_only_after_clarification,
        country_answer,
        time_window_answer,
    ) = _clarified_request_from_answers(
        session,
        prompt=prompt,
        answers=answers,
        detected_country=detected_country,
        client=client,
    )
    if trace is not None:
        trace.intent = clarified_request.intent
        trace.request_summary = clarified_request.request_summary
        trace.request_understanding = clarified_request.request_understanding
        _save_trace(session, trace)
        yield _update_trace_step(
            session,
            trace,
            step_id="clarify_scope",
            status="done",
            result_summary=f"已补充国家={country_answer}，时间范围={time_window_answer}。",
        )
        yield _build_execution_plan_event(trace)
    async for evt in _run_known_request(
        session,
        prompt=enriched_prompt,
        normalized_request=clarified_request,
        detected_country=detected_country,
        client=client,
        ctx=ctx,
        turn_id=turn_id,
        run_id=run_id,
        workspace_evidence=None,
        query_only_after_clarification_override=query_only_after_clarification,
    ):
        yield evt


async def _run_known_request(
    session: OrchestratorSession,
    *,
    prompt: str,
    normalized_request: NormalizedRequest,
    detected_country: str | None,
    client: ModelClient,
    ctx: FlowContext | None = None,
    turn_id: str | None = None,
    run_id: str | None = None,
    workspace_evidence: dict[str, Any] | None = None,
    query_only_after_clarification_override: bool | None = None,
    precomputed_availability: DataAvailability | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    # Temporary compatibility / defensive seam for request shapes not accepted
    # by migrated flows. Migrated primary paths should only reach here through
    # explicit compat or fallback routing.
    import app.services.orchestrator_agent.tools as tools_mod

    lifecycle = ctx.lifecycle if ctx is not None else SessionLifecycle(session)
    events = ctx.events if ctx is not None else EventRecorder(session, turn_id=turn_id or "", run_id=run_id or "")
    human_input = ctx.human_input if ctx is not None else HumanInputController()
    tools = ctx.tools if ctx is not None else ToolRunner(session=session, lifecycle=lifecycle, events=events)
    profile_runner = ProfileRunner(
        session=session,
        lifecycle=lifecycle,
        events=events,
        progress_logger=_log_run_profile_progress_impl,
        profile_executor=lambda input_obj, progress_callback=None: _call_tool_with_optional_progress_impl(
            tools_mod.run_profile,
            input_obj,
            progress_callback,
        ),
    )
    repair_runner = RepairRunner(
        session=session,
        lifecycle=lifecycle,
        events=events,
        human_input=human_input,
    )

    execution_id = uuid.uuid4().hex
    query_only_after_clarification = bool(query_only_after_clarification_override)

    def _yield_cancelled_events(trace: ExecutionTraceRecord | None = None) -> list[dict[str, Any]]:
        return _cancel_requested(session, turn_id=turn_id, run_id=run_id, trace=trace) or []

    def _request_cancelled_events(trace: ExecutionTraceRecord | None = None) -> list[dict[str, Any]]:
        request_run_cancel(session.session_id, run_id)
        return _yield_cancelled_events(trace)

    if normalized_request.intent == "answer_from_workspace" and workspace_evidence:
        trace = _create_execution_trace(
            session,
            execution_id=execution_id,
            turn_id=turn_id,
            run_id=run_id,
            prompt=prompt,
            normalized_request=normalized_request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="reuse_workspace",
                    title="复用现有画像结果",
                    kind="answer_from_workspace",
                    user_visible_reason="当前问题是只读追问，优先复用已有画像结果。",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认已有结果足以回答当前问题。",
                ),
            ],
        )
        yield _build_execution_plan_event(trace)
        yield _update_trace_step(
            session, trace, step_id="reuse_workspace", status="done",
            result_summary="已复用 session/tool_calls/workspace snapshot 中的画像结果，并装载证据回答上下文。",
        )
        final_message, confidence = answer_from_workspace_with_evidence(
            client,
            prompt=prompt,
            normalized_request=normalized_request,
            evidence_bundle=workspace_evidence,
        )
        review = ReviewResult(status="pass", issues=[], can_answer=True, confidence_impact=None)
        yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
        yield _set_trace_review(session, trace, review)
        _finalize_trace(session, trace, final_status="completed", final_message=final_message)
        yield _persist_final_message(
            session,
            prompt=prompt,
            final_message=final_message,
            confidence=confidence,
            detected_country=detected_country,
        )
        return

    if normalized_request.intent == "answer_from_workspace":
        trace = _create_execution_trace(
            session,
            execution_id=execution_id,
            turn_id=turn_id,
            run_id=run_id,
            prompt=prompt,
            normalized_request=normalized_request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="reuse_workspace",
                    title="复用现有画像结果",
                    kind="answer_from_workspace",
                    user_visible_reason="当前问题是只读追问，优先复用已有画像结果。",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认当前会话是否已有足够的画像上下文。",
                ),
            ],
        )
        yield _build_execution_plan_event(trace)
        yield _update_trace_step(
            session,
            trace,
            step_id="reuse_workspace",
            status="blocked",
            result_summary="当前会话没有可复用的画像结果。",
        )
        review = build_no_workspace_review()
        yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
        yield _set_trace_review(session, trace, review)
        final_message = _build_known_final_message(
            normalized_request,
            review=review,
            extra_note="请先分析 UID 或恢复历史 workspace 后再继续追问。",
        )
        _finalize_trace(session, trace, final_status="blocked", final_message=final_message)
        yield _persist_final_message(
            session,
            prompt=prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=detected_country,
        )
        return

    if normalized_request.intent == "need_clarification":
        trace = _create_execution_trace(
            session,
            execution_id=execution_id,
            turn_id=turn_id,
            run_id=run_id,
            prompt=prompt,
            normalized_request=normalized_request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="clarify_scope",
                    title="补充 cohort 查询条件",
                    kind="clarification",
                    user_visible_reason="当前请求明显是在筛选一批用户，但还缺少国家或时间范围。",
                    resolution_type="clarification",
                    resolution_prompt=(normalized_request.request_understanding.clarification_prompt if normalized_request.request_understanding else None),
                    resolution_required_slots=list((normalized_request.request_understanding.missing_slots if normalized_request.request_understanding else []) or []),
                    resolution_candidate_defaults=dict((normalized_request.request_understanding.candidate_defaults if normalized_request.request_understanding else {}) or {}),
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="等待补充关键条件后再继续执行。",
                ),
            ],
        )
        yield _build_execution_plan_event(trace)
        yield _update_trace_step(
            session,
            trace,
            step_id="clarify_scope",
            status="awaiting_resolution",
            result_summary="等待用户补充国家和时间范围。",
        )
        from app.services.orchestrator_agent.resolve_bus import open_resolution, wait_resolution

        _open_resolution_with_run(
            open_resolution,
            session.session_id,
            resolution_id=f"{execution_id}:clarify_scope",
            run_id=run_id,
        )
        _set_pending_resolution(
            session,
            run_id=run_id,
            resolution_id=f"{execution_id}:clarify_scope",
            step_id="clarify_scope",
            resolution_type="clarification",
            message=(normalized_request.request_understanding.clarification_prompt if normalized_request.request_understanding else "请补充国家和时间范围。"),
            options=[],
            title="请先补充执行条件",
        )
        _set_run_status(session, run_id=run_id, status="awaiting_resolution")
        _log_internal_run_event(
            session,
            run_id=run_id,
            event_type="awaiting_resolution",
            payload={
                "resolution_id": f"{execution_id}:clarify_scope",
                "step_id": "clarify_scope",
                "resolution_type": "clarification",
                "prompt": (normalized_request.request_understanding.clarification_prompt if normalized_request.request_understanding else "请补充国家和时间范围。"),
                "required_slots": list((normalized_request.request_understanding.missing_slots if normalized_request.request_understanding else []) or []),
                "candidate_defaults": dict((normalized_request.request_understanding.candidate_defaults if normalized_request.request_understanding else {}) or {}),
            },
        )
        yield _build_awaiting_resolution_event(
            trace,
            step_id="clarify_scope",
            resolution_id=f"{execution_id}:clarify_scope",
            resolution_type="clarification",
            prompt=(normalized_request.request_understanding.clarification_prompt if normalized_request.request_understanding else "请补充国家和时间范围。"),
            required_slots=list((normalized_request.request_understanding.missing_slots if normalized_request.request_understanding else []) or []),
            candidate_defaults=dict((normalized_request.request_understanding.candidate_defaults if normalized_request.request_understanding else {}) or {}),
        )
        resolution = await asyncio.to_thread(wait_resolution, session.session_id, 600.0)
        cancel_events = _yield_cancelled_events(trace)
        if cancel_events:
            for cancelled_evt in cancel_events:
                yield cancelled_evt
            return
        _log_internal_run_event(
            session,
            run_id=run_id,
            event_type="resolution_received" if resolution else "resolution_expired",
            payload={"resolution_id": f"{execution_id}:clarify_scope", "step_id": "clarify_scope"},
        )
        _clear_pending_resolution(session, run_id=run_id)
        _set_run_status(session, run_id=run_id, status="running")
        answers = dict((resolution or {}).get("answers") or {})
        country_answer = str(answers.get("country") or "").strip()
        time_window_answer = str(answers.get("time_window") or "").strip()
        auto_profile = (answers or {}).get("auto_profile")
        if not country_answer or not time_window_answer:
            review = ReviewResult(
                status="fail",
                issues=[{"type": "clarification_required", "message": "缺少国家或时间范围，无法继续 cohort 执行。"}],
                can_answer=False,
                confidence_impact="缺少 cohort 关键条件，已阻断执行",
            )
            yield _update_trace_step(session, trace, step_id="clarify_scope", status="blocked", result_summary="未补充完整的国家和时间范围。")
            yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
            yield _set_trace_review(session, trace, review)
            final_message = _build_known_final_message(
                normalized_request,
                review=review,
                extra_note="请补充国家和时间范围后重试，例如：墨西哥、最近 7 天。",
            )
            _finalize_trace(session, trace, final_status="blocked", final_message=final_message)
            yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
            return

        enriched_prompt = _apply_clarification_answers(prompt, answers)
        clarified_request = normalize_request(enriched_prompt, session, country_answer or detected_country)
        clarified_request = refine_normalized_request(
            client,
            prompt=enriched_prompt,
            session=session,
            normalized_request=clarified_request,
        )
        if clarified_request.intent == "need_clarification":
            clarified_request = clarified_request.model_copy(update={
                "intent": "query_data_then_profile",
                "country": country_answer or clarified_request.country or detected_country,
                "query_request": enriched_prompt,
            })
            clarified_request.request_understanding = build_request_understanding(
                prompt=enriched_prompt,
                intent="query_data_then_profile",
                uids=list(clarified_request.uids),
                focus=list((clarified_request.request_understanding.focus if clarified_request.request_understanding else []) or ["cohort"]),
                trace_days=clarified_request.trace_days,
            )
        query_only_after_clarification = (
            clarified_request.intent == "query_data_then_profile"
            and auto_profile is False
        )

        trace.intent = clarified_request.intent
        trace.request_summary = clarified_request.request_summary
        trace.request_understanding = clarified_request.request_understanding
        _save_trace(session, trace)
        yield _update_trace_step(
            session,
            trace,
            step_id="clarify_scope",
            status="done",
            result_summary=f"已补充国家={country_answer}，时间范围={time_window_answer}。",
        )
        yield _build_execution_plan_event(trace)
        normalized_request = clarified_request

    if normalized_request.intent == "run_trace" and normalized_request.uids:
        trace = _create_execution_trace(
            session,
            execution_id=execution_id,
            turn_id=turn_id,
            run_id=run_id,
            prompt=prompt,
            normalized_request=normalized_request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="run_trace",
                    title="执行轨迹分析",
                    kind="run_trace",
                    user_visible_reason="用户显式请求深度行为轨迹分析。",
                    tool_name="run_trace",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认轨迹分析结果可回答当前问题。",
                ),
            ],
        )
        yield _build_execution_plan_event(trace)
        yield _update_trace_step(session, trace, step_id="run_trace", status="running")
        handle = await tools.start(
            ToolRunSpec(
                name="run_trace",
                func=tools_mod.run_trace,
                input_payload={"uid": normalized_request.uids[0], "days": normalized_request.trace_days},
                call_args=(
                    _input_schema_for("run_trace")(
                        uid=normalized_request.uids[0],
                        days=normalized_request.trace_days,
                    ),
                ),
                trace_id=trace.trace_id or trace.execution_id,
            )
        )
        tool_call_id = handle.record.tool_call_id
        if handle.started_event is not None:
            yield handle.started_event
        result = await handle.execute()
        if result.completed_event is not None:
            yield result.completed_event
        if result.status == "completed":
            output = result.output
            cancel_events = _yield_cancelled_events(trace)
            if cancel_events:
                for cancelled_evt in cancel_events:
                    yield cancelled_evt
                return
            yield _update_trace_step(session, trace, step_id="run_trace", status="done", result_summary="已完成轨迹分析。", tool_call_id=tool_call_id)
            review = ReviewResult(status="pass", issues=[], can_answer=True, confidence_impact=None)
            yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
            yield _set_trace_review(session, trace, review)
            final_message = _build_known_final_message(
                normalized_request,
                trace_output=output,
                review=review,
                extra_note="可继续结合左侧画像模块核对关键风险信号。",
            )
            _finalize_trace(session, trace, final_status="completed", final_message=final_message)
            yield _persist_final_message(
                session,
                prompt=prompt,
                final_message=final_message,
                confidence=0.88,
                detected_country=detected_country,
            )
            return
        error_message = result.error or "run_trace failed"
        yield _update_trace_step(session, trace, step_id="run_trace", status="failed", result_summary=error_message, tool_call_id=tool_call_id)
        review = ReviewResult(status="fail", issues=[{"type": "tool_error", "message": error_message}], can_answer=False, confidence_impact="轨迹分析执行失败")
        yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
        yield _set_trace_review(session, trace, review)
        final_message = _build_known_final_message(normalized_request, review=review, extra_note="请稍后重试或改为查看已有画像模块。")
        _finalize_trace(session, trace, final_status="error", final_message=final_message)
        yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
        return

    if normalized_request.intent not in {"profile_uid", "profile_batch", "query_data_then_profile"}:
        return

    country_for_execution = normalized_request.country or detected_country or session.country or "mx"
    if normalized_request.intent == "query_data_then_profile":
        trace = _create_execution_trace(
            session,
            execution_id=execution_id,
            turn_id=turn_id,
            run_id=run_id,
            prompt=prompt,
            normalized_request=normalized_request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="query_data",
                    title="查询 cohort UID",
                    kind="query_data",
                    user_visible_reason="先通过 Data Agent 找到符合条件的 UID 集合。",
                    tool_name="query_data",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="确认 cohort 范围和后续画像条件。",
                ),
            ],
        )
        yield _build_execution_plan_event(trace)
        reason_message = (
            "query_data_then_profile 已迁入 QueryDataThenProfileFlow；"
            "当前请求未满足 flow 接管条件，已阻断旧主链执行。"
        )
        yield _update_trace_step(
            session,
            trace,
            step_id="query_data",
            status="blocked",
            result_summary=reason_message,
        )
        review = ReviewResult(
            status="fail",
            issues=[{"type": "query_data_then_profile_flow_unavailable", "message": reason_message}],
            can_answer=False,
            confidence_impact="query_data_then_profile legacy 主链已关闭",
        )
        yield _update_trace_step(
            session,
            trace,
            step_id="review_final",
            status="done",
            result_summary=_review_step_summary(review),
        )
        yield _set_trace_review(session, trace, review)
        final_message = _build_known_final_message(
            normalized_request,
            review=review,
            extra_note="请补充国家/时间范围后重试，或重新发起明确的 mx cohort 画像请求。",
        )
        _finalize_trace(session, trace, final_status="blocked", final_message=final_message)
        yield _persist_final_message(
            session,
            prompt=prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=detected_country,
        )
        return
    trace = None

    profile_steps: list[PlanStep] = []
    if normalized_request.uid_file_path:
        profile_steps.append(
            PlanStep(
                step_id="parse_uid_file",
                title="解析 UID 文件",
                kind="parse_uid_file",
                user_visible_reason="先从本地 UID 文件中提取待分析的用户列表。",
                tool_name="parse_uid_file",
            )
        )
    if trace is None and profile_steps:
        trace = _create_execution_trace(
            session,
            execution_id=execution_id,
            turn_id=turn_id,
            run_id=run_id,
            prompt=prompt,
            normalized_request=normalized_request,
            availability=None,
            steps=profile_steps,
        )
        yield _build_execution_plan_event(trace)

    if normalized_request.uid_file_path:
        handle = await tools.start(
            ToolRunSpec(
                name="parse_uid_file",
                func=tools_mod.parse_uid_file,
                input_payload={"file_path": normalized_request.uid_file_path},
                call_args=(
                    _input_schema_for("parse_uid_file")(file_path=normalized_request.uid_file_path),
                ),
                trace_id=(trace.trace_id or trace.execution_id) if trace is not None else None,
            )
        )
        tool_call_id = handle.record.tool_call_id
        if trace is not None:
            yield _update_trace_step(session, trace, step_id="parse_uid_file", status="running", tool_call_id=tool_call_id)
        if handle.started_event is not None:
            yield handle.started_event
        result = await handle.execute()
        if result.completed_event is not None:
            yield result.completed_event
        if result.status == "completed":
            output = result.output
            parsed_uids = list(output.get("uids") or [])
            normalized_request = normalized_request.model_copy(update={"uids": parsed_uids})
            if trace is not None:
                yield _update_trace_step(
                    session,
                    trace,
                    step_id="parse_uid_file",
                    status="done",
                    result_summary=f"已从文件中解析出 {len(parsed_uids)} 个 UID。",
                    tool_call_id=tool_call_id,
                )
            if not parsed_uids:
                review = ReviewResult(
                    status="fail",
                    issues=[{"type": "empty_uid_file", "message": "UID 文件中没有可用 UID"}],
                    can_answer=False,
                    confidence_impact="没有可执行的 UID，已阻断画像",
                )
                if trace is not None:
                    _append_trace_steps(
                        session,
                        trace,
                        [
                            PlanStep(
                                step_id="review_final",
                                title="规则审核",
                                kind="review",
                                user_visible_reason="确认文件中是否存在可执行 UID。",
                            )
                        ],
                    )
                    yield _build_execution_plan_event(trace)
                    yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
                    yield _set_trace_review(session, trace, review)
                    final_message = _build_known_final_message(
                        normalized_request,
                        review=review,
                        extra_note="请检查 UID 文件内容是否有效，或改为直接输入 UID。",
                    )
                    _finalize_trace(session, trace, final_status="blocked", final_message=final_message)
                    yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
                return
        elif trace is not None:
            error_message = result.error or "UID 文件解析失败"
            yield _update_trace_step(session, trace, step_id="parse_uid_file", status="failed", result_summary=error_message, tool_call_id=tool_call_id)
            review = ReviewResult(status="fail", issues=[{"type": "tool_error", "message": error_message}], can_answer=False, confidence_impact="UID 文件解析失败")
            _append_trace_steps(
                session,
                trace,
                [
                    PlanStep(
                        step_id="review_final",
                        title="规则审核",
                        kind="review",
                        user_visible_reason="确认 UID 文件是否可用于继续执行。",
                    )
                ],
            )
            yield _build_execution_plan_event(trace)
            yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
            yield _set_trace_review(session, trace, review)
            final_message = _build_known_final_message(
                normalized_request,
                review=review,
                extra_note="请检查文件路径是否正确，且文件位于 data/id_files/ 下。",
            )
            _finalize_trace(session, trace, final_status="error", final_message=final_message)
            yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
            return

    availability = precomputed_availability or check_data_availability(
        normalized_request.uids,
        country=country_for_execution,
    )
    repair_steps: list[PlanStep] = []
    missing_uids_by_bucket: dict[str, list[str]] = {}
    required_buckets = _required_buckets_for_request(normalized_request.modules)
    for row in availability.per_uid:
        for bucket in row.missing_buckets:
            if bucket in required_buckets:
                missing_uids_by_bucket.setdefault(bucket, []).append(row.uid)
    requested_missing = sorted(missing_uids_by_bucket.keys())
    capability = get_data_acquisition_capability() if requested_missing else None
    repair_available = bool(capability and capability.enabled)
    unavailable_missing_buckets = requested_missing if requested_missing and not repair_available else []
    initial_uid_modules_plan = _build_uid_module_plan(availability, normalized_request)
    has_runnable_modules = any(initial_uid_modules_plan.values())
    estimated_repair_sql_count = len(requested_missing)
    strategy_required = (
        normalized_request.intent == "query_data_then_profile"
        and repair_available
        and bool(requested_missing)
        and (
            len(normalized_request.uids) >= 10
            or len(requested_missing) >= 2
            or estimated_repair_sql_count >= 2
        )
    )
    profile_steps.extend([
        PlanStep(
            step_id="check_data",
            title="检查数据完整性",
            kind="check_data",
            user_visible_reason="直接检查本地 by_uid bucket，不使用 sample fallback。",
        ),
    ])
    if unavailable_missing_buckets:
        profile_steps.append(PlanStep(
            step_id="data_acquisition_unavailable",
            title="无法自动补数",
            kind="data_acquisition_unavailable",
            user_visible_reason="当前环境未启用或缺少 Data Agent 依赖，无法补齐本次请求真正缺失的 bucket。",
        ))
        if has_runnable_modules:
            profile_steps.extend([
                PlanStep(
                    step_id="run_profile",
                    title="执行画像分析",
                    kind="run_profile",
                    user_visible_reason="对有真实数据支撑的模块执行画像。",
                    tool_name="run_profile",
                ),
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="核对缺失数据、执行结果和置信度影响。",
                ),
            ])
        else:
            profile_steps.append(PlanStep(
                step_id="review_final",
                title="规则审核",
                kind="review",
                user_visible_reason="确认当前请求是否还有可运行的画像模块。",
            ))
    elif strategy_required:
        profile_steps.append(PlanStep(
            step_id="repair_strategy",
            title="选择补数策略",
            kind="repair_strategy",
            user_visible_reason="cohort 较大且缺失 bucket 较多，先确认补数策略再继续执行。",
            resolution_type="repair_strategy",
            resolution_prompt="本次 cohort 用户较多，且缺多个 bucket。请选择只分析已有数据、只补 behavior、补齐全部，或先缩小范围。",
            resolution_options=[
                "analyze_existing_only",
                "repair_behavior_only",
                "repair_all_missing",
                "refine_scope",
            ],
        ))
    else:
        for bucket in requested_missing:
            repair_steps.append(PlanStep(
                step_id=f"repair_{bucket}",
                title=f"补齐 {bucket} 数据",
                kind="repair_profile_data",
                user_visible_reason=f"本地缺少 {bucket} bucket，尝试通过 Data Agent 补数。",
                tool_name="repair_profile_data",
            ))
        profile_steps.extend([
            *repair_steps,
            PlanStep(
                step_id="run_profile",
                title="执行画像分析",
                kind="run_profile",
                user_visible_reason="对有真实数据支撑的模块执行画像。",
                tool_name="run_profile",
            ),
            PlanStep(
                step_id="review_final",
                title="规则审核",
                kind="review",
                user_visible_reason="核对缺失数据、执行结果和置信度影响。",
            ),
        ])
    if trace is None:
        trace = _create_execution_trace(
            session,
            execution_id=execution_id,
            turn_id=turn_id,
            run_id=run_id,
            prompt=prompt,
            normalized_request=normalized_request,
            availability=availability,
            steps=profile_steps,
        )
        yield _build_execution_plan_event(trace)
    else:
        _set_trace_availability(session, trace, availability)
        _append_trace_steps(session, trace, profile_steps)
        yield _build_execution_plan_event(trace)

    yield _update_trace_step(session, trace, step_id="check_data", status="done", result_summary=_availability_summary(availability))

    if unavailable_missing_buckets:
        reason_message = data_acquisition_unavailable_message(capability)
        step_status = "skipped" if has_runnable_modules else "blocked"
        yield _update_trace_step(
            session,
            trace,
            step_id="data_acquisition_unavailable",
            status=step_status,
            result_summary=f"缺失 {', '.join(unavailable_missing_buckets)} 数据，{reason_message}",
        )
        if not has_runnable_modules:
            review = _append_data_acquisition_issue(
                _build_profile_review(availability, initial_uid_modules_plan, None, normalized_request),
                missing_buckets=unavailable_missing_buckets,
                blocked=True,
            )
            yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
            yield _set_trace_review(session, trace, review)
            final_message = _build_known_final_message(
                normalized_request,
                availability=availability,
                review=review,
                extra_note=f"{reason_message} 请直接提供 UID/UID 文件，或补齐本地 bucket 后重试。",
            )
            _finalize_trace(session, trace, final_status="blocked", final_message=final_message)
            yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
            return
        requested_missing = []

    if strategy_required:
        from app.services.orchestrator_agent.resolve_bus import open_resolution, wait_resolution

        missing_counts = _missing_bucket_counts(availability, requested_missing)
        yield _update_trace_step(
            session,
            trace,
            step_id="repair_strategy",
            status="awaiting_resolution",
            result_summary=f"cohort 共 {len(normalized_request.uids)} 个 UID，缺失 bucket 包括 {', '.join(requested_missing)}。",
        )
        _open_resolution_with_run(
            open_resolution,
            session.session_id,
            resolution_id=f"{execution_id}:repair_strategy",
            run_id=run_id,
        )
        _set_pending_resolution(
            session,
            run_id=run_id,
            resolution_id=f"{execution_id}:repair_strategy",
            step_id="repair_strategy",
            resolution_type="repair_strategy",
            message="本次 cohort 用户较多，且缺多个 bucket。请选择补数策略。",
            options=["analyze_existing_only", "repair_behavior_only", "repair_all_missing", "refine_scope"],
            title="请选择本次 cohort 的补数策略",
        )
        _set_run_status(session, run_id=run_id, status="awaiting_resolution")
        _log_internal_run_event(
            session,
            run_id=run_id,
            event_type="awaiting_resolution",
            payload={
                "resolution_id": f"{execution_id}:repair_strategy",
                "step_id": "repair_strategy",
                "resolution_type": "repair_strategy",
                "prompt": "本次 cohort 返回的 UID 较多且缺多个 bucket，请先选择执行策略。",
                "options": ["analyze_existing_only", "repair_behavior_only", "repair_all_missing", "refine_scope"],
                "missing_bucket_counts": missing_counts,
                "cohort_size": len(normalized_request.uids),
            },
        )
        yield _build_awaiting_resolution_event(
            trace,
            step_id="repair_strategy",
            resolution_id=f"{execution_id}:repair_strategy",
            resolution_type="repair_strategy",
            prompt="本次 cohort 返回的 UID 较多且缺多个 bucket，请先选择执行策略。",
            options=["analyze_existing_only", "repair_behavior_only", "repair_all_missing", "refine_scope"],
            missing_bucket_counts=missing_counts,
            cohort_size=len(normalized_request.uids),
        )
        resolution = await asyncio.to_thread(wait_resolution, session.session_id, 600.0)
        cancel_events = _yield_cancelled_events(trace)
        if cancel_events:
            for cancelled_evt in cancel_events:
                yield cancelled_evt
            return
        _log_internal_run_event(
            session,
            run_id=run_id,
            event_type="resolution_received" if resolution else "resolution_expired",
            payload={"resolution_id": f"{execution_id}:repair_strategy", "step_id": "repair_strategy"},
        )
        _clear_pending_resolution(session, run_id=run_id)
        _set_run_status(session, run_id=run_id, status="running")
        selected_option = str((resolution or {}).get("selected_option") or "").strip() or "refine_scope"
        if selected_option == "refine_scope":
            review = ReviewResult(
                status="fail",
                issues=[{"type": "scope_refinement_requested", "message": "用户选择先缩小 cohort 范围后再执行。"}],
                can_answer=False,
                confidence_impact="当前 cohort 范围过大，已等待进一步缩小条件",
            )
            _append_trace_steps(session, trace, [
                PlanStep(
                    step_id="review_final",
                    title="规则审核",
                    kind="review",
                    user_visible_reason="记录本次 cohort 执行被用户主动收窄范围。",
                )
            ])
            yield _build_execution_plan_event(trace)
            yield _update_trace_step(session, trace, step_id="repair_strategy", status="blocked", result_summary="已请求用户缩小时间范围或筛选条件。")
            yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
            yield _set_trace_review(session, trace, review)
            final_message = _build_known_final_message(
                normalized_request,
                availability=availability,
                review=review,
                extra_note="请缩小时间范围、风险条件或国家范围后重新发起 cohort 请求。",
            )
            _finalize_trace(session, trace, final_status="blocked", final_message=final_message)
            yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
            return
        yield _update_trace_step(session, trace, step_id="repair_strategy", status="done", result_summary=f"已选择策略：{selected_option}。")
        if selected_option == "analyze_existing_only":
            requested_missing = []
        elif selected_option == "repair_behavior_only":
            requested_missing = ["behavior"] if "behavior" in requested_missing else []
        else:
            requested_missing = sorted(requested_missing)

        repair_steps = []
        for bucket in requested_missing:
            repair_steps.append(PlanStep(
                step_id=f"repair_{bucket}",
                title=f"补齐 {bucket} 数据",
                kind="repair_profile_data",
                user_visible_reason=f"根据选定策略，尝试补齐 {bucket} bucket。",
                tool_name="repair_profile_data",
            ))
        _append_trace_steps(session, trace, [
            *repair_steps,
            PlanStep(
                step_id="run_profile",
                title="执行画像分析",
                kind="run_profile",
                user_visible_reason="对有真实数据支撑的模块执行画像。",
                tool_name="run_profile",
            ),
            PlanStep(
                step_id="review_final",
                title="规则审核",
                kind="review",
                user_visible_reason="核对缺失数据、执行结果和置信度影响。",
            ),
        ])
        yield _build_execution_plan_event(trace)

    for bucket in requested_missing:
        step_id = f"repair_{bucket}"
        if country_for_execution != "mx":
            yield _update_trace_step(session, trace, step_id=step_id, status="blocked", result_summary="repair 目前仅支持 mx。")
            continue
        missing_uids = list(missing_uids_by_bucket.get(bucket) or [])
        repair_input = RepairProfileDataInput(
            uids=missing_uids,
            country=country_for_execution,
            bucket=bucket,
            reason=f"{bucket} bucket 缺失，需继续执行画像",
        )
        compat_mode = (
            "prepare_then_execute"
            if repair_profile_data is _ORIGINAL_REPAIR_PROFILE_DATA
            else "legacy_ack_inside_tool"
        )
        prepare_func = None
        execute_func = None
        legacy_execute_func = None
        legacy_tool_call_id: dict[str, str] | None = None
        if compat_mode == "prepare_then_execute":
            def _prepare_repair() -> Any:
                return asyncio.to_thread(prepare_repair_query, repair_input)

            def _execute_repair(prepared: RepairPrepare | None) -> Any:
                if prepared is None:
                    raise ValueError("prepared repair payload is required")
                return asyncio.to_thread(execute_repair_query, prepared.raw_prepared or prepared)

            prepare_func = _prepare_repair
            execute_func = _execute_repair
        else:
            legacy_tool_call_id = {"value": ""}

            def _legacy_repair(before_ack) -> Any:
                return repair_profile_data(
                    repair_input,
                    session_id=session.session_id,
                    tool_call_id=legacy_tool_call_id["value"],
                    before_ack=before_ack,
                )

            legacy_execute_func = _legacy_repair

        handle = await repair_runner.start(
            RepairRunSpec(
                trace_id=trace.trace_id or trace.execution_id,
                input_payload=repair_input.model_dump(mode="json"),
                compat_mode=compat_mode,
                prepare_func=prepare_func,
                execute_func=execute_func,
                legacy_execute_func=legacy_execute_func,
                should_cancel=(
                    (lambda current_run_id=run_id: bool(current_run_id) and is_run_cancel_requested(session.session_id, current_run_id))
                    if run_id
                    else None
                ),
            )
        )
        tool_call_id = handle.record.tool_call_id
        if legacy_tool_call_id is not None:
            legacy_tool_call_id["value"] = tool_call_id

        yield _update_trace_step(session, trace, step_id=step_id, status="running", tool_call_id=tool_call_id)
        if handle.started_event is not None:
            yield handle.started_event

        repair_result: RepairRunResult | None = None
        async for item in handle.stream():
            if item.event is not None:
                yield item.event
            if item.result is not None:
                repair_result = item.result

        if repair_result is None:
            raise RuntimeError("repair runner completed without result")

        if repair_result.status == "completed":
            cancel_events = _yield_cancelled_events(trace)
            if cancel_events:
                for cancelled_evt in cancel_events:
                    yield cancelled_evt
                return
            yield _update_trace_step(session, trace, step_id=step_id, status="done", result_summary=f"已补齐 {bucket} 数据。", tool_call_id=tool_call_id)
            continue

        if repair_result.status in {"rejected", "expired"}:
            from app.services.orchestrator_agent.session import mark_query_cancelled

            if repair_result.status == "rejected":
                mark_query_cancelled(session.session_id)
            cancel_events = _request_cancelled_events(trace)
            for cancelled_evt in cancel_events:
                yield cancelled_evt
            return

        if repair_result.status == "cancelled":
            cancel_events = _yield_cancelled_events(trace) or _request_cancelled_events(trace)
            for cancelled_evt in cancel_events:
                yield cancelled_evt
            return

        yield _update_trace_step(session, trace, step_id=step_id, status="blocked", result_summary=repair_result.error or "repair failed", tool_call_id=tool_call_id)

    availability = check_data_availability(normalized_request.uids, country=country_for_execution)
    _set_trace_availability(session, trace, availability)
    uid_modules_plan = _build_uid_module_plan(availability, normalized_request)
    execution_groups = [
        (modules, uids)
        for modules, uids in _group_uid_module_plan(uid_modules_plan)
        if modules
    ]
    if not execution_groups:
        yield _update_trace_step(session, trace, step_id="run_profile", status="blocked", result_summary="没有任何基础 bucket 可用于画像。")
        review = _build_profile_review(availability, uid_modules_plan, None, normalized_request)
        yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
        yield _set_trace_review(session, trace, review)
        final_message = _build_known_final_message(
            normalized_request,
            review=review,
            availability=availability,
            extra_note="请先补齐至少一个基础 bucket，再重新发起画像。",
        )
        _finalize_trace(session, trace, final_status="blocked", final_message=final_message)
        yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
        return

    run_profile_input = {
        "uids": normalized_request.uids,
        "app_time": normalized_request.application_time_hint,
        "modules": _flatten_planned_modules(uid_modules_plan),
        "strict_data_mode": True,
    }
    tool_call_id: str | None = None
    try:
        handle = await profile_runner.start(
            ProfileRunSpec(
                trace_id=trace.trace_id or trace.execution_id,
                input_payload=run_profile_input,
                execution_groups=execution_groups,
                application_time_hint=normalized_request.application_time_hint,
                should_cancel=(
                    (lambda current_run_id=run_id: bool(current_run_id) and is_run_cancel_requested(session.session_id, current_run_id))
                    if run_id
                    else None
                ),
            )
        )
        tool_call_id = handle.record.tool_call_id
        yield _update_trace_step(session, trace, step_id="run_profile", status="running", tool_call_id=tool_call_id)
        if handle.started_event is not None:
            yield handle.started_event
        output = None
        async for item in handle.stream():
            if isinstance(item, ProfileRunResult):
                if item.completed_event is not None:
                    yield item.completed_event
                if item.status == "failed":
                    raise RuntimeError(item.error or "run_profile failed")
                output = item.output
                break
            if item.tool_progress_event is not None:
                yield item.tool_progress_event
            cancel_events = _yield_cancelled_events(trace)
            if cancel_events:
                for cancelled_evt in cancel_events:
                    yield cancelled_evt
                return
        cancel_events = _yield_cancelled_events(trace)
        if cancel_events:
            for cancelled_evt in cancel_events:
                yield cancelled_evt
            return
        if output is None:
            raise RuntimeError("run_profile completed without output")
        executed_count = sum(len(modules) * len(uids) for modules, uids in execution_groups)
        yield _update_trace_step(session, trace, step_id="run_profile", status="done", result_summary=f"已完成 {executed_count} 个模块任务。", tool_call_id=tool_call_id)
        review = _build_profile_review(availability, uid_modules_plan, output, normalized_request)
        if unavailable_missing_buckets:
            review = _append_data_acquisition_issue(
                review,
                missing_buckets=unavailable_missing_buckets,
                blocked=False,
            )
        yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
        yield _set_trace_review(session, trace, review)
        final_message = _build_known_final_message(
            normalized_request,
            profile_output=output,
            review=review,
            availability=availability,
            extra_note="可继续追问具体模块或切到左侧 dashboard 查看结构化结果。",
        )
        _finalize_trace(session, trace, final_status="completed", final_message=final_message)
        yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.89 if review.status == "pass" else 0.72, detected_country=detected_country)
        return
    except asyncio.CancelledError:
        cancel_events = _yield_cancelled_events(trace)
        for cancelled_evt in cancel_events:
            yield cancelled_evt
        return
    except Exception as exc:  # noqa: BLE001
        yield _update_trace_step(session, trace, step_id="run_profile", status="failed", result_summary=str(exc), tool_call_id=tool_call_id)
        review = ReviewResult(status="fail", issues=[{"type": "tool_error", "message": str(exc)}], can_answer=False, confidence_impact="画像执行失败")
        yield _update_trace_step(session, trace, step_id="review_final", status="done", result_summary=_review_step_summary(review))
        yield _set_trace_review(session, trace, review)
        final_message = _build_known_final_message(normalized_request, review=review, availability=availability, extra_note="请稍后重试，或先检查本地 bucket 数据。")
        _finalize_trace(session, trace, final_status="error", final_message=final_message)
        yield _persist_final_message(session, prompt=prompt, final_message=final_message, confidence=0.0, detected_country=detected_country)
        return


async def _run_general_chat_defensive_fallback(
    session: OrchestratorSession,
    *,
    prompt: str,
    normalized_request: NormalizedRequest,
    turn_id: str,
    run_id: str,
) -> AsyncGenerator[dict, None]:
    # Thin defensive fallback only. Complex or unsupported general_chat
    # requests terminate here instead of re-entering the removed full
    # general-chat LLM/tool loop. This path must not execute registry/tool
    # logic or emit an ordinary final message.
    trace = _create_execution_trace(
        session,
        execution_id=uuid.uuid4().hex,
        turn_id=turn_id,
        run_id=run_id,
        prompt=prompt,
        normalized_request=normalized_request,
        availability=None,
        steps=[
            PlanStep(
                step_id="general_answer",
                title="进入通用 Agent 模式",
                kind="general_chat",
                user_visible_reason="当前问题不匹配稳定的画像、取数或轨迹执行路径，先按通用问答处理。",
            ),
        ],
    )
    update_internal_trace_metadata(
        trace,
        {
            "flow_name": "GeneralChatFlow",
            "flow_mode": "defensive_fallback",
            "fallback_reason": "unsupported_general_chat_complex_path",
            "terminal_reason": "unsupported_general_chat_complex_path",
        },
    )
    yield _build_execution_plan_event(trace)
    failure_message = "GeneralChatFlow 6C conservatively blocks complex or unsupported general-chat tool paths"
    yield _update_trace_step(
        session,
        trace,
        step_id="general_answer",
        status="failed",
        result_summary=failure_message,
    )
    _finalize_trace(session, trace, final_status="error", final_message=failure_message)
    _set_run_status(session, run_id=run_id, status="failed")
    yield {"type": "run_failed", "message": failure_message}
    yield {"type": "error", "message": failure_message}
    session.status = "error"
    save_session(session)


async def run_agent_loop(
    session: OrchestratorSession,
    prompt: str,
    client_turn_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
) -> AsyncGenerator[dict, None]:
    yield {"type": "session_started", "session_id": session.session_id}

    turn_id = uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    turn = _create_turn(session, turn_id=turn_id, client_turn_id=client_turn_id, prompt=prompt)
    _create_turn_run(session, turn_id=turn_id, run_id=run_id)
    yield _decorate_event(
        session,
        {
            "type": "turn_started",
            "turn_id": turn_id,
            "client_turn_id": client_turn_id,
        },
        turn_id=turn_id,
        run_id=run_id,
    )
    yield _decorate_event(
        session,
        {
            "type": "run_started",
            "trace_id": None,
        },
        turn_id=turn_id,
        run_id=run_id,
    )

    detected_country = (country or _detect_country(prompt) or session.country)
    apply_identity(
        session,
        user_id=user_id,
        project_id=project_id,
        country=detected_country,
    )
    turn.user_message.run_id = run_id
    save_session(session)

    deps = build_loop_dependencies()
    client = deps.model_client_factory()
    lifecycle = SessionLifecycle(session)
    events = EventRecorder(session, turn_id=turn_id, run_id=run_id)
    # R7 P0-3 Knowledge 层注入：从 prompt 提取 country code，动态拼接国别规则段。
    # 匹不到 → country=None → base prompt 不含国别规则，LLM 需问用户。
    system_prompt = assemble_system_prompt(detected_country)
    system_prompt = append_rolling_summary(system_prompt, session)

    retrieved_context, retrieved_memories = build_retrieved_memory_context(
        session=session,
        query=prompt,
        country=detected_country,
    )
    if retrieved_context:
        system_prompt = system_prompt + "\n\n" + retrieved_context

    # Plan 10 Phase 4 集成点 1：首轮拼接长期记忆（不进 messages，仅拼 system_prompt）。
    if detected_country and len(session.messages) == 1 and not retrieved_memories:
        memory_context = load_session_memories(session.session_id, detected_country)
        if memory_context:
            system_prompt = system_prompt + "\n\n" + memory_context

    ctx = FlowContext(
        session=session,
        prompt=prompt,
        turn_id=turn_id,
        run_id=run_id,
        detected_country=detected_country,
        client=client,
        lifecycle=lifecycle,
        events=events,
        trace=TraceStore(session),
        human_input=HumanInputController(),
        tools=ToolRunner(session=session, lifecycle=lifecycle, events=events),
        memory=_build_memory_facade(session, detected_country),
        deps=deps,
        system_prompt=system_prompt,
    )

    normalized_request = deps.normalize_request(prompt, session, detected_country)
    if not normalized_request.application_time_hint:
        snapshot = session.active_entities.get("workspace_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("applicationTime"):
            normalized_request = normalized_request.model_copy(update={
                "application_time_hint": snapshot.get("applicationTime"),
            })
    if normalized_request.intent != "need_clarification":
        normalized_request = deps.refine_normalized_request(
            client,
            prompt=prompt,
            session=session,
            normalized_request=normalized_request,
        )
    workspace_evidence = None
    if normalized_request.intent == "answer_from_workspace":
        workspace_evidence = build_workspace_evidence_bundle(
            session,
            normalized_request,
            prompt,
            detected_country,
        )

    flow = select_known_flow(normalized_request)
    flow_can_handle = False
    flow_signal: FlowControlSignal | None = None
    if flow is not None:
        flow_can_handle = await flow.can_handle(ctx, normalized_request)
    if flow is not None and flow_can_handle:
        async for item in flow.run(ctx, normalized_request):
            if isinstance(item, FlowControlSignal):
                flow_signal = item
                break
            if item.get("event_id"):
                yield item
            else:
                yield _decorate_event(session, item, turn_id=turn_id, run_id=run_id)
        if flow_signal is not None:
            if flow_signal.kind == "clarification_resume":
                query_flow = QueryDataThenProfileFlow()
                prepared_query_only = None
                prepared_query_profile = None
                answers = dict(flow_signal.payload.get("answers") or {})
                if answers.get("auto_profile") is False and flow_signal.payload.get("trace") is not None:
                    prepared_query_only = query_flow.prepare_query_only_after_clarification(
                        ctx,
                        prompt=prompt,
                        answers=answers,
                    )
                if answers.get("auto_profile") is True and flow_signal.payload.get("trace") is not None:
                    prepared_query_profile = query_flow.prepare_profile_after_clarification(
                        ctx,
                        prompt=prompt,
                        answers=answers,
                    )
                if prepared_query_only is not None:
                    async for evt in query_flow.run_query_only_after_clarification(
                        ctx,
                        prepared=prepared_query_only,
                        trace=flow_signal.payload["trace"],
                    ):
                        if evt.get("event_id"):
                            yield evt
                        else:
                            yield _decorate_event(session, evt, turn_id=turn_id, run_id=run_id)
                elif prepared_query_profile is not None:
                    async for evt in query_flow.run_profile_after_query_clarification(
                        ctx,
                        prepared=prepared_query_profile,
                        trace=flow_signal.payload["trace"],
                    ):
                        if evt.get("event_id"):
                            yield evt
                        else:
                            yield _decorate_event(session, evt, turn_id=turn_id, run_id=run_id)
                else:
                    async for evt in _run_clarification_resume_legacy(
                        session,
                        prompt=prompt,
                        normalized_request=normalized_request,
                        answers=answers,
                        detected_country=detected_country,
                        client=client,
                        ctx=ctx,
                        turn_id=turn_id,
                        run_id=run_id,
                        trace=flow_signal.payload.get("trace"),
                    ):
                        if evt.get("event_id"):
                            yield evt
                        else:
                            yield _decorate_event(session, evt, turn_id=turn_id, run_id=run_id)
        return
    if normalized_request.intent != "general_chat":
        if normalized_request.intent == "answer_from_workspace" and not workspace_evidence and normalized_request.uids:
            normalized_request = _promote_workspace_request_to_profile(prompt, normalized_request)
        precomputed_availability = None
        if flow is not None and hasattr(flow, "take_cached_availability"):
            precomputed_availability = flow.take_cached_availability(normalized_request)
        async for evt in _run_known_request(
            session,
            prompt=prompt,
            normalized_request=normalized_request,
            detected_country=detected_country,
            client=client,
            ctx=ctx,
            workspace_evidence=workspace_evidence,
            turn_id=turn_id,
            run_id=run_id,
            precomputed_availability=precomputed_availability,
        ):
            if evt.get("event_id"):
                yield evt
            else:
                yield _decorate_event(session, evt, turn_id=turn_id, run_id=run_id)
        run_record = _find_run(session, run_id)
        if session.final_message or (run_record is not None and run_record.status == "cancelled"):
            return
        return

    if normalized_request.intent == "general_chat":
        async for evt in _run_general_chat_defensive_fallback(
            session,
            prompt=prompt,
            normalized_request=normalized_request,
            turn_id=turn_id,
            run_id=run_id,
        ):
            if evt.get("event_id"):
                yield evt
            else:
                yield _decorate_event(session, evt, turn_id=turn_id, run_id=run_id)
        return
