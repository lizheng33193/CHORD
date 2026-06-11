"""Shared narrow runtime helper for availability-success profile execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from app.services.orchestrator_agent.execution.profile_runner import (
    ProfileRunResult,
    ProfileRunner,
    ProfileRunSpec,
    call_tool_with_optional_progress,
    log_run_profile_progress,
)
from app.services.orchestrator_agent.finalization.final_answer_builder import build_known_final_message
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.flows.base import FlowOutput
from app.services.orchestrator_agent.planning.plan_builder import flatten_planned_modules
from app.services.orchestrator_agent.review_rules import (
    append_data_acquisition_issue,
    append_partial_repair_issue,
    build_profile_review,
    review_step_summary,
)
from app.services.orchestrator_agent.runtime.cancellation import cancel_requested
from app.services.orchestrator_agent.runtime.trace_store import (
    finalize_trace,
    set_trace_review,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import NormalizedRequest, ReviewResult


@dataclass(slots=True)
class ProfileExecutionSpec:
    source_request: NormalizedRequest
    persist_prompt: str
    trace: Any
    availability: Any
    uid_modules_plan: dict[str, list[str]]
    execution_groups: list[tuple[list[str], list[str]]]
    requested_missing: list[str]
    decision_mode: Literal["success", "partial_unavailable"] = "success"
    strict_data_mode: bool = True
    success_extra_note: str = "可继续追问具体模块或切到左侧 dashboard 查看结构化结果。"
    blocked_extra_note: str = "请检查本地 bucket 完整性后重试。"
    failure_extra_note: str = "请稍后重试，或先检查本地 bucket 数据。"


async def execute_profile_runtime(
    ctx,
    *,
    spec: ProfileExecutionSpec,
    tools_mod,
) -> AsyncIterator[FlowOutput]:
    request = spec.source_request
    trace = spec.trace

    if not spec.execution_groups:
        review = ReviewResult(
            status="fail",
            issues=[{"type": "profile_flow_gate_mismatch", "message": "当前请求没有可运行模块。"}],
            can_answer=False,
            confidence_impact="ProfileFlow gate 与执行规划不一致，已阻断执行",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="run_profile",
            status="blocked",
            result_summary="当前请求没有可运行模块。",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="review_final",
            status="done",
            result_summary=review_step_summary(review),
        )
        yield set_trace_review(ctx.session, trace, review)
        final_message = build_known_final_message(
            request,
            review=review,
            availability=spec.availability,
            extra_note=spec.blocked_extra_note,
        )
        finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=spec.persist_prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )
        return

    profile_runner = ProfileRunner(
        session=ctx.session,
        lifecycle=ctx.lifecycle,
        events=ctx.events,
        progress_logger=log_run_profile_progress,
        profile_executor=lambda input_obj, progress_callback=None: call_tool_with_optional_progress(
            tools_mod.run_profile,
            input_obj,
            progress_callback,
        ),
    )
    run_profile_input = {
        "uids": request.uids,
        "app_time": request.application_time_hint,
        "modules": flatten_planned_modules(spec.uid_modules_plan),
        "strict_data_mode": spec.strict_data_mode,
    }
    tool_call_id: str | None = None
    try:
        handle = await profile_runner.start(
            ProfileRunSpec(
                trace_id=trace.trace_id or trace.execution_id,
                input_payload=run_profile_input,
                execution_groups=spec.execution_groups,
                application_time_hint=request.application_time_hint,
                should_cancel=None,
            )
        )
        tool_call_id = handle.record.tool_call_id
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="run_profile",
            status="running",
            tool_call_id=tool_call_id,
        )
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
            cancel_events = cancel_requested(
                ctx.session,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
                trace=trace,
            ) or []
            if cancel_events:
                for evt in cancel_events:
                    yield evt
                return

        cancel_events = cancel_requested(
            ctx.session,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            trace=trace,
        ) or []
        if cancel_events:
            for evt in cancel_events:
                yield evt
            return

        if output is None:
            raise RuntimeError("run_profile completed without output")

        executed_count = sum(len(modules) * len(uids) for modules, uids in spec.execution_groups)
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="run_profile",
            status="done",
            result_summary=f"已完成 {executed_count} 个模块任务。",
            tool_call_id=tool_call_id,
        )
        review = build_profile_review(spec.availability, spec.uid_modules_plan, output, request)
        if spec.decision_mode == "partial_unavailable":
            review = append_data_acquisition_issue(
                review,
                missing_buckets=spec.requested_missing,
                blocked=False,
            )
            review = append_partial_repair_issue(
                review,
                missing_buckets=spec.requested_missing,
            )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="review_final",
            status="done",
            result_summary=review_step_summary(review),
        )
        yield set_trace_review(ctx.session, trace, review)
        final_message = build_known_final_message(
            request,
            profile_output=output,
            review=review,
            availability=spec.availability,
            extra_note=spec.success_extra_note,
        )
        finalize_trace(ctx.session, trace, final_status="completed", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=spec.persist_prompt,
            final_message=final_message,
            confidence=0.89 if review.status == "pass" else 0.72,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )
        return
    except asyncio.CancelledError:
        cancel_events = cancel_requested(
            ctx.session,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            trace=trace,
        ) or []
        for evt in cancel_events:
            yield evt
        return
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="run_profile",
            status="failed",
            result_summary=error_message,
            tool_call_id=tool_call_id,
        )
        review = ReviewResult(
            status="fail",
            issues=[{"type": "tool_error", "message": error_message}],
            can_answer=False,
            confidence_impact="画像执行失败",
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="review_final",
            status="done",
            result_summary=review_step_summary(review),
        )
        yield set_trace_review(ctx.session, trace, review)
        final_message = build_known_final_message(
            request,
            review=review,
            availability=spec.availability,
            extra_note=spec.failure_extra_note,
        )
        finalize_trace(ctx.session, trace, final_status="error", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=spec.persist_prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )
