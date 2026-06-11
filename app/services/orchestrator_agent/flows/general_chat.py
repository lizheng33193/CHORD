"""Migrated general chat flow with conservative single-tool ownership."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import uuid
from typing import Any, AsyncIterator

from app.services.orchestrator_agent.budget import BudgetExceeded, check_and_increment
from app.services.orchestrator_agent.context_fit import MODEL_MAX_TOKENS_PER_TURN, ensure_context_fits
from app.services.orchestrator_agent.execution.data_query_runner import (
    DataQueryPreview,
    DataQueryRunner,
    DataQueryRunResult,
    DataQueryRunSpec,
)
from app.services.orchestrator_agent.execution.profile_runner import (
    ProfileRunner,
    ProfileRunResult,
    ProfileRunSpec,
    call_tool_with_optional_progress,
    log_run_profile_progress,
)
from app.services.orchestrator_agent.execution.tool_runner import ToolRunSpec
from app.services.orchestrator_agent.finalization.message_persistence import persist_final_message
from app.services.orchestrator_agent.finalization.query_data_messages import (
    build_query_data_observation_message,
    build_query_data_preview_text,
)
from app.services.orchestrator_agent.flows.base import FlowOutput
from app.services.orchestrator_agent.planning.query_request_normalizer import normalize_query_request
from app.services.orchestrator_agent.runtime.cancellation import cancel_requested
from app.services.orchestrator_agent.runtime.llm_input import build_llm_input
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.runtime.trace_store import (
    build_execution_plan_event,
    create_execution_trace,
    finalize_trace,
    update_trace_step,
)
from app.services.orchestrator_agent.schemas import (
    MemoryReadInput,
    MemoryWriteInput,
    NormalizedRequest,
    PlanStep,
    QueryDataInput,
    RunProfileInput,
    RunTraceInput,
)
from app.services.orchestrator_agent.session import is_run_cancel_requested, mark_query_cancelled, request_run_cancel


_MEMORY_WRITE_INTENT_RE = re.compile(
    r"(请记住|记住这点|记住|记下来|保存到记忆|写入记忆|save memory|remember this|remember that)",
    re.IGNORECASE,
)
_MEMORY_READ_INTENT_RE = re.compile(
    r"(你还记得|还记得吗|查记忆|读取记忆|回忆一下|之前说过什么|recall|read memory|what do you remember)",
    re.IGNORECASE,
)
_TRACE_TOOL_INTENT_RE = re.compile(
    r"(run\s*trace|trace|行为轨迹|操作路径|时间线|timeline|轨迹|路径)",
    re.IGNORECASE,
)
_PROFILE_TOOL_INTENT_RE = re.compile(r"(画像|profile|run_profile|用户分析|分析这个用户|执行画像)")
_QUERY_TOOL_INTENT_RE = re.compile(r"(查询|筛选|找出|拉取|获取|分群|cohort|query_data|高风险用户|用户列表)")


class GeneralChatFlow:
    intent = "general_chat"

    async def can_handle(self, ctx, request: NormalizedRequest) -> bool:
        return self._mode(ctx, request) is not None

    def _mode(self, ctx, request: NormalizedRequest) -> str | None:
        if request.intent != self.intent:
            return None
        if request.uids or request.uid_file_path or request.query_request:
            return None

        families = self._detect_tool_families(ctx, request)
        if len(families) > 1:
            return None
        if "memory" in families:
            return "memory_tool_loop"
        if "trace" in families:
            return "run_trace_tool_loop"
        if "query" in families:
            return "query_data_tool_loop"
        if "profile" in families:
            return "run_profile_tool_loop"

        understanding = request.request_understanding
        if understanding is None:
            return None
        if understanding.answer_mode != "general_chat":
            return None
        if understanding.requires_tools is not False:
            return None
        return "no_tool"

    async def run(self, ctx, request: NormalizedRequest) -> AsyncIterator[FlowOutput]:
        mode = self._mode(ctx, request)
        if mode is None:
            return

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
                "flow_mode": mode,
            },
        )
        yield build_execution_plan_event(trace)

        decision = None
        async for evt in self._generate_decision(ctx, trace, session_status_on_budget="budget_exceeded"):
            if evt.get("_decision") is not None:
                decision = evt["_decision"]
                continue
            yield evt
        if decision is None:
            return

        final_message = decision.get("final_message")
        if mode == "memory_tool_loop" and isinstance(final_message, str) and final_message.strip():
            async for evt in self._fail(
                ctx,
                trace,
                "GeneralChatFlow 6C requires a memory tool_call before finalizing memory prompts",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return
        if isinstance(final_message, str) and final_message.strip():
            async for evt in self._complete(ctx, trace, final_message, confidence=decision.get("confidence") or 0.0):
                yield evt
            return

        if mode == "memory_tool_loop":
            async for evt in self._run_memory_tool_loop(ctx, trace, request, decision):
                yield evt
            return
        if mode == "run_trace_tool_loop":
            async for evt in self._run_trace_tool_loop(ctx, trace, decision):
                yield evt
            return
        if mode == "query_data_tool_loop":
            async for evt in self._run_query_data_tool_loop(ctx, trace, decision):
                yield evt
            return
        if mode == "run_profile_tool_loop":
            async for evt in self._run_profile_tool_loop(ctx, trace, decision):
                yield evt
            return

        reason = "No-tool general chat returned an unsupported tool_call" if decision.get("tool_call") else "LLM did not produce a final_message"
        async for evt in self._fail(
            ctx,
            trace,
            reason,
            session_status="error",
            terminal_reason="unsupported_tool" if decision.get("tool_call") else "continuation_missing_final",
        ):
            yield evt

    @staticmethod
    def _structured_result(llm_out: Any) -> dict[str, Any]:
        if not isinstance(llm_out, dict):
            return {}
        result = llm_out.get("structured_result")
        return result if isinstance(result, dict) else {}

    async def _generate_decision(
        self,
        ctx,
        trace,
        *,
        session_status_on_budget: str,
    ) -> AsyncIterator[dict[str, Any]]:
        llm_input = build_llm_input(ctx.system_prompt or "", ctx.session.messages)
        try:
            llm_out = await asyncio.to_thread(
                ctx.client.generate_structured,
                skill_name="orchestrator_agent",
                prompt=llm_input,
                fallback_result={
                    "final_message": "AI 服务暂时不可用，请稍后重试",
                    "tool_call": None,
                    "confidence": 0.0,
                },
                route_key="orchestrator_agent.decide",
            )
        except Exception as exc:  # noqa: BLE001
            async for evt in self._fail(ctx, trace, str(exc), session_status="error", terminal_reason="llm_error"):
                yield evt
            return

        try:
            usage = getattr(ctx.client, "last_token_usage", {}) or {}
            budget = check_and_increment(ctx.session, int(usage.get("total", 0)))
        except BudgetExceeded as exc:
            async for evt in self._fail(
                ctx,
                trace,
                str(exc),
                session_status=session_status_on_budget,
                terminal_reason="budget_exceeded",
            ):
                yield evt
            return
        if budget["warn"]:
            yield {"type": "budget_warning", **budget}
        yield {"_decision": self._structured_result(llm_out)}

    @staticmethod
    def _text_for_gate(ctx, request: NormalizedRequest) -> str:
        understanding = request.request_understanding
        parts = [ctx.prompt, request.request_summary]
        if understanding is not None:
            parts.extend([
                understanding.route_label,
                understanding.rewritten_goal,
                " ".join(understanding.focus or []),
            ])
        return "\n".join(str(part or "") for part in parts)

    def _looks_like_trace_tool_prompt(self, ctx, request: NormalizedRequest) -> bool:
        return bool(_TRACE_TOOL_INTENT_RE.search(self._text_for_gate(ctx, request)))

    def _looks_like_profile_tool_prompt(self, ctx, request: NormalizedRequest) -> bool:
        return bool(_PROFILE_TOOL_INTENT_RE.search(self._text_for_gate(ctx, request)))

    def _looks_like_query_tool_prompt(self, ctx, request: NormalizedRequest) -> bool:
        return bool(_QUERY_TOOL_INTENT_RE.search(self._text_for_gate(ctx, request)))

    def _detect_memory_intent_kind(self, ctx, request: NormalizedRequest) -> str | None:
        text = self._text_for_gate(ctx, request)
        if _MEMORY_READ_INTENT_RE.search(text):
            return "read"
        if _MEMORY_WRITE_INTENT_RE.search(text):
            return "write"
        return None

    def _detect_tool_families(self, ctx, request: NormalizedRequest) -> set[str]:
        families: set[str] = set()
        if self._detect_memory_intent_kind(ctx, request) is not None:
            families.add("memory")
        if self._looks_like_trace_tool_prompt(ctx, request):
            families.add("trace")
        if self._looks_like_query_tool_prompt(ctx, request):
            families.add("query")
        if self._looks_like_profile_tool_prompt(ctx, request):
            families.add("profile")
        return families

    async def _complete(
        self,
        ctx,
        trace,
        final_message: str,
        *,
        confidence: float,
    ) -> AsyncIterator[FlowOutput]:
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="general_answer",
            status="done",
            result_summary="已按通用 Agent 模式完成回答。",
        )
        finalize_trace(ctx.session, trace, final_status="completed", final_message=final_message)
        final_evt = persist_final_message(
            ctx.session,
            prompt=ctx.prompt,
            final_message=final_message,
            confidence=confidence,
            detected_country=ctx.detected_country,
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
        )
        yield {"type": "run_completed", "trace_id": trace.trace_id or trace.execution_id}
        yield final_evt

    async def _run_memory_tool_loop(
        self,
        ctx,
        trace,
        request: NormalizedRequest,
        decision: dict[str, Any],
    ) -> AsyncIterator[FlowOutput]:
        tool_call = decision.get("tool_call")
        if not isinstance(tool_call, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "LLM did not produce a memory tool_call",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return

        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "memory tool_call arguments must be an object",
                session_status="error",
                terminal_reason="invalid_tool_arguments",
            ):
                yield evt
            return

        intent_kind = self._detect_memory_intent_kind(ctx, request)
        allowed_names = {"memory_write", "memory_read"}
        if intent_kind == "write":
            allowed_names = {"memory_write"}
        elif intent_kind == "read":
            allowed_names = {"memory_read"}

        tool_name = tool_call.get("name")
        if tool_name not in allowed_names:
            async for evt in self._fail(
                ctx,
                trace,
                f"GeneralChatFlow 6C does not support memory tool_call {tool_name!r} for this prompt",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return
        update_internal_trace_metadata(
            trace,
            {
                "tool_name": str(tool_name),
                "memory_operation": "write" if tool_name == "memory_write" else "read",
            },
        )

        if tool_name == "memory_write":
            try:
                input_obj = MemoryWriteInput(**arguments)
            except Exception as exc:  # noqa: BLE001
                async for evt in self._fail(ctx, trace, str(exc), session_status="error", terminal_reason="invalid_tool_arguments"):
                    yield evt
                return
            tool_fn = ctx.memory.write if ctx.memory is not None else None
        else:
            try:
                input_obj = MemoryReadInput(**arguments)
            except Exception as exc:  # noqa: BLE001
                async for evt in self._fail(ctx, trace, str(exc), session_status="error", terminal_reason="invalid_tool_arguments"):
                    yield evt
                return
            tool_fn = ctx.memory.read if ctx.memory is not None else None

        if tool_fn is None:
            async for evt in self._fail(
                ctx,
                trace,
                f"{tool_name} tool is unavailable",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return

        handle = await ctx.tools.start(
            ToolRunSpec(
                name=tool_name,
                func=tool_fn,
                input_payload=input_obj.model_dump(mode="json"),
                call_args=(input_obj,),
                trace_id=trace.trace_id or trace.execution_id,
            )
        )
        tool_call_id = handle.record.tool_call_id
        if handle.started_event is not None:
            yield handle.started_event
        result = await handle.execute()
        if result.completed_event is not None:
            yield result.completed_event
        if result.status != "completed":
            async for evt in self._fail(
                ctx,
                trace,
                result.error or f"{tool_name} failed",
                session_status="error",
                terminal_reason="tool_error",
            ):
                yield evt
            return

        if tool_name == "memory_write":
            output = result.output if isinstance(result.output, dict) else {}
            if output.get("ok") is not True:
                async for evt in self._fail(
                    ctx,
                    trace,
                    "memory_write reported ok=False",
                    session_status="error",
                    terminal_reason="tool_error",
                ):
                    yield evt
                return
            async for evt in self._complete(ctx, trace, "已记住。", confidence=0.95):
                yield evt
            return

        async for evt in self._continue_after_tool_observation(
            ctx,
            trace,
            tool_call_id=tool_call_id,
            output=result.output if isinstance(result.output, dict) else {"items": []},
            missing_final_reason="LLM did not produce a final_message after memory_read",
            second_tool_reason="GeneralChatFlow 6C does not support a second tool_call",
        ):
            yield evt

    async def _run_trace_tool_loop(
        self,
        ctx,
        trace,
        decision: dict[str, Any],
    ) -> AsyncIterator[FlowOutput]:
        tool_call = decision.get("tool_call")
        if not isinstance(tool_call, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "LLM did not produce final or run_trace tool_call",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return
        if tool_call.get("name") != "run_trace":
            async for evt in self._fail(
                ctx,
                trace,
                "GeneralChatFlow 6B-1 only supports run_trace tool_call",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return

        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "run_trace tool_call arguments must be an object",
                session_status="error",
                terminal_reason="invalid_tool_arguments",
            ):
                yield evt
            return
        try:
            input_obj = RunTraceInput(**arguments)
        except Exception as exc:  # noqa: BLE001
            async for evt in self._fail(ctx, trace, str(exc), session_status="error", terminal_reason="invalid_tool_arguments"):
                yield evt
            return
        update_internal_trace_metadata(trace, {"tool_name": "run_trace"})

        from app.services.orchestrator_agent import tools as tools_mod

        registry = tools_mod.get_tool_registry()
        tool_fn = registry.get("run_trace")
        if tool_fn is None:
            async for evt in self._fail(
                ctx,
                trace,
                "run_trace tool is unavailable",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return

        handle = await ctx.tools.start(
            ToolRunSpec(
                name="run_trace",
                func=tool_fn,
                input_payload=input_obj.model_dump(mode="json"),
                call_args=(input_obj,),
                trace_id=trace.trace_id or trace.execution_id,
            )
        )
        tool_call_id = handle.record.tool_call_id
        if handle.started_event is not None:
            yield handle.started_event
        result = await handle.execute()
        if result.completed_event is not None:
            yield result.completed_event
        if result.status != "completed":
            async for evt in self._fail(
                ctx,
                trace,
                result.error or "run_trace failed",
                session_status="error",
                terminal_reason="tool_error",
            ):
                yield evt
            return

        async for evt in self._continue_after_tool_observation(
            ctx,
            trace,
            tool_call_id=tool_call_id,
            output=result.output,
            missing_final_reason="LLM did not produce a final_message after run_trace",
            second_tool_reason="GeneralChatFlow 6B-1 does not support a second tool_call",
        ):
            yield evt

    async def _run_query_data_tool_loop(
        self,
        ctx,
        trace,
        decision: dict[str, Any],
    ) -> AsyncIterator[FlowOutput]:
        tool_call = decision.get("tool_call")
        if not isinstance(tool_call, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "LLM did not produce final or query_data tool_call",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return
        if tool_call.get("name") != "query_data":
            async for evt in self._fail(
                ctx,
                trace,
                "GeneralChatFlow 6B-2 only supports query_data tool_call",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return

        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "query_data tool_call arguments must be an object",
                session_status="error",
                terminal_reason="invalid_tool_arguments",
            ):
                yield evt
            return
        try:
            input_obj = QueryDataInput(**arguments)
        except Exception as exc:  # noqa: BLE001
            async for evt in self._fail(ctx, trace, str(exc), session_status="error", terminal_reason="invalid_tool_arguments"):
                yield evt
            return
        normalized_query = normalize_query_request(
            request_text=input_obj.request,
            country_hint=input_obj.country,
            request_understanding=None,
            clarification_answers=None,
            default_query_mode="query_only",
            default_auto_profile=False,
        )
        update_internal_trace_metadata(trace, {"tool_name": "query_data"})

        runner = DataQueryRunner(
            session=ctx.session,
            lifecycle=ctx.lifecycle,
            events=ctx.events,
            human_input=ctx.human_input,
        )

        async def _preview_query() -> DataQueryPreview:
            preview_maybe = ctx.deps.execute_query_data_cohort(
                ctx.session,
                normalized_query.effective_request_text,
                input_obj.country or normalized_query.country,
            )
            preview = await preview_maybe if inspect.isawaitable(preview_maybe) else preview_maybe
            if "uids" in preview and "child" not in preview:
                return DataQueryPreview(status="completed", output=preview)
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

        result: DataQueryRunResult | None = None
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id=trace.trace_id or trace.execution_id,
                input_payload=input_obj.model_dump(mode="json"),
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
        if handle.started_event is not None:
            yield handle.started_event
        async for item in handle.stream():
            if item.event is not None:
                yield item.event
            if item.result is not None:
                result = item.result
        if result is None:
            async for evt in self._fail(
                ctx,
                trace,
                "query_data runner completed without result",
                session_status="error",
                terminal_reason="tool_error",
            ):
                yield evt
            return
        if result.status in {"rejected", "expired"}:
            if result.status == "rejected":
                mark_query_cancelled(ctx.session.session_id)
            request_run_cancel(ctx.session.session_id, ctx.run_id)
            cancel_events = cancel_requested(ctx.session, turn_id=ctx.turn_id, run_id=ctx.run_id, trace=trace) or []
            for evt in cancel_events:
                yield evt
            return
        if result.status == "cancelled":
            request_run_cancel(ctx.session.session_id, ctx.run_id)
            cancel_events = cancel_requested(ctx.session, turn_id=ctx.turn_id, run_id=ctx.run_id, trace=trace) or []
            for evt in cancel_events:
                yield evt
            return
        if result.status == "failed":
            async for evt in self._fail(
                ctx,
                trace,
                result.error or "query_data failed",
                session_status="error",
                terminal_reason="tool_error",
            ):
                yield evt
            return

        output = result.output or {}
        async for evt in self._continue_after_tool_observation(
            ctx,
            trace,
            tool_call_id=tool_call_id,
            output=output,
            observation_content=build_query_data_observation_message(output),
            missing_final_reason="LLM did not produce a final_message after query_data",
            second_tool_reason="GeneralChatFlow 6B-2 does not support a second tool_call",
        ):
            yield evt

    async def _run_profile_tool_loop(
        self,
        ctx,
        trace,
        decision: dict[str, Any],
    ) -> AsyncIterator[FlowOutput]:
        tool_call = decision.get("tool_call")
        if not isinstance(tool_call, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "LLM did not produce final or run_profile tool_call",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return
        if tool_call.get("name") != "run_profile":
            async for evt in self._fail(
                ctx,
                trace,
                "GeneralChatFlow 6B-4 only supports run_profile tool_call",
                session_status="error",
                terminal_reason="unsupported_tool",
            ):
                yield evt
            return

        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            async for evt in self._fail(
                ctx,
                trace,
                "run_profile tool_call arguments must be an object",
                session_status="error",
                terminal_reason="invalid_tool_arguments",
            ):
                yield evt
            return

        payload = dict(arguments)
        payload["strict_data_mode"] = True
        try:
            input_obj = RunProfileInput(**payload)
        except Exception as exc:  # noqa: BLE001
            async for evt in self._fail(ctx, trace, str(exc), session_status="error", terminal_reason="invalid_tool_arguments"):
                yield evt
            return
        update_internal_trace_metadata(trace, {"tool_name": "run_profile"})
        modules = list(input_obj.modules or ["app"])
        if not modules:
            modules = ["app"]
        run_profile_input = {
            "uids": input_obj.uids,
            "app_time": input_obj.app_time,
            "modules": modules,
            "strict_data_mode": True,
        }

        from app.services.orchestrator_agent import tools as tools_mod

        profile_runner = ProfileRunner(
            session=ctx.session,
            lifecycle=ctx.lifecycle,
            events=ctx.events,
            progress_logger=log_run_profile_progress,
            profile_executor=lambda profile_input, progress_callback=None: call_tool_with_optional_progress(
                tools_mod.run_profile,
                profile_input,
                progress_callback,
            ),
        )
        handle = await profile_runner.start(
            ProfileRunSpec(
                trace_id=trace.trace_id or trace.execution_id,
                input_payload=run_profile_input,
                execution_groups=[(modules, input_obj.uids)],
                application_time_hint=input_obj.app_time,
                should_cancel=None,
            )
        )
        tool_call_id = handle.record.tool_call_id
        if handle.started_event is not None:
            yield handle.started_event

        output = None
        async for item in handle.stream():
            if isinstance(item, ProfileRunResult):
                if item.completed_event is not None:
                    yield item.completed_event
                if item.status != "completed":
                    async for evt in self._fail(
                        ctx,
                        trace,
                        item.error or "run_profile failed",
                        session_status="error",
                        terminal_reason="tool_error",
                    ):
                        yield evt
                    return
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

        if output is None:
            async for evt in self._fail(
                ctx,
                trace,
                "run_profile completed without output",
                session_status="error",
                terminal_reason="tool_error",
            ):
                yield evt
            return

        async for evt in self._continue_after_tool_observation(
            ctx,
            trace,
            tool_call_id=tool_call_id,
            output=output,
            missing_final_reason="LLM did not produce a final_message after run_profile",
            second_tool_reason="GeneralChatFlow 6B-4 does not support a second tool_call",
        ):
            yield evt

    async def _continue_after_tool_observation(
        self,
        ctx,
        trace,
        *,
        tool_call_id: str,
        output: Any,
        observation_content: str | None = None,
        missing_final_reason: str,
        second_tool_reason: str,
    ) -> AsyncIterator[FlowOutput]:
        ctx.lifecycle.append_tool_observation(
            turn_id=ctx.turn_id,
            run_id=ctx.run_id,
            tool_call_id=tool_call_id,
            content=observation_content if observation_content is not None else json.dumps(output, ensure_ascii=False),
        )
        try:
            ensure_context_fits(
                ctx.session,
                country=ctx.detected_country or ctx.session.country or "mx",
                max_tokens=MODEL_MAX_TOKENS_PER_TURN,
            )
        except Exception as exc:  # noqa: BLE001
            async for evt in self._fail(ctx, trace, str(exc), session_status="error", terminal_reason="context_fit_failed"):
                yield evt
            return

        continuation = None
        async for evt in self._generate_decision(ctx, trace, session_status_on_budget="budget_exceeded"):
            if evt.get("_decision") is not None:
                continuation = evt["_decision"]
                continue
            yield evt
        if continuation is None:
            return

        final_message = continuation.get("final_message")
        if isinstance(final_message, str) and final_message.strip():
            async for evt in self._complete(ctx, trace, final_message, confidence=continuation.get("confidence") or 0.0):
                yield evt
            return

        reason = second_tool_reason if continuation.get("tool_call") else missing_final_reason
        async for evt in self._fail(
            ctx,
            trace,
            reason,
            session_status="error",
            terminal_reason="continuation_second_tool_call" if continuation.get("tool_call") else "continuation_missing_final",
        ):
            yield evt

    async def _fail(
        self,
        ctx,
        trace,
        message: str,
        *,
        session_status: str,
        terminal_reason: str = "unknown_error",
    ) -> AsyncIterator[FlowOutput]:
        update_internal_trace_metadata(trace, {"terminal_reason": terminal_reason})
        yield update_trace_step(
            ctx.session,
            trace,
            step_id="general_answer",
            status="failed",
            result_summary=message,
        )
        finalize_trace(ctx.session, trace, final_status="error", final_message=message)
        ctx.lifecycle.mark_run_failed(run_id=ctx.run_id, session_status=session_status)
        yield {"type": "run_failed", "message": message, "trace_id": trace.trace_id or trace.execution_id}
        yield {"type": "error", "message": message, "trace_id": trace.trace_id or trace.execution_id}
