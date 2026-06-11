"""Migrated known flow for query_data_then_profile guard, query, profile, and repair paths."""

from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from app.auth.permissions import require_permissions
from app.core.audit import record_runtime_audit_event
from app.core.data_acquisition_capability import data_acquisition_unavailable_message
from app.services.orchestrator_agent.execution.data_query_runner import (
    DataQueryPreview,
    DataQueryRunResult,
    DataQueryRunner,
    DataQueryRunSpec,
)
from app.services.orchestrator_agent.execution.repair_runner import (
    RepairPrepare,
    RepairRunResult,
    RepairRunSpec,
    RepairRunner,
)
from app.services.orchestrator_agent.finalization.final_answer_builder import (
    build_known_final_message,
    build_query_only_final_message,
)
from app.services.orchestrator_agent.finalization.query_data_messages import (
    build_query_data_preview_text,
    build_query_empty_message,
    build_query_too_large_message,
)
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.flows._profile_runtime import (
    ProfileExecutionSpec,
    execute_profile_runtime,
)
from app.services.orchestrator_agent.flows.base import FlowOutput
from app.services.orchestrator_agent.planning.availability_summary import availability_summary
from app.services.orchestrator_agent.planning.plan_builder import (
    apply_clarification_answers,
    build_uid_module_plan,
    group_uid_module_plan,
    required_buckets_for_request,
)
from app.services.orchestrator_agent.planning.query_request_normalizer import normalize_query_request
from app.services.orchestrator_agent.review_rules import review_step_summary
from app.services.orchestrator_agent.runtime.cancellation import cancel_requested
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    replace_trace_steps,
    save_trace,
    set_trace_availability,
    set_trace_review,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import (
    ExecutionTraceRecord,
    NormalizedRequest,
    PlanStep,
    RepairProfileDataInput,
    ReviewResult,
)
from app.services.orchestrator_agent.session import (
    is_run_cancel_requested,
    mark_query_cancelled,
    request_run_cancel,
)


@dataclass(slots=True)
class _QueryDataDecision:
    mode: Literal["unsupported_country", "capability_unavailable", "first_turn_full_query", "legacy"]
    country: str
    capability: Any | None = None


@dataclass(slots=True)
class _QueryOnlyResumePayload:
    enriched_prompt: str
    clarified_request: NormalizedRequest
    country_answer: str
    time_window_answer: str
    clarification_answers: dict[str, Any]


@dataclass(slots=True)
class _QueryProfileResumePayload:
    enriched_prompt: str
    clarified_request: NormalizedRequest
    country_answer: str
    time_window_answer: str
    clarification_answers: dict[str, Any]


@dataclass(slots=True)
class _PreparedClarificationResume:
    enriched_prompt: str
    clarified_request: NormalizedRequest
    country_answer: str
    time_window_answer: str
    clarification_answers: dict[str, Any]


@dataclass(slots=True)
class _QueryPhaseOutcome:
    status: Literal["completed", "cancelled", "failed", "empty", "too_large"]
    output: dict[str, Any] | None = None


@dataclass(slots=True)
class _PostQueryProfileDecision:
    mode: Literal["success", "partial_unavailable", "repair_ready", "blocked_unavailable"]
    availability: Any
    uid_modules_plan: dict[str, list[str]]
    execution_groups: list[tuple[list[str], list[str]]]
    requested_missing: list[str]
    missing_uids_by_bucket: dict[str, list[str]]


_REPAIRABLE_BUCKETS = {"credit", "behavior", "app"}
_QUERY_DATA_REQUIRED_PERMISSIONS = (
    "data:query:view_sql",
    "data:query:execute",
)


