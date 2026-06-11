"""Migrated known flow for the no-repair profile_uid/profile_batch success paths."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from app.core.data_acquisition_capability import data_acquisition_unavailable_message
from app.services.orchestrator_agent.execution.profile_runner import (
    ProfileRunResult,
    ProfileRunner,
    ProfileRunSpec,
    call_tool_with_optional_progress,
    log_run_profile_progress,
)
from app.services.orchestrator_agent.execution.repair_runner import (
    RepairPrepare,
    RepairRunResult,
    RepairRunSpec,
    RepairRunner,
)
from app.services.orchestrator_agent.execution.tool_runner import ToolRunSpec
from app.services.orchestrator_agent.finalization.final_answer_builder import build_known_final_message
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.flows.base import FlowOutput
from app.services.orchestrator_agent.flows._profile_runtime import (
    ProfileExecutionSpec,
    execute_profile_runtime,
)
from app.services.orchestrator_agent.planning.availability_summary import availability_summary
from app.services.orchestrator_agent.planning.plan_builder import (
    build_uid_module_plan,
    flatten_planned_modules,
    group_uid_module_plan,
    required_buckets_for_request,
)
from app.services.orchestrator_agent.review_rules import (
    append_data_acquisition_issue,
    append_partial_repair_issue,
    build_profile_review,
    review_step_summary,
)
from app.services.orchestrator_agent.runtime.cancellation import cancel_requested
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    append_trace_steps,
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    set_trace_availability,
    set_trace_review,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import (
    ExecutionTraceRecord,
    NormalizedRequest,
    ParseUidFileInput,
    PlanStep,
    RepairProfileDataInput,
    ReviewResult,
)
from app.services.orchestrator_agent.session import (
    is_run_cancel_requested,
    mark_query_cancelled,
    request_run_cancel,
)

_REPAIR_BUCKET_PRIORITY = {
    "credit": 10,
    "behavior": 20,
    "app": 30,
}


@dataclass(slots=True)
class _ProfileGateDecision:
    mode: Literal[
        "success",
        "partial_unavailable",
        "blocked_unavailable",
        "uid_file_parse",
        "repair_ready",
        "legacy_repair",
        "not_applicable",
    ]
    availability: Any | None = None
    uid_modules_plan: dict[str, list[str]] | None = None
    execution_groups: list[tuple[list[str], list[str]]] | None = None
    requested_missing: list[str] | None = None
    missing_uids_by_bucket: dict[str, list[str]] | None = None
    capability_enabled: bool | None = None
    capability: Any | None = None


@dataclass(slots=True)
class _ParsedUidFileResult:
    uids: list[str]
    error: str | None = None


class ProfileFlow:
    intent = "profile_uid"
    intents = {"profile_uid", "profile_batch"}

    def __init__(self) -> None:
        self._cached_decision: _ProfileGateDecision | None = None
        self._cached_request_key: tuple | None = None

    def _update_trace_metadata(self, trace: ExecutionTraceRecord, **values: Any) -> None:
        update_internal_trace_metadata(
            trace,
            {
                key: value
                for key, value in values.items()
                if value is not None
            },
        )

    def _ordered_repair_buckets(self, buckets: list[str]) -> list[str]:
        return sorted(
            buckets,
            key=lambda bucket: (_REPAIR_BUCKET_PRIORITY.get(bucket, 999), bucket),
        )

    def _build_plan_event_for_steps(self, trace, steps: list[PlanStep]) -> dict[str, Any]:
        return build_execution_plan_event(trace.model_copy(update={"steps": steps}))

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        decision = self._build_gate_decision(ctx, request)
        self._cache_decision(request, decision)
        return decision.mode in {"success", "partial_unavailable", "blocked_unavailable", "uid_file_parse", "repair_ready"}

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[FlowOutput]:
        from app.services.orchestrator_agent import tools as tools_mod

        decision = self._pop_cached_decision(request) or self._build_gate_decision(ctx, request)
        if decision.mode == "uid_file_parse":
            async for event in self._run_uid_file_parse_path(ctx, request, decision, tools_mod):
                yield event
            return
        if decision.mode == "repair_ready":
            async for event in self._run_repair_path(ctx, request, decision, tools_mod):
                yield event
            return
        if decision.mode not in {"success", "partial_unavailable", "blocked_unavailable"}:
            raise RuntimeError(f"ProfileFlow gate decision mismatch: {decision.mode}")
        async for event in self._run_profile_decision(ctx, request, decision, tools_mod):
            yield event

    async def _run_profile_decision(
        self,
        ctx,
        request: NormalizedRequest,
        decision: _ProfileGateDecision,
        tools_mod,
        *,
        trace=None,
    ) -> AsyncIterator[FlowOutput]:
        if decision.mode not in {"success", "partial_unavailable", "blocked_unavailable"}:
            raise RuntimeError(f"ProfileFlow gate decision mismatch: {decision.mode}")

        availability = decision.availability or self._load_availability(ctx, request)
        uid_modules_plan = decision.uid_modules_plan or build_uid_module_plan(availability, request)
        execution_groups = list(decision.execution_groups or [])
        requested_missing = list(decision.requested_missing or [])
        unavailable_reason = None
        if decision.mode in {"partial_unavailable", "blocked_unavailable"}:
            unavailable_reason = data_acquisition_unavailable_message(decision.capability)

        steps = [
            PlanStep(
                step_id="check_data",
                title="检查数据完整性",
                kind="check_data",
                user_visible_reason="直接检查本地 by_uid bucket，不使用 sample fallback。",
            ),
        ]
        if decision.mode in {"partial_unavailable", "blocked_unavailable"}:
            steps.append(
                PlanStep(
                    step_id="data_acquisition_unavailable",
                    title="无法自动补数",
                    kind="data_acquisition_unavailable",
                    user_visible_reason="当前环境未启用或缺少 Data Agent 依赖，无法补齐本次请求真正缺失的 bucket。",
                )
            )
        if decision.mode != "blocked_unavailable":
            steps.append(
                PlanStep(
                    step_id="run_profile",
                    title="执行画像分析",
                    kind="run_profile",
                    user_visible_reason="对有真实数据支撑的模块执行画像。",
                    tool_name="run_profile",
                )
            )
        steps.append(
            PlanStep(
                step_id="review_final",
                title="规则审核",
                kind="review",
                user_visible_reason="核对缺失数据、执行结果和置信度影响。",
            )
        )

        if trace is None:
            trace = create_execution_trace(
                ctx.session,
                execution_id=uuid.uuid4().hex,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
                prompt=ctx.prompt,
                normalized_request=request,
                availability=availability,
                steps=steps,
            )
        else:
            set_trace_availability(ctx.session, trace, availability)
            append_trace_steps(ctx.session, trace, steps)
        self._update_trace_metadata(
            trace,
            flow_name="ProfileFlow",
            decision_mode=decision.mode,
            uid_count=len(request.uids),
            country=self._country_for_execution(ctx, request),
            requested_missing=requested_missing or None,
            execution_group_count=len(execution_groups) if execution_groups else None,
            capability_enabled=decision.capability_enabled,
        )
        yield (
            build_execution_plan_event(trace)
            if trace.availability is None or len(trace.steps) == len(steps)
            else self._build_plan_event_for_steps(trace, steps)
        )
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="check_data",
            status="done",
            result_summary=availability_summary(availability),
        )

        if decision.mode in {"partial_unavailable", "blocked_unavailable"}:
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="data_acquisition_unavailable",
                status="skipped" if decision.mode == "partial_unavailable" else "blocked",
                result_summary=f"缺失 {', '.join(requested_missing)} 数据，{unavailable_reason}",
            )

        if decision.mode == "blocked_unavailable":
            async for event in self._finalize_blocked_unavailable(
                ctx,
                request,
                trace,
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                requested_missing=requested_missing,
                unavailable_reason=unavailable_reason or "",
            ):
                yield event
            return

        async for event in self._execute_profile_run_and_finalize(
            ctx,
            request,
            trace,
            availability=availability,
            uid_modules_plan=uid_modules_plan,
            execution_groups=execution_groups,
            requested_missing=requested_missing,
            decision_mode=decision.mode,
            tools_mod=tools_mod,
        ):
            yield event

    async def _run_uid_file_parse_path(self, ctx, request: NormalizedRequest, decision: _ProfileGateDecision, tools_mod) -> AsyncIterator[FlowOutput]:
        if not request.uid_file_path:
            raise RuntimeError("ProfileFlow uid_file parse path missing uid_file_path")

        trace = create_execution_trace(
            ctx.session,
            execution_id=uuid.uuid4().hex,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            prompt=ctx.prompt,
            normalized_request=request,
            availability=None,
            steps=[
                PlanStep(
                    step_id="parse_uid_file",
                    title="解析 UID 文件",
                    kind="parse_uid_file",
                    user_visible_reason="先从本地 UID 文件中提取待分析的用户列表。",
                    tool_name="parse_uid_file",
                )
            ],
        )
        self._update_trace_metadata(
            trace,
            flow_name="ProfileFlow",
            decision_mode="uid_file_parse",
            country=self._country_for_execution(ctx, request),
            capability_enabled=decision.capability_enabled,
        )
        yield build_execution_plan_event(trace)

        handle = await ctx.tools.start(
            ToolRunSpec(
                name="parse_uid_file",
                func=tools_mod.parse_uid_file,
                input_payload={"file_path": request.uid_file_path},
                call_args=(ParseUidFileInput(file_path=request.uid_file_path),),
                trace_id=trace.trace_id or trace.execution_id,
            )
        )
        tool_call_id = handle.record.tool_call_id
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="parse_uid_file",
            status="running",
            tool_call_id=tool_call_id,
        )
        if handle.started_event is not None:
            yield handle.started_event
        result = await handle.execute()
        if result.completed_event is not None:
            yield result.completed_event

        if result.status != "completed":
            error_message = result.error or "UID 文件解析失败"
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="parse_uid_file",
                status="failed",
                result_summary=error_message,
                tool_call_id=tool_call_id,
            )
            async for event in self._finalize_uid_file_terminal_path(
                ctx,
                request,
                trace,
                review=ReviewResult(
                    status="fail",
                    issues=[{"type": "tool_error", "message": error_message}],
                    can_answer=False,
                    confidence_impact="UID 文件解析失败",
                ),
                final_status="error",
                extra_note="请检查文件路径是否正确，且文件位于 data/id_files/ 下。",
                terminal_reason="tool_error",
            ):
                yield event
            return

        parsed = self._normalize_parse_uid_file_output(result.output)
        if parsed.error:
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="parse_uid_file",
                status="failed",
                result_summary=parsed.error,
                tool_call_id=tool_call_id,
            )
            async for event in self._finalize_uid_file_terminal_path(
                ctx,
                request,
                trace,
                review=ReviewResult(
                    status="fail",
                    issues=[{"type": "tool_error", "message": parsed.error}],
                    can_answer=False,
                    confidence_impact="UID 文件解析结果异常",
                ),
                final_status="error",
                extra_note="请检查 UID 文件格式后重试。",
                terminal_reason="tool_error",
            ):
                yield event
            return

        parsed_uids = parsed.uids
        self._update_trace_metadata(trace, parsed_uid_count=len(parsed_uids))
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="parse_uid_file",
            status="done",
            result_summary=f"已从文件中解析出 {len(parsed_uids)} 个 UID。",
            tool_call_id=tool_call_id,
        )
        if not parsed_uids:
            async for event in self._finalize_uid_file_terminal_path(
                ctx,
                request,
                trace,
                review=ReviewResult(
                    status="fail",
                    issues=[{"type": "empty_uid_file", "message": "UID 文件中没有可用 UID"}],
                    can_answer=False,
                    confidence_impact="没有可执行的 UID，已阻断画像",
                ),
                final_status="blocked",
                extra_note="请检查 UID 文件内容是否有效，或改为直接输入 UID。",
            ):
                yield event
            return

        resolved_request = request.model_copy(update={"uids": parsed_uids, "uid_file_path": None})
        resolved_decision = self._build_gate_decision(ctx, resolved_request)
        if resolved_decision.mode == "repair_ready":
            async for event in self._run_repair_path(
                ctx,
                resolved_request,
                resolved_decision,
                tools_mod,
                trace=trace,
            ):
                yield event
            return

        if resolved_decision.mode not in {"success", "partial_unavailable", "blocked_unavailable"}:
            review = ReviewResult(
                status="fail",
                issues=[{"type": "profile_flow_gate_mismatch", "message": "解析出的 UID 当前不在本轮迁移覆盖范围内。"}],
                can_answer=False,
                confidence_impact="当前文件画像请求需要更复杂的后续处理，已阻断执行",
            )
            async for event in self._finalize_uid_file_terminal_path(
                ctx,
                resolved_request,
                trace,
                review=review,
                final_status="blocked",
                extra_note="当前文件画像请求超出本轮接管范围，请缩小画像范围或补齐本地数据后重试。",
            ):
                yield event
            return

        async for event in self._run_profile_decision(ctx, resolved_request, resolved_decision, tools_mod, trace=trace):
            yield event

    async def _execute_profile_run_and_finalize(
        self,
        ctx,
        request: NormalizedRequest,
        trace,
        *,
        availability,
        uid_modules_plan: dict[str, list[str]],
        execution_groups: list[tuple[list[str], list[str]]],
        requested_missing: list[str],
        decision_mode: Literal["success", "partial_unavailable"],
        tools_mod,
    ) -> AsyncIterator[FlowOutput]:
        async for event in execute_profile_runtime(
            ctx,
            spec=ProfileExecutionSpec(
                source_request=request,
                persist_prompt=ctx.prompt,
                trace=trace,
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=requested_missing,
                decision_mode=decision_mode,
            ),
            tools_mod=tools_mod,
        ):
            yield event

    async def _finalize_blocked_unavailable(
        self,
        ctx,
        request: NormalizedRequest,
        trace,
        *,
        availability,
        uid_modules_plan: dict[str, list[str]],
        requested_missing: list[str],
        unavailable_reason: str,
    ) -> AsyncIterator[FlowOutput]:
        review = append_data_acquisition_issue(
            build_profile_review(availability, uid_modules_plan, None, request),
            missing_buckets=requested_missing,
            blocked=True,
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
            availability=availability,
            review=review,
            extra_note=f"{unavailable_reason} 请直接提供 UID/UID 文件，或补齐本地 bucket 后重试。",
        )
        self._update_trace_metadata(trace, terminal_reason="blocked_unavailable")
        finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )

    async def _run_repair_path(
        self,
        ctx,
        request: NormalizedRequest,
        decision: _ProfileGateDecision,
        tools_mod,
        *,
        trace=None,
    ) -> AsyncIterator[FlowOutput]:
        if decision.mode != "repair_ready":
            raise RuntimeError(f"ProfileFlow repair gate mismatch: {decision.mode}")

        availability = decision.availability or self._load_availability(ctx, request)
        requested_missing = self._ordered_repair_buckets(list(decision.requested_missing or []))
        missing_uids_by_bucket = dict(
            decision.missing_uids_by_bucket
            or self._missing_uids_by_bucket(availability, request)
        )
        steps = [
            PlanStep(
                step_id="check_data",
                title="检查数据完整性",
                kind="check_data",
                user_visible_reason="直接检查本地 by_uid bucket，不使用 sample fallback。",
            ),
            *[
                PlanStep(
                    step_id=f"repair_{bucket}",
                    title=f"补齐 {bucket} 数据",
                    kind="repair_profile_data",
                    user_visible_reason=f"本地缺少 {bucket} bucket，尝试通过 Data Agent 补数。",
                    tool_name="repair_profile_data",
                )
                for bucket in requested_missing
            ],
            PlanStep(
                step_id="run_profile",
                title="执行画像分析",
                kind="run_profile",
                user_visible_reason="对修复后数据执行画像。",
                tool_name="run_profile",
            ),
            PlanStep(
                step_id="review_final",
                title="规则审核",
                kind="review",
                user_visible_reason="核对补数结果、执行结果和置信度影响。",
            ),
        ]
        if trace is None:
            trace = create_execution_trace(
                ctx.session,
                execution_id=uuid.uuid4().hex,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
                prompt=ctx.prompt,
                normalized_request=request,
                availability=availability,
                steps=steps,
            )
            self._update_trace_metadata(
                trace,
                flow_name="ProfileFlow",
                decision_mode="repair_ready",
                uid_count=len(request.uids),
                country=self._country_for_execution(ctx, request),
                requested_missing=requested_missing or None,
                repair_buckets=requested_missing or None,
                execution_group_count=len(list(decision.execution_groups or [])) or None,
                capability_enabled=decision.capability_enabled,
            )
            yield build_execution_plan_event(trace)
        else:
            set_trace_availability(ctx.session, trace, availability)
            append_trace_steps(ctx.session, trace, steps)
            self._update_trace_metadata(
                trace,
                flow_name="ProfileFlow",
                decision_mode="repair_ready",
                uid_count=len(request.uids),
                country=self._country_for_execution(ctx, request),
                requested_missing=requested_missing or None,
                repair_buckets=requested_missing or None,
                execution_group_count=len(list(decision.execution_groups or [])) or None,
                capability_enabled=decision.capability_enabled,
            )
            yield self._build_plan_event_for_steps(trace, steps)
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="check_data",
            status="done",
            result_summary=availability_summary(availability),
        )

        compat_mode = (
            "prepare_then_execute"
            if ctx.deps.repair_profile_data is ctx.deps.original_repair_profile_data
            else "legacy_ack_inside_tool"
        )
        for bucket in requested_missing:
            step_id = f"repair_{bucket}"
            missing_uids = list(missing_uids_by_bucket.get(bucket) or [])
            repair_input = RepairProfileDataInput(
                uids=missing_uids,
                country=self._country_for_execution(ctx, request),
                bucket=bucket,
                reason=f"{bucket} bucket 缺失，需继续执行画像",
            )
            legacy_tool_call_id: dict[str, str] | None = None
            prepare_func = None
            execute_func = None
            legacy_execute_func = None
            if compat_mode == "prepare_then_execute":
                def _prepare_repair(current_input=repair_input):
                    prepared = ctx.deps.prepare_repair_query(current_input)
                    return RepairPrepare(
                        sql_text=getattr(prepared, "sql_text", ""),
                        rows_estimated=int(getattr(prepared, "rows_estimated", -1) or -1),
                        raw_prepared=getattr(prepared, "raw_prepared", prepared),
                    )

                def _execute_repair(prepared: RepairPrepare | None):
                    if prepared is None:
                        raise ValueError("prepared repair payload is required")
                    return ctx.deps.execute_repair_query(prepared.raw_prepared or prepared)

                prepare_func = _prepare_repair
                execute_func = _execute_repair
            else:
                legacy_tool_call_id = {"value": ""}

                def _legacy_repair(before_ack, current_input=repair_input):
                    return ctx.deps.repair_profile_data(
                        current_input,
                        session_id=ctx.session.session_id,
                        tool_call_id=legacy_tool_call_id["value"],
                        before_ack=before_ack,
                    )

                legacy_execute_func = _legacy_repair

            repair_runner = RepairRunner(
                session=ctx.session,
                lifecycle=ctx.lifecycle,
                events=ctx.events,
                human_input=ctx.human_input,
            )
            handle = await repair_runner.start(
                RepairRunSpec(
                    trace_id=trace.trace_id or trace.execution_id,
                    input_payload=repair_input.model_dump(mode="json"),
                    compat_mode=compat_mode,
                    prepare_func=prepare_func,
                    execute_func=execute_func,
                    legacy_execute_func=legacy_execute_func,
                    should_cancel=(
                        (lambda current_run_id=ctx.run_id: bool(current_run_id) and is_run_cancel_requested(ctx.session.session_id, current_run_id))
                        if ctx.run_id
                        else None
                    ),
                )
            )
            tool_call_id = handle.record.tool_call_id
            if legacy_tool_call_id is not None:
                legacy_tool_call_id["value"] = tool_call_id
            yield update_trace_step(
                ctx.session,
                trace,
                step_id=step_id,
                status="running",
                tool_call_id=tool_call_id,
            )
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
                yield update_trace_step(
                    ctx.session,
                    trace,
                    step_id=step_id,
                    status="done",
                    result_summary=f"已补齐 {bucket} 数据。",
                    tool_call_id=tool_call_id,
                )
                continue
            if repair_result.status in {"rejected", "expired"}:
                self._update_trace_metadata(
                    trace,
                    ack_result=repair_result.status,
                    terminal_reason="ack_rejected" if repair_result.status == "rejected" else "ack_expired",
                )
                if repair_result.status == "rejected":
                    mark_query_cancelled(ctx.session.session_id)
                request_run_cancel(ctx.session.session_id, ctx.run_id)
                cancel_events = cancel_requested(
                    ctx.session,
                    turn_id=ctx.turn_id,
                    run_id=ctx.run_id,
                    trace=trace,
                ) or []
                for evt in cancel_events:
                    yield evt
                return
            if repair_result.status == "cancelled":
                self._update_trace_metadata(trace, ack_result="cancelled", terminal_reason="ack_cancelled")
                cancel_events = cancel_requested(
                    ctx.session,
                    turn_id=ctx.turn_id,
                    run_id=ctx.run_id,
                    trace=trace,
                ) or []
                if not cancel_events:
                    request_run_cancel(ctx.session.session_id, ctx.run_id)
                    cancel_events = cancel_requested(
                        ctx.session,
                        turn_id=ctx.turn_id,
                        run_id=ctx.run_id,
                        trace=trace,
                    ) or []
                for evt in cancel_events:
                    yield evt
                return
            yield update_trace_step(
                ctx.session,
                trace,
                step_id=step_id,
                status="failed",
                result_summary=repair_result.error or "repair failed",
                tool_call_id=tool_call_id,
            )
            async for event in self._finalize_profile_terminal_path(
                ctx,
                request,
                trace,
                availability=availability,
                review=ReviewResult(
                    status="fail",
                    issues=[{"type": "tool_error", "message": repair_result.error or "repair failed"}],
                    can_answer=False,
                    confidence_impact="补数执行失败",
                ),
                final_status="error",
                extra_note="请稍后重试，或先检查补数链路配置。",
                terminal_reason="tool_error",
            ):
                yield event
            return

        is_batch_like = request.intent == "profile_batch" or (
            request.intent == "profile_uid" and len(request.uids) > 1
        )
        post_decision = self._build_post_repair_decision(ctx, request)
        if is_batch_like and post_decision.mode == "partial_unavailable" and post_decision.execution_groups:
            post_availability = post_decision.availability or self._load_availability(ctx, request)
            set_trace_availability(ctx.session, trace, post_availability)
            async for event in self._execute_profile_run_and_finalize(
                ctx,
                request,
                trace,
                availability=post_availability,
                uid_modules_plan=post_decision.uid_modules_plan or build_uid_module_plan(post_availability, request),
                execution_groups=list(post_decision.execution_groups or []),
                requested_missing=list(post_decision.requested_missing or []),
                decision_mode="partial_unavailable",
                tools_mod=tools_mod,
            ):
                yield event
            return

        if post_decision.mode != "success":
            post_availability = post_decision.availability or self._load_availability(ctx, request)
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="run_profile",
                status="blocked",
                result_summary="repair 完成后仍未达到可执行成功路径。",
            )
            async for event in self._finalize_profile_terminal_path(
                ctx,
                request,
                trace,
                availability=post_availability,
                review=ReviewResult(
                    status="fail",
                    issues=[{"type": "profile_flow_gate_mismatch", "message": f"repair 后得到 {post_decision.mode}，当前阶段不继续执行画像。"}],
                    can_answer=False,
                    confidence_impact="补数后仍无法进入稳定画像路径",
                ),
                final_status="blocked",
                extra_note="请检查补数结果与 bucket 完整性后重试。",
                terminal_reason="blocked_unavailable",
            ):
                yield event
            return

        post_availability = post_decision.availability or self._load_availability(ctx, request)
        set_trace_availability(ctx.session, trace, post_availability)
        async for event in self._execute_profile_run_and_finalize(
            ctx,
            request,
            trace,
            availability=post_availability,
            uid_modules_plan=post_decision.uid_modules_plan or build_uid_module_plan(post_availability, request),
            execution_groups=list(post_decision.execution_groups or []),
            requested_missing=[],
            decision_mode="success",
            tools_mod=tools_mod,
        ):
            yield event

    async def _finalize_profile_terminal_path(
        self,
        ctx,
        request: NormalizedRequest,
        trace,
        *,
        availability,
        review: ReviewResult,
        final_status: Literal["blocked", "error"],
        extra_note: str,
        terminal_reason: str | None = None,
    ) -> AsyncIterator[FlowOutput]:
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
            availability=availability,
            extra_note=extra_note,
        )
        self._update_trace_metadata(trace, terminal_reason=terminal_reason)
        finalize_trace(ctx.session, trace, final_status=final_status, final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )

    async def _finalize_uid_file_terminal_path(
        self,
        ctx,
        request: NormalizedRequest,
        trace,
        *,
        review: ReviewResult,
        final_status: Literal["blocked", "error"],
        extra_note: str,
        terminal_reason: str | None = None,
    ) -> AsyncIterator[FlowOutput]:
        append_trace_steps(
            ctx.session,
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
        yield build_execution_plan_event(trace)
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
            extra_note=extra_note,
        )
        self._update_trace_metadata(trace, terminal_reason=terminal_reason)
        finalize_trace(ctx.session, trace, final_status=final_status, final_message=final_message)
        yield persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=0.0,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )

    def _load_availability(self, ctx, request: NormalizedRequest):
        country_for_execution = self._country_for_execution(ctx, request)
        return ctx.deps.check_data_availability(request.uids, country=country_for_execution)

    def _build_gate_decision(self, ctx, request: NormalizedRequest) -> _ProfileGateDecision:
        if request.intent not in self.intents:
            return _ProfileGateDecision(mode="not_applicable")
        if request.uid_file_path and not request.uids:
            capability_enabled, capability = self._resolve_capability(ctx)
            if capability_enabled in {True, False}:
                return _ProfileGateDecision(
                    mode="uid_file_parse",
                    capability_enabled=capability_enabled,
                    capability=capability,
                )
            return _ProfileGateDecision(mode="not_applicable", capability=capability)
        if not request.uids:
            return _ProfileGateDecision(mode="not_applicable")
        if request.uid_file_path:
            return _ProfileGateDecision(mode="not_applicable")

        return self._build_availability_decision(ctx, request, allow_repair=True)

    def _build_post_repair_decision(self, ctx, request: NormalizedRequest) -> _ProfileGateDecision:
        return self._build_availability_decision(ctx, request, allow_repair=False)

    def _build_availability_decision(
        self,
        ctx,
        request: NormalizedRequest,
        *,
        allow_repair: bool,
    ) -> _ProfileGateDecision:
        availability = self._load_availability(ctx, request)
        uid_modules_plan = build_uid_module_plan(availability, request)
        execution_groups = [
            (modules, uids)
            for modules, uids in group_uid_module_plan(uid_modules_plan)
            if modules
        ]
        missing_uids_by_bucket = self._missing_uids_by_bucket(availability, request)
        requested_missing = sorted(missing_uids_by_bucket.keys())
        if not requested_missing:
            if not execution_groups:
                return _ProfileGateDecision(
                    mode="not_applicable",
                    availability=availability,
                    uid_modules_plan=uid_modules_plan,
                    execution_groups=execution_groups,
                    requested_missing=[],
                    missing_uids_by_bucket=missing_uids_by_bucket,
                )
            return _ProfileGateDecision(
                mode="success",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=[],
                missing_uids_by_bucket=missing_uids_by_bucket,
            )

        capability_enabled, capability = self._resolve_capability(ctx)
        if not allow_repair:
            return _ProfileGateDecision(
                mode="partial_unavailable" if execution_groups else "blocked_unavailable",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=requested_missing,
                missing_uids_by_bucket=missing_uids_by_bucket,
                capability_enabled=capability_enabled,
                capability=capability,
            )
        if capability_enabled is True:
            if self._can_run_repair_ready(ctx, request, requested_missing, missing_uids_by_bucket):
                return _ProfileGateDecision(
                    mode="repair_ready",
                    availability=availability,
                    uid_modules_plan=uid_modules_plan,
                    execution_groups=execution_groups,
                    requested_missing=requested_missing,
                    missing_uids_by_bucket=missing_uids_by_bucket,
                    capability_enabled=True,
                    capability=capability,
                )
            return _ProfileGateDecision(
                mode="legacy_repair",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=requested_missing,
                missing_uids_by_bucket=missing_uids_by_bucket,
                capability_enabled=True,
                capability=capability,
            )
        if capability_enabled is False:
            return _ProfileGateDecision(
                mode="partial_unavailable" if execution_groups else "blocked_unavailable",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=requested_missing,
                missing_uids_by_bucket=missing_uids_by_bucket,
                capability_enabled=False,
                capability=capability,
            )
        return _ProfileGateDecision(
            mode="not_applicable",
            availability=availability,
            uid_modules_plan=uid_modules_plan,
            execution_groups=execution_groups,
            requested_missing=requested_missing,
            missing_uids_by_bucket=missing_uids_by_bucket,
            capability_enabled=None,
            capability=capability,
        )

    def _country_for_execution(self, ctx, request: NormalizedRequest) -> str:
        return request.country or ctx.detected_country or ctx.session.country or "mx"

    def _can_run_repair_ready(
        self,
        ctx,
        request: NormalizedRequest,
        requested_missing: list[str],
        missing_uids_by_bucket: dict[str, list[str]],
    ) -> bool:
        if request.uid_file_path is not None or self._country_for_execution(ctx, request) != "mx":
            return False
        if request.intent == "profile_uid" and len(request.uids) == 1:
            return len(requested_missing) in {1, 2} and all(
                bool(missing_uids_by_bucket.get(bucket))
                for bucket in requested_missing
            )

        is_batch_like = request.intent == "profile_batch" or (
            request.intent == "profile_uid" and len(request.uids) > 1
        )
        return (
            is_batch_like
            and len(request.uids) > 1
            and len(requested_missing) in {1, 2}
            and all(
                bucket in _REPAIR_BUCKET_PRIORITY and bool(missing_uids_by_bucket.get(bucket))
                for bucket in requested_missing
            )
        )

    def _missing_uids_by_bucket(self, availability, request: NormalizedRequest) -> dict[str, list[str]]:
        missing_uids_by_bucket: dict[str, list[str]] = {}
        required_buckets = required_buckets_for_request(request.modules)
        for row in availability.per_uid:
            for bucket in row.missing_buckets:
                if bucket in required_buckets:
                    missing_uids_by_bucket.setdefault(bucket, []).append(row.uid)
        return missing_uids_by_bucket

    def _resolve_capability(self, ctx) -> tuple[bool | None, Any | None]:
        try:
            capability = ctx.deps.get_data_acquisition_capability()
        except Exception:  # noqa: BLE001
            return None, None
        if capability is None:
            return None, None
        enabled = getattr(capability, "enabled", None)
        if enabled is True:
            return True, capability
        if enabled is False:
            return False, capability
        return None, capability

    def _normalize_parse_uid_file_output(self, output: Any) -> _ParsedUidFileResult:
        if output is None:
            return _ParsedUidFileResult(uids=[], error="UID 文件解析结果为空")
        if hasattr(output, "model_dump"):
            output = output.model_dump(mode="json")
        if not isinstance(output, dict):
            return _ParsedUidFileResult(uids=[], error="UID 文件解析结果格式异常")
        raw_uids = output.get("uids")
        if raw_uids is None:
            return _ParsedUidFileResult(uids=[], error="UID 文件解析结果缺少 uids 字段")
        if not isinstance(raw_uids, list):
            return _ParsedUidFileResult(uids=[], error="UID 文件解析结果中的 uids 字段格式异常")
        return _ParsedUidFileResult(uids=[str(uid) for uid in raw_uids if str(uid).strip()])

    def _request_key(self, request: NormalizedRequest) -> tuple:
        return (
            request.intent,
            tuple(request.uids),
            request.uid_file_path,
            tuple(request.modules),
            request.country,
            request.application_time_hint,
        )

    def _cache_decision(self, request: NormalizedRequest, decision: _ProfileGateDecision) -> None:
        self._cached_request_key = self._request_key(request)
        self._cached_decision = decision

    def _pop_cached_decision(self, request: NormalizedRequest):
        if self._cached_request_key != self._request_key(request):
            return None
        decision = self._cached_decision
        self._cached_request_key = None
        self._cached_decision = None
        return decision

    def take_cached_availability(self, request: NormalizedRequest):
        decision = self._pop_cached_decision(request)
        return decision.availability if decision is not None else None