class QueryDataThenProfileFlow:
    intent = "query_data_then_profile"

    def _update_trace_metadata(self, trace: ExecutionTraceRecord, **values: Any) -> None:
        update_internal_trace_metadata(
            trace,
            {
                key: value
                for key, value in values.items()
                if value is not None
            },
        )

    def _decide(self, ctx, request: NormalizedRequest) -> _QueryDataDecision:
        if request.intent != self.intent:
            return _QueryDataDecision(mode="legacy", country="")
        country_raw = request.country or ctx.detected_country or ctx.session.country
        country = str(country_raw or "").strip().lower()
        if not country or country == "unknown":
            return _QueryDataDecision(mode="legacy", country=country)
        if country != "mx":
            return _QueryDataDecision(mode="unsupported_country", country=country)
        try:
            capability = ctx.deps.get_data_acquisition_capability()
        except Exception:  # noqa: BLE001
            return _QueryDataDecision(mode="legacy", country=country)
        if not capability.enabled:
            return _QueryDataDecision(
                mode="capability_unavailable",
                country=country,
                capability=capability,
            )
        return _QueryDataDecision(mode="first_turn_full_query", country=country, capability=capability)

    def _build_query_data_review_step(self) -> PlanStep:
        return PlanStep(
            step_id="review_final",
            title="规则审核",
            kind="review",
            user_visible_reason="确认 cohort 范围和后续画像条件。",
        )

    def _build_query_data_step(self) -> PlanStep:
        return PlanStep(
            step_id="query_data",
            title="查询 cohort UID",
            kind="query_data",
            user_visible_reason="先通过 Data Agent 找到符合条件的 UID 集合。",
            tool_name="query_data",
        )

    def _build_check_data_step(self) -> PlanStep:
        return PlanStep(
            step_id="check_data",
            title="检查数据完整性",
            kind="check_data",
            user_visible_reason="直接检查本地 by_uid bucket，不使用 sample fallback。",
        )

    def _build_run_profile_step(self) -> PlanStep:
        return PlanStep(
            step_id="run_profile",
            title="执行画像分析",
            kind="run_profile",
            user_visible_reason="对 query 得到的 cohort 执行 no-repair 画像分析。",
            tool_name="run_profile",
        )

    def _build_repair_step(self, bucket: str) -> PlanStep:
        return PlanStep(
            step_id=f"repair_{bucket}",
            title=f"补齐 {bucket} 数据",
            kind="repair_profile_data",
            user_visible_reason=f"本地缺少 {bucket} bucket，尝试通过 Data Agent 补数。",
            tool_name="repair_profile_data",
        )

    def _build_post_query_plan_steps(
        self,
        trace: ExecutionTraceRecord,
        *,
        clarify_summary: str | None,
        query_count: int,
        check_data_summary: str | None = None,
        repair_bucket: str | None = None,
    ) -> list[PlanStep]:
        query_step = self._build_query_data_step().model_copy(
            update={
                "status": "done",
                "result_summary": f"已获取 {query_count} 个 UID。",
            },
            deep=True,
        )
        check_step = self._build_check_data_step()
        if check_data_summary is not None:
            check_step = check_step.model_copy(
                update={
                    "status": "done",
                    "result_summary": check_data_summary,
                },
                deep=True,
            )
        steps: list[PlanStep] = []
        if clarify_summary is not None:
            steps.append(self._replacement_clarify_step(trace, result_summary=clarify_summary))
        steps.extend([query_step, check_step])
        if repair_bucket is not None:
            steps.append(self._build_repair_step(repair_bucket))
        steps.extend([self._build_run_profile_step(), self._build_query_data_review_step()])
        return steps

    def _replacement_clarify_step(
        self,
        trace: ExecutionTraceRecord,
        *,
        result_summary: str,
    ) -> PlanStep:
        for step in trace.steps:
            if step.step_id != "clarify_scope":
                continue
            return step.model_copy(
                update={"status": "done", "result_summary": result_summary},
                deep=True,
            )
        return PlanStep(
            step_id="clarify_scope",
            title="补充 cohort 查询条件",
            kind="clarification",
            status="done",
            user_visible_reason="当前请求明显是在筛选一批用户，但还缺少国家或时间范围。",
            result_summary=result_summary,
        )

    def _prepare_after_clarification_common(
        self,
        ctx,
        *,
        prompt: str,
        answers: dict[str, Any],
    ) -> _PreparedClarificationResume | None:
        country_answer = str((answers or {}).get("country") or "").strip()
        time_window_answer = str((answers or {}).get("time_window") or "").strip()
        enriched_prompt = apply_clarification_answers(prompt, answers)
        clarified_request = ctx.deps.normalize_request(
            enriched_prompt,
            ctx.session,
            country_answer or ctx.detected_country,
        )
        clarified_request = ctx.deps.refine_normalized_request(
            ctx.client,
            prompt=enriched_prompt,
            session=ctx.session,
            normalized_request=clarified_request,
        )
        if clarified_request.intent == "need_clarification":
            clarified_request = clarified_request.model_copy(
                update={
                    "intent": "query_data_then_profile",
                    "country": country_answer or clarified_request.country or ctx.detected_country,
                    "query_request": enriched_prompt,
                }
            )
            clarified_request.request_understanding = ctx.deps.build_request_understanding(
                prompt=enriched_prompt,
                intent="query_data_then_profile",
                uids=list(clarified_request.uids),
                focus=list(
                    (
                        clarified_request.request_understanding.focus
                        if clarified_request.request_understanding
                        else []
                    )
                    or ["cohort"]
                ),
                trace_days=clarified_request.trace_days,
            )

        if clarified_request.intent != self.intent:
            return None

        country_for_execution = (
            clarified_request.country or ctx.detected_country or ctx.session.country or "mx"
        )
        if country_for_execution != "mx":
            return None

        try:
            capability = ctx.deps.get_data_acquisition_capability()
        except Exception:  # noqa: BLE001
            return None
        if not capability.enabled:
            return None

        return _PreparedClarificationResume(
            enriched_prompt=enriched_prompt,
            clarified_request=clarified_request,
            country_answer=country_answer,
            time_window_answer=time_window_answer,
            clarification_answers=dict(answers or {}),
        )

    def _reset_resume_trace(
        self,
        ctx,
        *,
        trace: ExecutionTraceRecord,
        clarified_request: NormalizedRequest,
        clarify_summary: str,
        steps: list[PlanStep],
    ) -> dict[str, Any]:
        trace.intent = clarified_request.intent
        trace.request_summary = clarified_request.request_summary
        trace.request_understanding = clarified_request.request_understanding
        trace.review = None
        trace.final_status = "running"
        trace.final_message = None
        save_trace(ctx.session, trace)
        replace_trace_steps(
            ctx.session,
            trace,
            [self._replacement_clarify_step(trace, result_summary=clarify_summary), *steps],
        )
        return update_trace_step(
            ctx.session,
            trace,
            step_id="clarify_scope",
            status="done",
            result_summary=clarify_summary,
        )

    def _build_post_query_profile_decision(
        self,
        ctx,
        request: NormalizedRequest,
    ) -> _PostQueryProfileDecision:
        return self._build_post_query_decision(ctx, request, allow_repair=True)

    def _build_post_query_no_repair_decision(
        self,
        ctx,
        request: NormalizedRequest,
    ) -> _PostQueryProfileDecision:
        return self._build_post_query_decision(ctx, request, allow_repair=False)

    def _build_post_query_repair_bridge_decision(
        self,
        ctx,
        request: NormalizedRequest,
    ) -> _PostQueryProfileDecision:
        (
            availability,
            uid_modules_plan,
            execution_groups,
            requested_missing,
            missing_uids_by_bucket,
        ) = self._inspect_post_query_availability(ctx, request)
        if not requested_missing and execution_groups:
            return _PostQueryProfileDecision(
                mode="success",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=[],
                missing_uids_by_bucket=missing_uids_by_bucket,
            )
        if self._can_run_post_query_repair_bridge(
            ctx,
            request,
            requested_missing=requested_missing,
            missing_uids_by_bucket=missing_uids_by_bucket,
            execution_groups=execution_groups,
        ):
            return _PostQueryProfileDecision(
                mode="repair_ready",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=requested_missing,
                missing_uids_by_bucket=missing_uids_by_bucket,
            )
        return _PostQueryProfileDecision(
            mode="blocked_unavailable",
            availability=availability,
            uid_modules_plan=uid_modules_plan,
            execution_groups=execution_groups,
            requested_missing=requested_missing,
            missing_uids_by_bucket=missing_uids_by_bucket,
        )

    def _inspect_post_query_availability(
        self,
        ctx,
        request: NormalizedRequest,
    ) -> tuple[Any, dict[str, list[str]], list[tuple[list[str], list[str]]], list[str], dict[str, list[str]]]:
        country_for_execution = request.country or ctx.detected_country or ctx.session.country or "mx"
        availability = ctx.deps.check_data_availability(request.uids, country=country_for_execution)
        uid_modules_plan = build_uid_module_plan(availability, request)
        execution_groups = [
            (modules, uids)
            for modules, uids in group_uid_module_plan(uid_modules_plan)
            if modules
        ]
        missing_uids_by_bucket = self._missing_uids_by_bucket(availability, request)
        requested_missing = sorted(missing_uids_by_bucket.keys())
        return (
            availability,
            uid_modules_plan,
            execution_groups,
            requested_missing,
            missing_uids_by_bucket,
        )

    def _build_post_query_decision(
        self,
        ctx,
        request: NormalizedRequest,
        *,
        allow_repair: bool,
    ) -> _PostQueryProfileDecision:
        (
            availability,
            uid_modules_plan,
            execution_groups,
            requested_missing,
            missing_uids_by_bucket,
        ) = self._inspect_post_query_availability(ctx, request)
        if not requested_missing and execution_groups:
            return _PostQueryProfileDecision(
                mode="success",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=[],
                missing_uids_by_bucket=missing_uids_by_bucket,
            )
        if requested_missing and execution_groups:
            return _PostQueryProfileDecision(
                mode="repair_ready" if allow_repair else "partial_unavailable",
                availability=availability,
                uid_modules_plan=uid_modules_plan,
                execution_groups=execution_groups,
                requested_missing=requested_missing,
                missing_uids_by_bucket=missing_uids_by_bucket,
            )
        return _PostQueryProfileDecision(
            mode="blocked_unavailable",
            availability=availability,
            uid_modules_plan=uid_modules_plan,
            execution_groups=execution_groups,
            requested_missing=requested_missing,
            missing_uids_by_bucket=missing_uids_by_bucket,
        )

    def _missing_uids_by_bucket(
        self,
        availability,
        request: NormalizedRequest,
    ) -> dict[str, list[str]]:
        missing_uids_by_bucket: dict[str, list[str]] = {}
        required_buckets = required_buckets_for_request(list(request.modules or []))
        for row in availability.per_uid:
            for bucket in row.missing_buckets:
                if bucket in required_buckets:
                    missing_uids_by_bucket.setdefault(bucket, []).append(row.uid)
        return missing_uids_by_bucket

    def _can_run_post_query_repair_bridge(
        self,
        ctx,
        request: NormalizedRequest,
        *,
        requested_missing: list[str],
        missing_uids_by_bucket: dict[str, list[str]],
        execution_groups: list[tuple[list[str], list[str]]],
    ) -> bool:
        if not execution_groups or len(requested_missing) != 1:
            return False
        country_for_execution = request.country or ctx.detected_country or ctx.session.country or "mx"
        if country_for_execution != "mx":
            return False
        bucket = requested_missing[0]
        if bucket not in _REPAIRABLE_BUCKETS:
            return False
        try:
            capability = ctx.deps.get_data_acquisition_capability()
        except Exception:  # noqa: BLE001
            return False
        if capability is None or not getattr(capability, "enabled", False):
            return False
        return bool(missing_uids_by_bucket.get(bucket))

    async def _run_post_query_repair_approved_path(
        self,
        ctx,
        *,
        trace: ExecutionTraceRecord,
        request: NormalizedRequest,
        persist_prompt: str,
        clarify_summary: str,
        post_decision: _PostQueryProfileDecision,
        tools_mod,
    ) -> AsyncIterator[FlowOutput]:
        if post_decision.mode != "repair_ready" or len(post_decision.requested_missing) != 1:
            raise RuntimeError("post-query repair bridge invoked without single-bucket repair_ready")

        bucket = post_decision.requested_missing[0]

        missing_uids = list(post_decision.missing_uids_by_bucket.get(bucket) or [])
        repair_input = RepairProfileDataInput(
            uids=missing_uids,
            country=request.country or ctx.detected_country or ctx.session.country or "mx",
            bucket=bucket,
            reason=f"{bucket} bucket 缺失，需继续执行画像",
        )
        compat_mode = (
            "prepare_then_execute"
            if ctx.deps.repair_profile_data is ctx.deps.original_repair_profile_data
            else "legacy_ack_inside_tool"
        )
        prepare_func = None
        execute_func = None
        legacy_execute_func = None
        legacy_tool_call_id: dict[str, str] | None = None
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
            step_id=f"repair_{bucket}",
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
                step_id=f"repair_{bucket}",
                status="done",
                result_summary=f"已补齐 {bucket} 数据。",
                tool_call_id=tool_call_id,
            )
        elif repair_result.status in {"rejected", "expired"}:
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
        elif repair_result.status == "cancelled":
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
        else:
            error_message = repair_result.error or "repair failed"
            yield update_trace_step(
                ctx.session,
                trace,
                step_id=f"repair_{bucket}",
                status="failed",
                result_summary=error_message,
                tool_call_id=tool_call_id,
            )
            review = ReviewResult(
                status="fail",
                issues=[{"type": "tool_error", "message": error_message}],
                can_answer=False,
                confidence_impact="补数执行失败",
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
                availability=post_decision.availability,
                extra_note="请稍后重试，或先检查补数链路配置。",
            )
            finalize_trace(ctx.session, trace, final_status="error", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=persist_prompt,
                final_message=final_message,
                confidence=0.0,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        post_repair_decision = self._build_post_query_no_repair_decision(ctx, request)
        set_trace_availability(ctx.session, trace, post_repair_decision.availability)
        if (
            post_repair_decision.mode == "partial_unavailable"
            and post_repair_decision.execution_groups
        ):
            async for event in execute_profile_runtime(
                ctx,
                spec=ProfileExecutionSpec(
                    source_request=request,
                    persist_prompt=persist_prompt,
                    trace=trace,
                    availability=post_repair_decision.availability,
                    uid_modules_plan=post_repair_decision.uid_modules_plan,
                    execution_groups=post_repair_decision.execution_groups,
                    requested_missing=list(post_repair_decision.requested_missing or []),
                    decision_mode="partial_unavailable",
                ),
                tools_mod=tools_mod,
            ):
                yield event
            return

        if post_repair_decision.mode != "success" or not post_repair_decision.execution_groups:
            blocked_reason = "repair 完成后仍未达到可执行成功路径。"
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="run_profile",
                status="blocked",
                result_summary=blocked_reason,
            )
            review = ReviewResult(
                status="fail",
                issues=[{"type": "blocked_unavailable", "message": blocked_reason}],
                can_answer=False,
                confidence_impact="补数后仍无法进入稳定画像路径",
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
                availability=post_repair_decision.availability,
                review=review,
                extra_note="请检查补数结果与 bucket 完整性后重试。",
            )
            finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=persist_prompt,
                final_message=final_message,
                confidence=0.0,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        async for event in execute_profile_runtime(
            ctx,
            spec=ProfileExecutionSpec(
                source_request=request,
                persist_prompt=persist_prompt,
                trace=trace,
                availability=post_repair_decision.availability,
                uid_modules_plan=post_repair_decision.uid_modules_plan,
                execution_groups=post_repair_decision.execution_groups,
                requested_missing=[],
                decision_mode="success",
            ),
            tools_mod=tools_mod,
        ):
            yield event

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        return self._decide(ctx, request).mode in {
            "unsupported_country",
            "capability_unavailable",
            "first_turn_full_query",
        }

    def prepare_query_only_after_clarification(
        self,
        ctx,
        *,
        prompt: str,
        answers: dict[str, Any],
    ) -> _QueryOnlyResumePayload | None:
        if (answers or {}).get("auto_profile") is not False:
            return None
        prepared = self._prepare_after_clarification_common(
            ctx,
            prompt=prompt,
            answers=answers,
        )
        if prepared is None:
            return None
        return _QueryOnlyResumePayload(
            enriched_prompt=prepared.enriched_prompt,
            clarified_request=prepared.clarified_request,
            country_answer=prepared.country_answer,
            time_window_answer=prepared.time_window_answer,
            clarification_answers=prepared.clarification_answers,
        )

    def prepare_profile_after_clarification(
        self,
        ctx,
        *,
        prompt: str,
        answers: dict[str, Any],
    ) -> _QueryProfileResumePayload | None:
        if (answers or {}).get("auto_profile") is not True:
            return None
        prepared = self._prepare_after_clarification_common(
            ctx,
            prompt=prompt,
            answers=answers,
        )
        if prepared is None:
            return None
        return _QueryProfileResumePayload(
            enriched_prompt=prepared.enriched_prompt,
            clarified_request=prepared.clarified_request,
            country_answer=prepared.country_answer,
            time_window_answer=prepared.time_window_answer,
            clarification_answers=prepared.clarification_answers,
        )

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[FlowOutput]:
        decision = self._decide(ctx, request)
        if decision.mode == "legacy":
            raise RuntimeError("QueryDataThenProfileFlow run invoked for legacy path")
        if decision.mode == "first_turn_full_query":
            async for event in self._run_first_turn_full_query(ctx, request):
                yield event
            return

        trace = create_execution_trace(
            ctx.session,
            execution_id=uuid.uuid4().hex,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            prompt=ctx.prompt,
            normalized_request=request,
            availability=None,
            steps=[self._build_query_data_step(), self._build_query_data_review_step()],
        )
        self._update_trace_metadata(
            trace,
            flow_name="QueryDataThenProfileFlow",
            flow_mode="guard_unsupported_country" if decision.mode == "unsupported_country" else "guard_capability_unavailable",
            country=decision.country or None,
            terminal_reason="unsupported_country" if decision.mode == "unsupported_country" else "data_acquisition_unavailable",
        )
        yield build_execution_plan_event(trace)

        if decision.mode == "unsupported_country":
            blocked_reason = "query_data_then_profile 目前仅支持 mx。"
            review = ReviewResult(
                status="fail",
                issues=[{"type": "unsupported_country", "message": blocked_reason}],
                can_answer=False,
                confidence_impact="非 mx Data Agent 闭环尚未支持，已阻断执行",
            )
            extra_note = "当前补数/取数闭环只支持 mx，请切换到 mx 或改为已有画像上的只读追问。"
        else:
            blocked_reason = data_acquisition_unavailable_message(decision.capability)
            review = ReviewResult(
                status="fail",
                issues=[{"type": "data_acquisition_unavailable", "message": blocked_reason}],
                can_answer=False,
                confidence_impact="数据获取能力当前不可用，已阻断 cohort 自动执行",
            )
            extra_note = blocked_reason

        yield update_trace_step(
            ctx.session,
            trace,
            step_id="query_data",
            status="blocked",
            result_summary=blocked_reason,
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
            extra_note=extra_note,
        )
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

    async def _run_first_turn_full_query(
        self,
        ctx,
        request: NormalizedRequest,
    ) -> AsyncIterator[FlowOutput]:
        from app.services.orchestrator_agent import tools as tools_mod

        trace = create_execution_trace(
            ctx.session,
            execution_id=uuid.uuid4().hex,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            prompt=ctx.prompt,
            normalized_request=request,
            availability=None,
            steps=[
                self._build_query_data_step(),
                self._build_check_data_step(),
                self._build_run_profile_step(),
                self._build_query_data_review_step(),
            ],
        )
        self._update_trace_metadata(
            trace,
            flow_name="QueryDataThenProfileFlow",
            flow_mode="query_profile",
            auto_profile=True,
            country=request.country or ctx.detected_country or ctx.session.country or "mx",
        )
        yield build_execution_plan_event(trace)

        outcome: _QueryPhaseOutcome | None = None
        async for item in self._run_query_data_phase(
            ctx,
            trace=trace,
            request=request,
            persist_prompt=ctx.prompt,
            failed_extra_note="请调整取数条件或重新发起会话。",
            clarification_answers=None,
            default_query_mode="query_profile",
            default_auto_profile=True,
        ):
            if isinstance(item, _QueryPhaseOutcome):
                outcome = item
            else:
                yield item

        if outcome is None or outcome.status in {"cancelled", "failed"}:
            return

        async for event in self._continue_auto_profile_after_query_output(
            ctx,
            trace=trace,
            request=request,
            persist_prompt=ctx.prompt,
            outcome=outcome,
            clarify_summary=None,
            tools_mod=tools_mod,
        ):
            yield event

    async def _continue_auto_profile_after_query_output(
        self,
        ctx,
        *,
        trace: ExecutionTraceRecord,
        request: NormalizedRequest,
        persist_prompt: str,
        outcome: _QueryPhaseOutcome,
        clarify_summary: str | None,
        tools_mod,
    ) -> AsyncIterator[FlowOutput]:
        output = outcome.output or {}
        if outcome.status == "empty":
            self._update_trace_metadata(trace, terminal_reason="cohort_empty")
            review = ReviewResult(
                status="fail",
                issues=[{"type": "empty_cohort", "message": "cohort 没有匹配到可画像 UID"}],
                can_answer=False,
                confidence_impact="没有可用于自动画像的 UID，已阻断执行",
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
                extra_note=build_query_empty_message(query_mode="query_profile"),
            )
            finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=persist_prompt,
                final_message=final_message,
                confidence=0.0,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        if outcome.status == "too_large":
            self._update_trace_metadata(trace, terminal_reason="cohort_too_large")
            review = ReviewResult(
                status="fail",
                issues=[{"type": "cohort_too_large", "message": "cohort 返回 UID 数量超过 200"}],
                can_answer=False,
                confidence_impact="范围过大，已阻断自动画像",
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
                extra_note=build_query_too_large_message(
                    query_mode="query_profile",
                    cohort_size=len(list(output.get("uids") or [])) or None,
                    limit=200,
                ),
            )
            finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=persist_prompt,
                final_message=final_message,
                confidence=0.0,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        resolved_request = request.model_copy(update={"uids": list(output.get("uids") or [])})
        post_decision = self._build_post_query_repair_bridge_decision(ctx, resolved_request)
        set_trace_availability(ctx.session, trace, post_decision.availability)
        check_data_summary = availability_summary(post_decision.availability)

        if post_decision.mode == "repair_ready":
            self._update_trace_metadata(trace, flow_mode="query_repair")
            replace_trace_steps(
                ctx.session,
                trace,
                self._build_post_query_plan_steps(
                    trace,
                    clarify_summary=clarify_summary,
                    query_count=len(resolved_request.uids),
                    repair_bucket=post_decision.requested_missing[0],
                ),
            )
        else:
            replace_trace_steps(
                ctx.session,
                trace,
                self._build_post_query_plan_steps(
                    trace,
                    clarify_summary=clarify_summary,
                    query_count=len(resolved_request.uids),
                ),
            )
            yield build_execution_plan_event(trace)

        yield update_trace_step(
            ctx.session,
            trace,
            step_id="check_data",
            status="done",
            result_summary=check_data_summary,
        )

        if post_decision.mode == "repair_ready":
            replace_trace_steps(
                ctx.session,
                trace,
                self._build_post_query_plan_steps(
                    trace,
                    clarify_summary=clarify_summary,
                    query_count=len(resolved_request.uids),
                    check_data_summary=check_data_summary,
                    repair_bucket=post_decision.requested_missing[0],
                ),
            )
            yield build_execution_plan_event(trace)
            async for event in self._run_post_query_repair_approved_path(
                ctx,
                trace=trace,
                request=resolved_request,
                persist_prompt=persist_prompt,
                clarify_summary=clarify_summary or "",
                post_decision=post_decision,
                tools_mod=tools_mod,
            ):
                yield event
            return

        if post_decision.mode == "blocked_unavailable" or not post_decision.execution_groups:
            self._update_trace_metadata(trace, terminal_reason="blocked_unavailable")
            blocked_reason = "query 结果当前没有可直接执行的画像模块。"
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="run_profile",
                status="blocked",
                result_summary=blocked_reason,
            )
            review = ReviewResult(
                status="fail",
                issues=[{"type": "blocked_unavailable", "message": blocked_reason}],
                can_answer=False,
                confidence_impact="query_data 后的画像条件当前不满足，已阻断自动画像",
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
                resolved_request,
                availability=post_decision.availability,
                review=review,
                extra_note="请缩小筛选条件、改为 query-only，或等待后续 repair 分支接管后重试。",
            )
            finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=persist_prompt,
                final_message=final_message,
                confidence=0.0,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        decision_mode: Literal["success", "partial_unavailable"] = (
            "partial_unavailable" if post_decision.mode == "partial_unavailable" else "success"
        )
        requested_missing = (
            list(post_decision.requested_missing or [])
            if decision_mode == "partial_unavailable"
            else []
        )
        async for event in execute_profile_runtime(
            ctx,
            spec=ProfileExecutionSpec(
                source_request=resolved_request,
                persist_prompt=persist_prompt,
                trace=trace,
                availability=post_decision.availability,
                uid_modules_plan=post_decision.uid_modules_plan,
                execution_groups=post_decision.execution_groups,
                requested_missing=requested_missing,
                decision_mode=decision_mode,
            ),
            tools_mod=tools_mod,
        ):
            yield event

    async def _run_query_data_phase(
        self,
        ctx,
        *,
        trace: ExecutionTraceRecord,
        request: NormalizedRequest,
        persist_prompt: str,
        failed_extra_note: str,
        clarification_answers: dict[str, Any] | None,
        default_query_mode: Literal["query_only", "query_profile", "unknown"],
        default_auto_profile: bool | None,
    ) -> AsyncIterator[FlowOutput | _QueryPhaseOutcome]:
        data_query_runner = DataQueryRunner(
            session=ctx.session,
            lifecycle=ctx.lifecycle,
            events=ctx.events,
            human_input=ctx.human_input,
        )
        request_text = request.query_request or persist_prompt
        normalized_query = normalize_query_request(
            request_text=request_text,
            country_hint=request.country or ctx.detected_country or ctx.session.country,
            request_understanding=request.request_understanding,
            clarification_answers=clarification_answers,
            default_query_mode=default_query_mode,
            default_auto_profile=default_auto_profile,
        )
        country_for_execution = request.country or ctx.detected_country or ctx.session.country or normalized_query.country or "mx"
        if ctx.user_context is not None:
            self._update_trace_metadata(trace, approved_by=ctx.user_context.username)
            try:
                require_permissions(ctx.user_context, _QUERY_DATA_REQUIRED_PERMISSIONS)
            except PermissionError as exc:
                record_runtime_audit_event(
                    user=ctx.user_context,
                    request_context=ctx.request_context,
                    event_type="data.query.preview",
                    action="preview",
                    status="denied",
                    resource_type="tool",
                    resource_id="query_data",
                    metadata={
                        "country": country_for_execution,
                        "required_permissions": list(_QUERY_DATA_REQUIRED_PERMISSIONS),
                    },
                )
                raise
        tool_call_id: str | None = None
        ack_requested = False

        try:
            async def _preview_query() -> DataQueryPreview:
                nonlocal ack_requested
                preview_maybe = ctx.deps.execute_query_data_cohort(
                    ctx.session,
                    normalized_query.effective_request_text,
                    country_for_execution,
                )
                preview = await preview_maybe if inspect.isawaitable(preview_maybe) else preview_maybe
                if "uids" in preview and "child" not in preview:
                    return DataQueryPreview(status="completed", output=preview)
                ack_requested = True
                raw_sql_text = str(preview.get("sql_text") or "")
                display_sql_text = build_query_data_preview_text(
                    query_mode=normalized_query.query_mode,
                    country=normalized_query.country,
                    time_window_label=normalized_query.time_window_label,
                    filters_summary=normalized_query.filters_summary,
                    raw_sql=raw_sql_text,
                    rows_estimated=preview.get("rows_estimated"),
                )
                return DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "sql_text": display_sql_text,
                        "rows_estimated": preview["rows_estimated"],
                    },
                    raw_preview=preview,
                )

            async def _complete_query(preview: DataQueryPreview) -> dict[str, Any]:
                raw_preview = dict(preview.raw_preview or {})
                output_maybe = ctx.deps.complete_query_data_cohort(
                    ctx.session,
                    raw_preview["child"],
                    raw_preview["sql_text"],
                )
                return await output_maybe if inspect.isawaitable(output_maybe) else output_maybe

            handle = await data_query_runner.start(
                DataQueryRunSpec(
                    trace_id=trace.trace_id or trace.execution_id,
                    input_payload={
                        "request": request_text,
                        "country": country_for_execution,
                    },
                    preview_func=_preview_query,
                    complete_func=_complete_query,
                    should_cancel=(
                        (lambda current_run_id=ctx.run_id: bool(current_run_id) and is_run_cancel_requested(ctx.session.session_id, current_run_id))
                        if ctx.run_id
                        else None
                    ),
                )
            )
            tool_call_id = handle.record.tool_call_id
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="query_data",
                status="running",
                tool_call_id=tool_call_id,
            )
            if handle.started_event is not None:
                yield handle.started_event

            result: DataQueryRunResult | None = None
            async for item in handle.stream():
                if item.event is not None:
                    yield item.event
                if item.result is not None:
                    result = item.result

            if result is None:
                raise RuntimeError("query_data runner completed without result")

            if result.status in {"rejected", "expired"}:
                self._update_trace_metadata(
                    trace,
                    ack_result=result.status,
                    terminal_reason="ack_rejected" if result.status == "rejected" else "ack_expired",
                )
                if result.status == "rejected":
                    mark_query_cancelled(ctx.session.session_id)
                request_run_cancel(ctx.session.session_id, ctx.run_id)
                cancel_events = cancel_requested(
                    ctx.session,
                    turn_id=ctx.turn_id,
                    run_id=ctx.run_id,
                    trace=trace,
                ) or []
                for cancelled_evt in cancel_events:
                    yield cancelled_evt
                yield _QueryPhaseOutcome(status="cancelled")
                return

            if result.status == "cancelled":
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
                for cancelled_evt in cancel_events:
                    yield cancelled_evt
                yield _QueryPhaseOutcome(status="cancelled")
                return

            if result.status == "failed":
                raise RuntimeError(result.error or "query_data failed")

            output = result.output or {}
            cancel_events = cancel_requested(
                ctx.session,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
                trace=trace,
            ) or []
            if cancel_events:
                for cancelled_evt in cancel_events:
                    yield cancelled_evt
                yield _QueryPhaseOutcome(status="cancelled")
                return

            uids = list(output.get("uids") or [])
            self._update_trace_metadata(
                trace,
                cohort_size=len(uids),
                ack_result="approved" if ack_requested else None,
            )
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="query_data",
                status="done",
                result_summary=f"已获取 {len(uids)} 个 UID。",
                tool_call_id=tool_call_id,
            )
            if not uids:
                yield _QueryPhaseOutcome(status="empty", output=output)
                return
            if len(uids) > 200:
                yield _QueryPhaseOutcome(status="too_large", output=output)
                return
            yield _QueryPhaseOutcome(status="completed", output=output)
            return
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            self._update_trace_metadata(trace, terminal_reason="tool_error")
            yield update_trace_step(
                ctx.session,
                trace,
                step_id="query_data",
                status="failed",
                result_summary=error_message,
                tool_call_id=tool_call_id,
            )
            review = ReviewResult(
                status="fail",
                issues=[{"type": "tool_error", "message": error_message}],
                can_answer=False,
                confidence_impact="取数阶段失败",
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
                extra_note=failed_extra_note,
            )
            finalize_trace(
                ctx.session,
                trace,
                final_status="error",
                final_message=final_message,
            )
            yield persist_final_message(
                ctx.session,
                prompt=persist_prompt,
                final_message=final_message,
                confidence=0.0,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            yield _QueryPhaseOutcome(status="failed")

    async def run_query_only_after_clarification(
        self,
        ctx,
        *,
        prepared: _QueryOnlyResumePayload,
        trace: ExecutionTraceRecord,
    ) -> AsyncIterator[FlowOutput]:
        clarified_request = prepared.clarified_request
        clarify_summary = f"已补充国家={prepared.country_answer}，时间范围={prepared.time_window_answer}。"
        yield self._reset_resume_trace(
            ctx,
            trace=trace,
            clarified_request=clarified_request,
            clarify_summary=clarify_summary,
            steps=[
                self._build_query_data_step(),
                self._build_query_data_review_step(),
            ],
        )
        self._update_trace_metadata(
            trace,
            flow_name="QueryDataThenProfileFlow",
            flow_mode="query_only",
            auto_profile=False,
            country=clarified_request.country or ctx.detected_country or ctx.session.country or "mx",
            clarification_resume=True,
        )
        yield build_execution_plan_event(trace)

        outcome: _QueryPhaseOutcome | None = None
        async for item in self._run_query_data_phase(
            ctx,
            trace=trace,
            request=clarified_request,
            persist_prompt=prepared.enriched_prompt,
            failed_extra_note="请调整取数条件或重新发起会话。",
            clarification_answers=prepared.clarification_answers,
            default_query_mode="query_only",
            default_auto_profile=False,
        ):
            if isinstance(item, _QueryPhaseOutcome):
                outcome = item
            else:
                yield item

        if outcome is None or outcome.status in {"cancelled", "failed"}:
            return

        output = outcome.output or {}
        if outcome.status == "too_large":
            self._update_trace_metadata(trace, terminal_reason="cohort_too_large")
            review = ReviewResult(
                status="fail",
                issues=[{"type": "cohort_too_large", "message": "cohort 返回 UID 数量超过 200"}],
                can_answer=False,
                confidence_impact="范围过大，已阻断自动画像",
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
                clarified_request,
                review=review,
                extra_note=build_query_too_large_message(
                    query_mode="query_only",
                    cohort_size=len(list(output.get("uids") or [])) or None,
                    limit=200,
                ),
            )
            finalize_trace(ctx.session, trace, final_status="blocked", final_message=final_message)
            yield persist_final_message(
                ctx.session,
                prompt=prepared.enriched_prompt,
                final_message=final_message,
                confidence=0.0,
                detected_country=ctx.detected_country,
                turn_id=ctx.turn_id,
                run_id=ctx.run_id,
            )
            return

        review = ReviewResult(status="pass", issues=[], can_answer=True, confidence_impact=None)
        if not list(output.get("uids") or []):
            self._update_trace_metadata(trace, terminal_reason="cohort_empty")
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="review_final",
            status="done",
            result_summary="已按用户要求仅返回 cohort 查询结果，不继续自动画像。",
        )
        yield set_trace_review(ctx.session, trace, review)
        final_message = build_query_only_final_message(
            clarified_request,
            output=output,
        )
        finalize_trace(
            ctx.session,
            trace,
            final_status="completed",
            final_message=final_message,
        )
        yield persist_final_message(
            ctx.session,
            prompt=prepared.enriched_prompt,
            final_message=final_message,
            confidence=0.85,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )

    async def run_profile_after_query_clarification(
        self,
        ctx,
        *,
        prepared: _QueryProfileResumePayload,
        trace: ExecutionTraceRecord,
    ) -> AsyncIterator[FlowOutput]:
        from app.services.orchestrator_agent import tools as tools_mod

        clarified_request = prepared.clarified_request
        clarify_summary = f"已补充国家={prepared.country_answer}，时间范围={prepared.time_window_answer}。"
        yield self._reset_resume_trace(
            ctx,
            trace=trace,
            clarified_request=clarified_request,
            clarify_summary=clarify_summary,
            steps=[
                self._build_query_data_step(),
                self._build_query_data_review_step(),
            ],
        )
        self._update_trace_metadata(
            trace,
            flow_name="QueryDataThenProfileFlow",
            flow_mode="query_profile",
            auto_profile=True,
            country=clarified_request.country or ctx.detected_country or ctx.session.country or "mx",
            clarification_resume=True,
        )

        outcome: _QueryPhaseOutcome | None = None
        async for item in self._run_query_data_phase(
            ctx,
            trace=trace,
            request=clarified_request,
            persist_prompt=prepared.enriched_prompt,
            failed_extra_note="请调整取数条件或重新发起会话。",
            clarification_answers=prepared.clarification_answers,
            default_query_mode="query_profile",
            default_auto_profile=True,
        ):
            if isinstance(item, _QueryPhaseOutcome):
                outcome = item
            else:
                yield item

        if outcome is None or outcome.status in {"cancelled", "failed"}:
            return

        async for event in self._continue_auto_profile_after_query_output(
            ctx,
            trace=trace,
            request=clarified_request,
            persist_prompt=prepared.enriched_prompt,
            outcome=outcome,
            clarify_summary=clarify_summary,
            tools_mod=tools_mod,
        ):
            yield event
