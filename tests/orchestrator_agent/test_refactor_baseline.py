from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.user_context import ProjectAccessScope, UserContext
from app.services.orchestrator_agent import agent_loop
from app.services.orchestrator_agent.flows.base import FlowControlSignal
from app.services.orchestrator_agent.flows.query_data_then_profile import QueryDataThenProfileFlow
from app.services.orchestrator_agent.flows.select_known_flow import select_known_flow
from app.services.orchestrator_agent.loop_context import FlowContext, HumanInputResult, MemoryFacade
from app.services.orchestrator_agent.planning.query_request_normalizer import NormalizedQueryRequest
from app.services.orchestrator_agent.runtime import event_recorder, session_lifecycle, trace_store
from app.services.orchestrator_agent.schemas import (
    BucketAvailability,
    DataAvailability,
    MemoryReadInput,
    MemoryWriteInput,
    NormalizedRequest,
    PlanStep,
    RequestUnderstanding,
    UidAvailability,
)
from app.services.orchestrator_agent.session_store import create_session
from app.services.orchestrator_agent.tools.create_data_agent_run_tool import CreateDataAgentRunToolInput
from app.services.orchestrator_agent.tools import get_tool_registry
from app.core.data_acquisition_capability import DataAcquisitionCapability


def _available_bucket(path: str) -> BucketAvailability:
    return BucketAvailability(
        status="available",
        available=True,
        usable_for_profile=True,
        checked_sources=["csv:available"],
        source_type="csv",
        path=path,
    )


def _missing_bucket(path: str) -> BucketAvailability:
    return BucketAvailability(
        status="missing",
        available=False,
        usable_for_profile=False,
        checked_sources=["csv:missing"],
        source_type="csv",
        path=path,
    )


def _availability_for_uid(
    uid: str,
    *,
    app: bool,
    behavior: bool,
    credit: bool,
    country: str = "mx",
) -> DataAvailability:
    available_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if ok]
    missing_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if not ok]
    return DataAvailability(
        country=country,
        checked_uids=[uid],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=_available_bucket(f"{uid}-app.csv") if app else _missing_bucket(f"{uid}-app.csv"),
                behavior=_available_bucket(f"{uid}-behavior.csv") if behavior else _missing_bucket(f"{uid}-behavior.csv"),
                credit=_available_bucket(f"{uid}-credit.csv") if credit else _missing_bucket(f"{uid}-credit.csv"),
                available_buckets=available_buckets,
                missing_buckets=missing_buckets,
            )
        ],
    )


def _availability_for_rows(
    rows: list[tuple[str, bool, bool, bool]],
    *,
    country: str = "mx",
) -> DataAvailability:
    checked_uids: list[str] = []
    per_uid: list[UidAvailability] = []
    for uid, app, behavior, credit in rows:
        checked_uids.append(uid)
        available_buckets = [
            bucket
            for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)]
            if ok
        ]
        missing_buckets = [
            bucket
            for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)]
            if not ok
        ]
        per_uid.append(
            UidAvailability(
                uid=uid,
                app=_available_bucket(f"{uid}-app.csv") if app else _missing_bucket(f"{uid}-app.csv"),
                behavior=_available_bucket(f"{uid}-behavior.csv") if behavior else _missing_bucket(f"{uid}-behavior.csv"),
                credit=_available_bucket(f"{uid}-credit.csv") if credit else _missing_bucket(f"{uid}-credit.csv"),
                available_buckets=available_buckets,
                missing_buckets=missing_buckets,
            )
        )
    return DataAvailability(
        country=country,
        checked_uids=checked_uids,
        per_uid=per_uid,
    )


def _flow_ctx(
    session,
    *,
    prompt: str,
    detected_country: str | None = "mx",
):
    return FlowContext(
        session=session,
        prompt=prompt,
        turn_id="t1",
        run_id="r1",
        detected_country=detected_country,
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )


def _user_context(*, permissions: tuple[str, ...], country: str = "mx") -> UserContext:
    return UserContext(
        user_id="42",
        username="analyst",
        email="analyst@example.com",
        display_name="Analyst",
        roles=("analyst",),
        permissions=permissions,
        project_id="7",
        project_code="proj",
        country=country,
        project_scopes=(
            ProjectAccessScope(
                project_id="7",
                project_code="proj",
                access_level="member",
                country=country,
            ),
        ),
        is_superuser=False,
    )


def _assert_metadata_includes(actual: dict[str, object] | None, expected: dict[str, object]) -> None:
    assert actual is not None
    for key, value in expected.items():
        assert actual.get(key) == value


def test_build_loop_dependencies_uses_current_agent_loop_namespace(monkeypatch):
    fake_normalize = object()
    fake_check = object()
    fake_client_factory = lambda: "fake-client"
    fake_capability = lambda: "fake-cap"
    fake_prepare = object()
    fake_execute = object()

    monkeypatch.setattr(agent_loop, "normalize_request", fake_normalize)
    monkeypatch.setattr(agent_loop, "check_data_availability", fake_check)
    monkeypatch.setattr(agent_loop, "ModelClient", fake_client_factory)
    monkeypatch.setattr(agent_loop, "get_data_acquisition_capability", fake_capability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", fake_prepare)
    monkeypatch.setattr(agent_loop, "execute_repair_query", fake_execute)

    deps = agent_loop.build_loop_dependencies()

    assert deps.normalize_request is fake_normalize
    assert deps.check_data_availability is fake_check
    assert deps.model_client_factory is fake_client_factory
    assert deps.get_data_acquisition_capability is fake_capability
    assert deps.prepare_repair_query is fake_prepare
    assert deps.execute_repair_query is fake_execute
    assert deps.original_repair_profile_data is agent_loop._ORIGINAL_REPAIR_PROFILE_DATA
    assert deps.complete_query_data_cohort is agent_loop._complete_query_data_cohort


def test_flow_context_disallows_dynamic_state_fields():
    ctx = FlowContext(
        session=object(),
        prompt="hello",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=object(),
    )

    with pytest.raises(AttributeError):
        ctx.review = {"status": "pass"}  # type: ignore[attr-defined]


def test_select_known_flow_returns_query_data_then_profile_flow_for_query_intent():
    request = NormalizedRequest(
        intent="query_data_then_profile",
        country="mx",
        uids=[],
        query_request="找出一批高流失用户并画像",
        request_summary="查询 cohort 并画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    assert type(flow).__name__ == "QueryDataThenProfileFlow"


def test_query_data_then_profile_helpers_keep_no_repair_partial_seam_and_bridge_single_bucket_repair(monkeypatch):
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    flow = QueryDataThenProfileFlow()
    ctx = _flow_ctx(create_session(country="mx"), prompt="找一批高流失用户并自动画像")
    request = NormalizedRequest(
        intent="query_data_then_profile",
        country="mx",
        uids=["u1", "u2"],
        modules=["app", "behavior", "credit"],
        request_summary="查询 cohort 并画像",
        query_request="找墨西哥最近 7 天高流失用户并自动画像",
    )

    repair_aware_decision = flow._build_post_query_profile_decision(ctx, request)
    no_repair_decision = flow._build_post_query_no_repair_decision(ctx, request)
    bridge_decision = flow._build_post_query_repair_bridge_decision(ctx, request)

    assert repair_aware_decision.mode == "repair_ready"
    assert repair_aware_decision.execution_groups
    assert no_repair_decision.mode == "partial_unavailable"
    assert no_repair_decision.execution_groups
    assert no_repair_decision.missing_uids_by_bucket == {"credit": ["u2"]}
    assert bridge_decision.mode == "repair_ready"
    assert bridge_decision.missing_uids_by_bucket == {"credit": ["u2"]}


def test_select_known_flow_returns_answer_workspace_flow_for_workspace_intent():
    request = NormalizedRequest(
        intent="answer_from_workspace",
        country="mx",
        uids=["824812551379353600"],
        modules=["behavior"],
        request_summary="总结行为画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    assert type(flow).__name__ == "AnswerWorkspaceFlow"


def test_select_known_flow_returns_clarify_scope_flow_for_need_clarification():
    request = NormalizedRequest(
        intent="need_clarification",
        country=None,
        request_summary="找一批高流失用户",
        request_understanding=RequestUnderstanding(
            intent="need_clarification",
            route_label="需要补充条件",
            rewritten_goal="补充 cohort 查询条件后继续执行",
            focus=["cohort"],
            requires_tools=False,
            route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
            answer_mode="tool_execution",
            missing_slots=["country", "time_window"],
            clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
            candidate_defaults={"country": "mx"},
        ),
    )
    flow = select_known_flow(request)
    assert flow is not None
    assert type(flow).__name__ == "ClarifyScopeFlow"


def test_select_known_flow_returns_run_trace_flow_for_run_trace_intent():
    request = NormalizedRequest(
        intent="run_trace",
        country="mx",
        uids=["824812551379353600"],
        trace_days=30,
        request_summary="分析用户轨迹",
    )
    flow = select_known_flow(request)
    assert flow is not None
    assert type(flow).__name__ == "RunTraceFlow"


def _general_chat_understanding(*, requires_tools=True, answer_mode="general_chat"):
    return RequestUnderstanding(
        intent="general_chat",
        route_label="通用 Agent 对话",
        rewritten_goal="进入通用 Agent 模式回答当前问题",
        focus=["summary"],
        requires_tools=requires_tools,
        route_reason="当前问题不匹配确定性画像、取数或轨迹路径，进入通用 Agent 模式。",
        answer_mode=answer_mode,
    )


def _general_chat_request(**updates):
    base = {
        "intent": "general_chat",
        "country": "mx",
        "uids": [],
        "uid_file_path": None,
        "modules": [],
        "request_summary": "通用问答",
        "query_request": None,
        "request_understanding": _general_chat_understanding(requires_tools=False),
    }
    base.update(updates)
    return NormalizedRequest(**base)


def test_select_known_flow_returns_general_chat_flow_for_general_chat_intent():
    flow = select_known_flow(_general_chat_request())

    assert flow is not None
    assert type(flow).__name__ == "GeneralChatFlow"


def test_select_known_flow_returns_data_agent_run_flow_for_create_data_agent_run_intent():
    request = NormalizedRequest(
        intent="create_data_agent_run",
        country="mx",
        uids=[],
        uid_file_path=None,
        modules=[],
        request_summary="创建 Data Agent SQL 审核任务",
        query_request="用 Data Agent 生成 SQL，查询最近 7 天高风险用户",
    )

    flow = select_known_flow(request)

    assert flow is not None
    assert type(flow).__name__ == "DataAgentRunFlow"


def test_select_known_flow_returns_clarify_data_request_flow_for_ambiguous_data_intent():
    request = NormalizedRequest(
        intent="clarify_data_request",
        country="mx",
        uids=[],
        uid_file_path=None,
        modules=[],
        request_summary="澄清数据请求",
        query_request="帮我查一下数据",
    )

    flow = select_known_flow(request)

    assert flow is not None
    assert type(flow).__name__ == "ClarifyDataRequestFlow"


def test_create_data_agent_run_tool_input_rejects_sql_text_and_manual_sql_fields():
    with pytest.raises(ValidationError):
        CreateDataAgentRunToolInput.model_validate(
            {
                "natural_language_request": "查询最近 7 天高风险用户",
                "target_country": "mx",
                "run_type": "cohort_query",
                "sql_text": "SELECT * FROM users",
                "manual_sql": "SELECT * FROM users",
            }
        )


def test_general_tool_registry_does_not_expose_create_data_agent_run_tool():
    registry = get_tool_registry()
    assert "create_data_agent_run_tool" not in registry


@pytest.mark.timeout(3)
def test_data_agent_run_flow_creates_review_run_and_emits_artifact_without_approve_or_execute(monkeypatch):
    session = create_session(country="mx")
    session_lifecycle.create_turn(session, turn_id="t1", client_turn_id=None, prompt="用 Data Agent 生成 SQL，查询最近 7 天高风险用户")
    session_lifecycle.create_turn_run(session, turn_id="t1", run_id="r1")
    request = NormalizedRequest(
        intent="create_data_agent_run",
        country="mx",
        uids=[],
        modules=[],
        request_summary="创建 Data Agent SQL 审核任务",
        query_request="用 Data Agent 生成 SQL，查询最近 7 天高风险用户",
        data_agent_run_type="cohort_query",
    )
    flow = select_known_flow(request)
    assert flow is not None

    called = {"approve": 0, "execute": 0, "tool_inputs": []}

    async def _fake_create_run(*, user_context, request_context, payload):
        del request_context
        called["tool_inputs"].append((user_context.username, payload))
        return {
            "type": "data_agent_run",
            "run_id": "da-run-1",
            "status": "awaiting_review",
        }

    def _forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("DataAgentRunFlow must never approve or execute runs")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.flows.data_agent_run.create_data_agent_run_tool",
        _fake_create_run,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.flows.data_agent_run.DataAgentService.approve_run",
        _forbidden,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.flows.data_agent_run.DataAgentService.execute_run",
        _forbidden,
    )

    ctx = FlowContext(
        session=session,
        prompt="用 Data Agent 生成 SQL，查询最近 7 天高风险用户",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=session_lifecycle.SessionLifecycle(session),
        events=event_recorder.EventRecorder(session, turn_id="t1", run_id="r1"),
        trace=trace_store.TraceStore(session),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
        user_context=_user_context(permissions=("data:query:generate", "data:query:view_sql")),
        request_context=None,
    )

    async def _drive():
        return [item async for item in flow.run(ctx, request)]

    items = asyncio.run(_drive())

    assert called["tool_inputs"] == [
        (
            "analyst",
            {
                "natural_language_request": "用 Data Agent 生成 SQL，查询最近 7 天高风险用户",
                "target_country": "mx",
                "run_type": "cohort_query",
                "output_bucket": None,
                "output_format": None,
            },
        )
    ]
    assert items[-1]["type"] == "final"
    assert items[-1]["artifacts"] == [{"type": "data_agent_run", "run_id": "da-run-1"}]
    assert session.turns[0].artifacts == [{"type": "data_agent_run", "run_id": "da-run-1"}]


@pytest.mark.timeout(3)
def test_clarify_data_request_flow_uses_original_prompt_when_user_chooses_sql_review_task(monkeypatch):
    session = create_session(country="mx")
    session_lifecycle.create_turn(session, turn_id="t1", client_turn_id=None, prompt="帮我查一下数据")
    session_lifecycle.create_turn_run(session, turn_id="t1", run_id="r1")
    request = NormalizedRequest(
        intent="clarify_data_request",
        country="mx",
        uids=[],
        modules=[],
        request_summary="澄清数据任务类型",
        query_request="帮我查一下数据",
        request_understanding=RequestUnderstanding(
            intent="clarify_data_request",
            route_label="需要澄清数据任务类型",
            rewritten_goal="先澄清是继续普通画像对话，还是创建 SQL 审核任务",
            focus=["data_request"],
            requires_tools=False,
            route_reason="当前请求只表达了要查数据，但还没有说明是普通画像还是要创建 SQL 审核任务。",
            answer_mode="tool_execution",
            missing_slots=["task_type"],
            clarification_prompt="你是想继续普通画像/对话，还是创建一个需要人工审核的 SQL 任务？",
            candidate_defaults={"task_type": "profile_chat"},
        ),
    )
    flow = select_known_flow(request)
    assert flow is not None

    captured = {"payloads": []}

    async def _fake_create_run(*, user_context, request_context, payload):
        del user_context, request_context
        captured["payloads"].append(payload)
        return {"type": "data_agent_run", "run_id": "da-run-clarify", "status": "awaiting_review"}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.flows.data_agent_run.create_data_agent_run_tool",
        _fake_create_run,
    )

    class _HumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", payload={"selected_option": "create_sql_review_task"})

    ctx = FlowContext(
        session=session,
        prompt="帮我查一下数据",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=session_lifecycle.SessionLifecycle(session),
        events=event_recorder.EventRecorder(session, turn_id="t1", run_id="r1"),
        trace=trace_store.TraceStore(session),
        human_input=_HumanInput(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
        user_context=_user_context(permissions=("data:query:generate", "data:query:view_sql")),
        request_context=None,
    )

    async def _drive():
        return [item async for item in flow.run(ctx, request)]

    items = asyncio.run(_drive())

    assert captured["payloads"] == [
        {
            "natural_language_request": "帮我查一下数据",
            "target_country": "mx",
            "run_type": "cohort_query",
            "output_bucket": None,
            "output_format": None,
        }
    ]
    assert items[-1]["type"] == "final"
    assert items[-1]["artifacts"] == [{"type": "data_agent_run", "run_id": "da-run-clarify"}]


@pytest.mark.parametrize(
    ("normalized_request", "expected"),
    [
        (_general_chat_request(), True),
        (_general_chat_request(request_understanding=None), False),
        (_general_chat_request(request_understanding=_general_chat_understanding(requires_tools=True)), False),
        (
            _general_chat_request(
                request_understanding=_general_chat_understanding(requires_tools=False).model_copy(update={"requires_tools": None})
            ),
            False,
        ),
        (_general_chat_request(uids=["824812551379353600"]), False),
        (_general_chat_request(uid_file_path="./data/id_files/mx/sample.txt"), False),
        (_general_chat_request(query_request="找出最近 7 天高风险用户"), False),
    ],
)
def test_general_chat_flow_can_handle_only_explicit_no_tool_requests(normalized_request, expected):
    flow = select_known_flow(normalized_request)
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt="你是谁？")

    assert asyncio.run(flow.can_handle(ctx, normalized_request)) is expected


def test_general_chat_flow_can_handle_memory_write_tool_loop_prompt():
    flow = select_known_flow(_general_chat_request(request_understanding=None))
    assert flow is not None

    ctx = _flow_ctx(
        create_session(country="mx"),
        prompt="请记住：我偏好中文输出，并且回答要简洁。",
    )

    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None))) is True


def test_general_chat_flow_can_handle_trace_like_tool_loop_prompt():
    flow = select_known_flow(_general_chat_request(request_understanding=None))
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt="你好，先帮我查一下用户行为轨迹")

    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None))) is True


def test_general_chat_flow_can_handle_memory_read_tool_loop_prompt():
    flow = select_known_flow(_general_chat_request(request_understanding=None))
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt="你还记得我之前说过的输出偏好吗？")

    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None))) is True


def test_general_chat_flow_can_handle_profile_like_tool_loop_prompt():
    flow = select_known_flow(_general_chat_request(request_understanding=None))
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt="请执行这个用户的画像分析")

    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None))) is True


def test_general_chat_flow_can_handle_query_like_tool_loop_prompt():
    flow = select_known_flow(_general_chat_request(request_understanding=None))
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt="帮我筛选最近 7 天高风险用户列表")

    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None))) is True


def test_general_chat_flow_can_handle_query_plus_profile_prompt_stays_legacy():
    flow = select_known_flow(_general_chat_request(request_understanding=None))
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt="帮我筛选最近 7 天高风险用户并生成画像")

    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None))) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "请先筛选最近 7 天高风险用户，再把结果记住。",
        "先查看这个用户的行为轨迹，再记住结论。",
        "先分析这个用户画像，再把结论保存到记忆。",
    ],
)
def test_general_chat_flow_multi_family_prompts_stay_legacy_and_not_no_tool(prompt):
    flow = select_known_flow(_general_chat_request(request_understanding=None))
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt=prompt)

    assert flow._mode(ctx, _general_chat_request(request_understanding=None)) is None
    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None))) is False


@pytest.mark.parametrize(
    "updates",
    [
        {"uids": ["824812551379353600"]},
        {"uid_file_path": "./data/id_files/mx/sample.txt"},
        {"query_request": "筛选最近 7 天高风险用户"},
    ],
)
def test_general_chat_flow_can_handle_query_like_false_when_structured_query_fields_present(updates):
    flow = select_known_flow(_general_chat_request(request_understanding=None, **updates))
    assert flow is not None

    ctx = _flow_ctx(create_session(country="mx"), prompt="帮我筛选最近 7 天高风险用户列表")

    assert asyncio.run(flow.can_handle(ctx, _general_chat_request(request_understanding=None, **updates))) is False


def test_build_memory_facade_binds_detected_country_scope(monkeypatch):
    session = create_session(user_id="u1", project_id="p1", country="th")
    seen: list[tuple[str, str, str, str]] = []

    def _fake_write(input_obj, *, user_id, project_id, default_country):
        seen.append(("write", user_id, project_id, default_country))
        return {"ok": True}

    def _fake_read(input_obj, *, user_id, project_id, default_country):
        seen.append(("read", user_id, project_id, default_country))
        return {"items": []}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.memory.memory_write_scoped", _fake_write)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.memory.memory_read_scoped", _fake_read)

    facade = agent_loop._build_memory_facade(session, detected_country="mx")
    facade.write(MemoryWriteInput(key="pref-key", value="请记住：偏好中文输出"))
    facade.read(MemoryReadInput(key_pattern="pref-key"))

    assert seen == [
        ("write", "u1", "p1", "mx"),
        ("read", "u1", "p1", "mx"),
    ]


def test_build_memory_facade_falls_back_to_session_country_then_mx(monkeypatch):
    seen: list[str] = []

    def _fake_write(input_obj, *, user_id, project_id, default_country):
        seen.append(default_country)
        return {"ok": True}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.memory.memory_write_scoped", _fake_write)

    facade_with_session_country = agent_loop._build_memory_facade(
        create_session(user_id="u1", project_id="p1", country="th"),
        detected_country=None,
    )
    facade_with_session_country.write(MemoryWriteInput(key="pref-key", value="请记住：偏好中文输出"))

    facade_with_default = agent_loop._build_memory_facade(
        create_session(user_id="u1", project_id="p1", country=None),
        detected_country=None,
    )
    facade_with_default.write(MemoryWriteInput(key="pref-key", value="请记住：偏好中文输出"))

    assert seen == ["th", "mx"]


def test_select_known_flow_returns_profile_flow_for_profile_uid_intent():
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=["824812551379353600"],
        modules=["app"],
        request_summary="分析一个 UID",
    )
    flow = select_known_flow(request)
    assert flow is not None
    assert type(flow).__name__ == "ProfileFlow"


def test_select_known_flow_returns_profile_flow_for_profile_batch_intent():
    request = NormalizedRequest(
        intent="profile_batch",
        country="mx",
        uids=["824812551379353600", "900000000000000001"],
        modules=[],
        request_summary="分析一批 UID",
    )
    flow = select_known_flow(request)
    assert flow is not None
    assert type(flow).__name__ == "ProfileFlow"


@pytest.mark.timeout(3)
def test_query_data_then_profile_flow_can_handle_true_for_unsupported_country_without_side_effects(monkeypatch):
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: (_ for _ in ()).throw(AssertionError("capability should not be probed for non-mx guard")),
    )
    session = create_session(country="th")
    request = NormalizedRequest(
        intent="query_data_then_profile",
        country="th",
        uids=[],
        modules=["app"],
        request_summary="查询泰国 cohort 并画像",
        query_request="最近 7 天高流失用户",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = _flow_ctx(session, prompt="查询泰国 cohort 并画像", detected_country="th")
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_query_data_then_profile_flow_can_handle_true_when_capability_disabled_without_side_effects(monkeypatch):
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_by_config"),
    )
    session = create_session(country="mx")
    request = NormalizedRequest(
        intent="query_data_then_profile",
        country="mx",
        uids=[],
        modules=["app"],
        request_summary="查询 cohort 并画像",
        query_request="找墨西哥最近 7 天高流失用户并分析",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = _flow_ctx(session, prompt="找墨西哥最近 7 天高流失用户并分析")
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_query_data_then_profile_flow_can_handle_true_when_capability_enabled_without_side_effects(monkeypatch):
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    session = create_session(country="mx")
    request = NormalizedRequest(
        intent="query_data_then_profile",
        country="mx",
        uids=[],
        modules=["app"],
        request_summary="查询 cohort 并画像",
        query_request="找墨西哥最近 7 天高流失用户并分析",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = _flow_ctx(session, prompt="找墨西哥最近 7 天高流失用户并分析")
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_query_data_then_profile_flow_can_handle_false_when_country_unknown_without_side_effects(monkeypatch):
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: (_ for _ in ()).throw(AssertionError("capability should not be probed when country is unknown")),
    )
    session = create_session(country=None)
    request = NormalizedRequest(
        intent="query_data_then_profile",
        country=None,
        uids=[],
        modules=["app"],
        request_summary="查询 cohort 并画像",
        query_request="找最近 7 天高流失用户并分析",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = _flow_ctx(session, prompt="找最近 7 天高流失用户并分析", detected_country=None)
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is False
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_answer_workspace_flow_can_handle_true_without_side_effects(monkeypatch):
    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {
                "uid": "824812551379353600",
                "module": "behavior",
                "summary": "行为画像：近30天登录偏低，流失风险高。",
                "structured_result": {"risk_level": "high"},
            }
        ],
    }
    request = NormalizedRequest(
        intent="answer_from_workspace",
        country="mx",
        uids=["824812551379353600"],
        modules=["behavior"],
        request_summary="总结行为画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = FlowContext(
        session=session,
        prompt="帮我总结一下这个用户的行为画像特点",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_answer_workspace_flow_can_handle_false_when_workspace_evidence_missing():
    session = create_session(country="mx")
    request = NormalizedRequest(
        intent="answer_from_workspace",
        country="mx",
        uids=["824812551379353600"],
        modules=["behavior"],
        request_summary="总结行为画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = FlowContext(
        session=session,
        prompt="帮我总结一下这个用户的行为画像特点",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is False


@pytest.mark.timeout(3)
def test_run_trace_flow_can_handle_requires_uid():
    flow = select_known_flow(
        NormalizedRequest(
            intent="run_trace",
            country="mx",
            uids=["824812551379353600"],
            trace_days=7,
            request_summary="分析用户轨迹",
        )
    )
    assert flow is not None
    ctx = FlowContext(
        session=create_session(country="mx"),
        prompt="帮我看轨迹",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )

    handled = asyncio.run(
        flow.can_handle(
            ctx,
            NormalizedRequest(
                intent="run_trace",
                country="mx",
                uids=[],
                trace_days=7,
                request_summary="分析用户轨迹",
            ),
        )
    )

    assert handled is False


@pytest.mark.timeout(3)
def test_run_trace_flow_can_handle_true_with_uid():
    flow = select_known_flow(
        NormalizedRequest(
            intent="run_trace",
            country="mx",
            uids=["824812551379353600"],
            trace_days=7,
            request_summary="分析用户轨迹",
        )
    )
    assert flow is not None
    ctx = FlowContext(
        session=create_session(country="mx"),
        prompt="帮我看轨迹",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )

    handled = asyncio.run(
        flow.can_handle(
            ctx,
            NormalizedRequest(
                intent="run_trace",
                country="mx",
                uids=["824812551379353600"],
                trace_days=7,
                request_summary="分析用户轨迹",
            ),
        )
    )

    assert handled is True


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_without_side_effects(monkeypatch):
    session = create_session(country="mx")
    uid = "824812551379353600"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=False, credit=False, country=country or "mx"),
    )
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid],
        modules=["app"],
        request_summary="分析这个 UID 的 app 画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = FlowContext(
        session=session,
        prompt="分析这个 UID 的 app 画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_false_for_profile_batch_when_repair_capability_enabled(monkeypatch):
    session = create_session(country="mx")
    uid = "824812551379353600"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_batch",
        country="mx",
        uids=[uid],
        modules=["app", "behavior", "credit"],
        request_summary="批量分析这个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = FlowContext(
        session=session,
        prompt="批量分析这个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is False
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_false_when_capability_unknown(monkeypatch):
    session = create_session(country="mx")
    uid = "824812551379353600"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: (_ for _ in ()).throw(RuntimeError("capability probe failed")),
    )
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid],
        modules=["app", "behavior", "credit"],
        request_summary="分析这个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    ctx = FlowContext(
        session=session,
        prompt="分析这个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is False
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_multiple_uids_without_side_effects(monkeypatch):
    uid = "824812551379353600"
    other_uid = "900000000000000001"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (uid, True, True, True),
                (other_uid, True, False, False),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_for_test"),
    )
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid, other_uid],
        modules=[],
        request_summary="分析这两个 UID",
    )
    flow = select_known_flow(
        NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid, other_uid],
            modules=[],
            request_summary="分析这个 UID",
        )
    )
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="分析这两个 UID",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_uid_file_path_when_capability_enabled(monkeypatch):
    uid = "824812551379353600"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=True, credit=True, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_batch",
        country="mx",
        uids=[],
        uid_file_path="./data/id_files/mx/sample.txt",
        modules=[],
        request_summary="分析 UID 文件",
    )
    flow = select_known_flow(
        NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=["seed"],
            modules=[],
            request_summary="分析一批 UID",
        )
    )
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="分析 ./data/id_files/mx/sample.txt",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_false_for_uid_file_path_when_capability_unknown(monkeypatch):
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: type("UnknownCapability", (), {"mode": "unknown", "enabled": None, "reason": "unknown_for_test"})(),
    )
    request = NormalizedRequest(
        intent="profile_batch",
        country="mx",
        uids=[],
        uid_file_path="./data/id_files/mx/sample.txt",
        modules=[],
        request_summary="分析 UID 文件",
    )
    flow = select_known_flow(
        NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=["seed"],
            modules=[],
            request_summary="分析一批 UID",
        )
    )
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="分析 ./data/id_files/mx/sample.txt",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is False
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_uid_file_path_when_capability_disabled(monkeypatch):
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_for_test"),
    )
    request = NormalizedRequest(
        intent="profile_batch",
        country="mx",
        uids=[],
        uid_file_path="./data/id_files/mx/sample.txt",
        modules=[],
        request_summary="分析 UID 文件",
    )
    flow = select_known_flow(
        NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=["seed"],
            modules=[],
            request_summary="分析一批 UID",
        )
    )
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="分析 ./data/id_files/mx/sample.txt",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_single_uid_repair_ready_without_side_effects(monkeypatch):
    uid = "824812551379353600"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid],
        modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        request_summary="分析这个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="分析这个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_single_uid_two_bucket_repair_ready_without_side_effects(monkeypatch):
    uid = "824812551379353600"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=False, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid],
        modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        request_summary="分析这个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="分析这个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_profile_batch_multi_uid_single_bucket_repair_ready_without_side_effects(monkeypatch):
    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (full_uid, True, True, True),
                (repair_uid, True, True, False),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_batch",
        country="mx",
        uids=[full_uid, repair_uid],
        modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        request_summary="批量分析这两个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="批量分析这两个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_profile_uid_multi_uid_single_bucket_repair_ready_without_side_effects(monkeypatch):
    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (full_uid, True, True, True),
                (repair_uid, True, True, False),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[full_uid, repair_uid],
        modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        request_summary="批量分析这两个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="批量分析这两个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_profile_batch_multi_uid_two_bucket_repair_ready_without_side_effects(monkeypatch):
    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (full_uid, True, True, True),
                (credit_uid, True, True, False),
                (behavior_uid, True, False, True),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_batch",
        country="mx",
        uids=[full_uid, credit_uid, behavior_uid],
        modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        request_summary="批量分析这三个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="批量分析这三个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_profile_flow_can_handle_true_for_profile_uid_multi_uid_two_bucket_repair_ready_without_side_effects(monkeypatch):
    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (full_uid, True, True, True),
                (credit_uid, True, True, False),
                (behavior_uid, True, False, True),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[full_uid, credit_uid, behavior_uid],
        modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        request_summary="批量分析这三个 UID 的完整画像",
    )
    flow = select_known_flow(request)
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt="批量分析这三个 UID 的完整画像",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, request))

    assert handled is True
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("normalized_request", "availability"),
    [
        (
            NormalizedRequest(
                intent="profile_batch",
                country="mx",
                uids=["824812551379353600"],
                modules=["app", "behavior", "credit"],
                request_summary="批量画像",
            ),
            _availability_for_uid("824812551379353600", app=True, behavior=True, credit=False),
        ),
        (
            NormalizedRequest(
                intent="profile_uid",
                country="mx",
                uids=["824812551379353600"],
                uid_file_path="./data/id_files/mx/sample.txt",
                modules=["app", "behavior", "credit"],
                request_summary="uid_file repair",
            ),
            _availability_for_uid("824812551379353600", app=True, behavior=True, credit=False),
        ),
        (
            NormalizedRequest(
                intent="profile_uid",
                country="co",
                uids=["824812551379353600"],
                modules=["app", "behavior", "credit"],
                request_summary="非 mx repair",
            ),
            _availability_for_uid("824812551379353600", app=True, behavior=True, credit=False, country="co"),
        ),
        (
            NormalizedRequest(
                intent="profile_uid",
                country="mx",
                uids=["824812551379353600"],
                modules=["app", "behavior", "credit"],
                request_summary="三 bucket repair",
            ),
            _availability_for_uid("824812551379353600", app=False, behavior=False, credit=False),
        ),
        (
            NormalizedRequest(
                intent="query_data_then_profile",
                country="mx",
                uids=["824812551379353600"],
                modules=["app", "behavior", "credit"],
                request_summary="query_data_then_profile",
                query_request="先查 cohort",
            ),
            _availability_for_uid("824812551379353600", app=True, behavior=True, credit=False),
        ),
        (
            NormalizedRequest(
                intent="profile_batch",
                country="mx",
                uids=["824812551379353600", "824812551379353601"],
                modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
                request_summary="三 bucket batch repair",
            ),
            _availability_for_rows(
                [
                    ("824812551379353600", False, False, False),
                    ("824812551379353601", True, True, True),
                ],
            ),
        ),
    ],
)
def test_profile_flow_can_handle_false_for_out_of_scope_repair_ready_requests_without_side_effects(monkeypatch, normalized_request, availability):
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: availability,
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    flow = select_known_flow(
        NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=["seed"],
            modules=["app"],
            request_summary="seed",
        )
    )
    assert flow is not None
    session = create_session(country="mx")
    ctx = FlowContext(
        session=session,
        prompt=normalized_request.request_summary,
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=object(),
        events=object(),
        trace=object(),
        human_input=object(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )
    before_messages = len(session.messages)
    before_traces = len(session.execution_traces)
    before_tool_calls = len(session.tool_calls)
    before_runs = len(session.turns)

    handled = asyncio.run(flow.can_handle(ctx, normalized_request))

    assert handled is False
    assert len(session.messages) == before_messages
    assert len(session.execution_traces) == before_traces
    assert len(session.tool_calls) == before_tool_calls
    assert len(session.turns) == before_runs


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_three_bucket_repair_falls_back_to_legacy(monkeypatch):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=False, behavior=False, credit=False, country=country or "mx"),
    )

    def _fail(*args, **kwargs):
        raise AssertionError("ProfileFlow repair path should not run for >2 missing buckets")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    tool_names = [evt.get("tool_name") for evt in events if evt["type"] in {"tool_started", "tool_completed"}]

    assert called["legacy"] is True
    assert "repair_profile_data" not in tool_names
    assert "run_profile" not in tool_names


@pytest.mark.timeout(3)
def test_clarify_scope_flow_emits_awaiting_resolution_before_wait_and_returns_resume_signal():
    session = create_session(country="mx")
    session_lifecycle.create_turn(session, turn_id="t1", client_turn_id=None, prompt="找一批高流失用户")
    session_lifecycle.create_turn_run(session, turn_id="t1", run_id="r1")
    request = NormalizedRequest(
        intent="need_clarification",
        country=None,
        request_summary="找一批高流失用户",
        query_request="找一批高流失用户",
        request_understanding=RequestUnderstanding(
            intent="need_clarification",
            route_label="需要补充条件",
            rewritten_goal="补充 cohort 查询条件后继续执行",
            focus=["cohort"],
            requires_tools=False,
            route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
            answer_mode="tool_execution",
            missing_slots=["country", "time_window"],
            clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
            candidate_defaults={"country": "mx"},
        ),
    )
    flow = select_known_flow(request)
    assert flow is not None

    class _HumanInput:
        def __init__(self) -> None:
            self.wait_started = asyncio.Event()
            self.release_wait = asyncio.Event()

        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            self.wait_started.set()
            await self.release_wait.wait()
            return HumanInputResult(
                status="resolved",
                payload={"country": "mx", "time_window": "最近 7 天"},
            )

    human_input = _HumanInput()
    ctx = FlowContext(
        session=session,
        prompt="找一批高流失用户",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=session_lifecycle.SessionLifecycle(session),
        events=event_recorder.EventRecorder(session, turn_id="t1", run_id="r1"),
        trace=trace_store.TraceStore(session),
        human_input=human_input,
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )

    async def _drive():
        gen = flow.run(ctx, request)
        first = await gen.__anext__()
        second = await gen.__anext__()
        third = await gen.__anext__()
        assert first["type"] == "execution_plan"
        assert second["type"] == "plan_step_status"
        assert third["type"] == "awaiting_resolution"
        assert human_input.wait_started.is_set() is False
        pending = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        assert human_input.wait_started.is_set() is True
        human_input.release_wait.set()
        signal = await pending
        return signal

    signal = asyncio.run(_drive())
    run = session_lifecycle.find_run(session, "r1")
    assert isinstance(signal, FlowControlSignal)
    assert signal.kind == "clarification_resume"
    assert signal.payload["answers"] == {"country": "mx", "time_window": "最近 7 天"}
    assert run is not None
    assert run.pending_resolution is None
    assert run.status == "running"


@pytest.mark.timeout(3)
def test_clarify_scope_flow_timeout_emits_single_blocked_final_and_cleans_pending():
    session = create_session(country="mx")
    session_lifecycle.create_turn(session, turn_id="t1", client_turn_id=None, prompt="找一批高流失用户")
    session_lifecycle.create_turn_run(session, turn_id="t1", run_id="r1")
    request = NormalizedRequest(
        intent="need_clarification",
        country=None,
        request_summary="找一批高流失用户",
        query_request="找一批高流失用户",
        request_understanding=RequestUnderstanding(
            intent="need_clarification",
            route_label="需要补充条件",
            rewritten_goal="补充 cohort 查询条件后继续执行",
            focus=["cohort"],
            requires_tools=False,
            route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
            answer_mode="tool_execution",
            missing_slots=["country", "time_window"],
            clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
            candidate_defaults={"country": "mx"},
        ),
    )
    flow = select_known_flow(request)
    assert flow is not None

    class _HumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            return HumanInputResult(status="expired")

    ctx = FlowContext(
        session=session,
        prompt="找一批高流失用户",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=session_lifecycle.SessionLifecycle(session),
        events=event_recorder.EventRecorder(session, turn_id="t1", run_id="r1"),
        trace=trace_store.TraceStore(session),
        human_input=_HumanInput(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )

    async def _drive():
        return [item async for item in flow.run(ctx, request)]

    items = asyncio.run(_drive())
    run = session_lifecycle.find_run(session, "r1")
    types = [item["type"] for item in items if isinstance(item, dict)]
    assert types.count("final") == 1
    assert items[-1]["type"] == "final"
    assert run is not None
    assert run.pending_resolution is None
    assert run.status == "completed"


@pytest.mark.timeout(3)
def test_clarify_scope_flow_external_cancel_cleans_pending_resolution():
    session = create_session(country="mx")
    session_lifecycle.create_turn(session, turn_id="t1", client_turn_id=None, prompt="找一批高流失用户")
    session_lifecycle.create_turn_run(session, turn_id="t1", run_id="r1")
    request = NormalizedRequest(
        intent="need_clarification",
        country=None,
        request_summary="找一批高流失用户",
        query_request="找一批高流失用户",
        request_understanding=RequestUnderstanding(
            intent="need_clarification",
            route_label="需要补充条件",
            rewritten_goal="补充 cohort 查询条件后继续执行",
            focus=["cohort"],
            requires_tools=False,
            route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
            answer_mode="tool_execution",
            missing_slots=["country", "time_window"],
            clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
            candidate_defaults={"country": "mx"},
        ),
    )
    flow = select_known_flow(request)
    assert flow is not None

    class _HumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            raise asyncio.CancelledError()

    ctx = FlowContext(
        session=session,
        prompt="找一批高流失用户",
        turn_id="t1",
        run_id="r1",
        detected_country="mx",
        client=object(),
        lifecycle=session_lifecycle.SessionLifecycle(session),
        events=event_recorder.EventRecorder(session, turn_id="t1", run_id="r1"),
        trace=trace_store.TraceStore(session),
        human_input=_HumanInput(),
        tools=object(),
        memory=None,
        deps=agent_loop.build_loop_dependencies(),
    )

    async def _drive():
        gen = flow.run(ctx, request)
        await gen.__anext__()
        await gen.__anext__()
        await gen.__anext__()
        with pytest.raises(asyncio.CancelledError):
            await gen.__anext__()

    asyncio.run(_drive())
    run = session_lifecycle.find_run(session, "r1")
    assert run is not None
    assert run.pending_resolution is None
    assert run.status == "running"


@pytest.mark.timeout(3)
def test_run_agent_loop_uses_legacy_fallback_when_selector_returns_none(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: None})())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=["824812551379353600"],
            modules=["app"],
            request_summary="分析一个 UID",
        ),
    )
    monkeypatch.setattr(agent_loop, "select_known_flow", lambda request: None)

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        args[0].final_message = "legacy-final"
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID", country="mx")]

    events = asyncio.run(collect())
    assert called["legacy"] is True
    assert any(evt["type"] == "final" for evt in events)


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_uses_flow_and_skips_legacy(monkeypatch):
    ack_requests: list[dict[str, object]] = []
    completed_sql_texts: list[str] = []
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, True)],
        ),
        seen_ack_requests=ack_requests,
        seen_completed_sql_texts=completed_sql_texts,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    awaiting_evt = next(evt for evt in events if evt["type"] == "awaiting_user_ack")

    assert called["legacy"] is False
    assert review_evt["status"] == "pass"
    assert seen_profile_inputs == [
        {
            "uids": ["u1", "u2"],
            "app_time": None,
            "modules": ["app", "behavior"],
            "strict_data_mode": True,
        },
    ]
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert "查询摘要" in awaiting_evt["sql_text"]
    assert "筛选条件" in awaiting_evt["sql_text"]
    assert "确认提示" in awaiting_evt["sql_text"]
    assert "原始 SQL" in awaiting_evt["sql_text"]
    assert "SELECT uid FROM t" in awaiting_evt["sql_text"]
    assert awaiting_evt["sql_text"] != "SELECT uid FROM t"
    assert ack_requests and ack_requests[0]["sql_text"] == awaiting_evt["sql_text"]
    assert completed_sql_texts == ["SELECT uid FROM t"]
    assert not any(
        step["step_id"] == "clarify_scope"
        for evt in plan_events
        for step in evt["steps"]
    )


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_blocks_unsupported_country_without_legacy_or_tools(monkeypatch):
    session = create_session(country="th")
    called = {"legacy": False}
    assistant_before = len([msg for msg in session.messages if msg.role == "assistant"])

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="th",
            uids=[],
            modules=["app", "behavior", "credit"],
            request_summary="查询泰国 cohort 并画像",
            query_request="最近 7 天高流失用户",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: (_ for _ in ()).throw(AssertionError("capability should not be probed for unsupported country guard")),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_query_data_cohort",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("query_data should not run for unsupported country guard")),
    )

    def _fail():
        raise AssertionError("get_tool_registry should not be called for query_data_then_profile guard flow")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我找最近7天高流失用户并分析", country="th")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")
    trace = session.execution_traces[-1]

    assert called["legacy"] is False
    assert [step["step_id"] for step in plan_evt["steps"]] == ["query_data", "review_final"]
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "unsupported_country" for issue in review_evt["issues"])
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "query_data" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    _assert_metadata_includes(trace.internal_metadata, {
        "flow_name": "QueryDataThenProfileFlow",
        "flow_mode": "guard_unsupported_country",
        "country": "th",
        "terminal_reason": "unsupported_country",
    })


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_blocks_when_data_acquisition_disabled_without_legacy_or_tools(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    assistant_before = len([msg for msg in session.messages if msg.role == "assistant"])

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=["app"],
            request_summary="查询 cohort 并画像",
            query_request="找墨西哥最近 7 天高流失用户并分析",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_by_config"),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_query_data_cohort",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("query_data should not run when capability is disabled")),
    )

    def _fail():
        raise AssertionError("get_tool_registry should not be called for query_data_then_profile guard flow")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")

    assert called["legacy"] is False
    assert [step["step_id"] for step in plan_evt["steps"]] == ["query_data", "review_final"]
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "query_data" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_flow_signal_stays_internal_and_calls_legacy_resume(monkeypatch):
    session = create_session(country="mx")
    called = {"resume": False}

    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx"},
            ),
        ),
    )
    monkeypatch.setattr(agent_loop, "ModelClient", lambda: object())

    ack_requests: list[dict[str, object]] = []
    completed_sql_texts: list[str] = []

    class _FakeHumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            return HumanInputResult(
                status="resolved",
                payload={"country": "mx", "time_window": "最近 7 天"},
            )

    monkeypatch.setattr(agent_loop, "HumanInputController", lambda: _FakeHumanInput())

    async def _resume(*args, **kwargs):
        called["resume"] = True
        session.final_message = "legacy-resume-final"
        yield {"type": "final", "final_message": "legacy-resume-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_clarification_resume_legacy", _resume)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assert called["resume"] is True
    assert not any(evt.get("type") == "clarification_resume" for evt in events)
    assert events[-1]["type"] == "final"
    assert events[-1]["final_message"] == "legacy-resume-final"


def _setup_query_only_clarification_resume_baseline(
    monkeypatch,
    *,
    ack_status: str = "approved",
    preview_result: dict[str, object] | None = None,
    preview_exception: Exception | None = None,
    complete_result: dict[str, object] | None = None,
    complete_exception: Exception | None = None,
):
    session = create_session(country="mx")
    assistant_before = len([msg for msg in session.messages if msg.role == "assistant"])
    called = {"legacy_resume": False}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=["app", "behavior"],
            trace_days=7,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并分析",
        }),
    )

    class _FakeHumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            return HumanInputResult(
                status="resolved",
                payload={"country": "mx", "time_window": "最近 7 天", "auto_profile": False},
            )

        async def request_ack(self, **kwargs):
            return HumanInputResult(status="resolved", action="ack_requested")

        async def wait_for_ack(self, **kwargs):
            return HumanInputResult(status=ack_status)

    monkeypatch.setattr(agent_loop, "HumanInputController", lambda: _FakeHumanInput())
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _preview(*args, **kwargs):
        if preview_exception is not None:
            raise preview_exception
        if preview_result is not None:
            return preview_result
        return {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        }

    def _complete(*args, **kwargs):
        if complete_exception is not None:
            raise complete_exception
        if complete_result is not None:
            return complete_result
        return {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        }

    def _fail(*args, **kwargs):
        raise AssertionError("query-only clarification flow should not call profile/registry helpers")

    async def _legacy_resume(*args, **kwargs):
        called["legacy_resume"] = True
        yield {"type": "final", "final_message": "legacy-resume-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "check_data_availability", _fail)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for query-only clarification flow")),
    )
    monkeypatch.setattr(agent_loop, "_run_clarification_resume_legacy", _legacy_resume)
    return session, assistant_before, called


def _setup_query_profile_clarification_resume_baseline(
    monkeypatch,
    *,
    ack_status: str = "approved",
    query_ack_status: str | None = None,
    repair_ack_status: str | None = None,
    repair_execute_exception: Exception | None = None,
    preview_result: dict[str, object] | None = None,
    preview_exception: Exception | None = None,
    complete_result: dict[str, object] | None = None,
    complete_exception: Exception | None = None,
    availability: DataAvailability | None = None,
    post_repair_availability: DataAvailability | None = None,
    modules: list[str] | None = None,
    allow_profile_run: bool = True,
    allow_repair_run: bool = False,
):
    session = create_session(country="mx")
    assistant_before = len([msg for msg in session.messages if msg.role == "assistant"])
    called = {"legacy_resume": False}
    seen_profile_inputs: list[dict[str, object]] = []
    seen_repair_inputs: list[dict[str, object]] = []
    ack_requests: list[dict[str, object]] = []
    ack_status_sequence = [
        query_ack_status or ack_status,
        repair_ack_status or ack_status,
    ]
    active_modules = list(modules or ["app", "behavior"])
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=list(active_modules),
            trace_days=7,
            request_summary="找一批高流失用户并自动画像",
            query_request="找一批高流失用户并自动画像",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort", "profile"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并自动画像",
        }),
    )

    class _FakeHumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            return HumanInputResult(
                status="resolved",
                payload={"country": "mx", "time_window": "最近 7 天", "auto_profile": True},
            )

        async def request_ack(self, **kwargs):
            ack_requests.append(dict(kwargs))
            return HumanInputResult(status="resolved", action="ack_requested")

        async def wait_for_ack(self, **kwargs):
            status = ack_status_sequence.pop(0) if ack_status_sequence else ack_status
            return HumanInputResult(status=status)

    monkeypatch.setattr(agent_loop, "HumanInputController", lambda: _FakeHumanInput())
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _preview(*args, **kwargs):
        if preview_exception is not None:
            raise preview_exception
        if preview_result is not None:
            return preview_result
        return {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        }

    def _complete(*args, **kwargs):
        if complete_exception is not None:
            raise complete_exception
        if complete_result is not None:
            return complete_result
        return {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        }

    def _availability(resolved_uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1 and availability is not None:
            return availability
        if availability_calls["count"] > 1 and post_repair_availability is not None:
            return post_repair_availability
        return _availability_for_rows(
            [(uid, True, True, False) for uid in resolved_uids],
            country=country or "mx",
        )

    def _prepare_repair_query(input_data):
        if not allow_repair_run:
            raise AssertionError("repair_profile_data should not run for this query-profile path")
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {
                    "bucket": input_data.bucket,
                    "uids": list(input_data.uids),
                },
            },
        )()

    def _execute_repair_query(prepared):
        if not allow_repair_run:
            raise AssertionError("execute_repair_query should not run for this query-profile path")
        if repair_execute_exception is not None:
            raise repair_execute_exception
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["bucket"],
                    "requested_uids": list(prepared["uids"]),
                    "written_uids": list(prepared["uids"]),
                    "filenames": [f"{uid}_{prepared['bucket']}.csv" for uid in prepared["uids"]],
                    "sql_text": f"SELECT * FROM {prepared['bucket']}_source",
                    "rows_estimated": len(prepared["uids"]),
                    "rows_actual": len(prepared["uids"]),
                },
            },
        )()

    def _run_profile(input_data, progress_callback=None):
        if not allow_profile_run:
            raise AssertionError("run_profile should not run for this query-profile path")
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "RunProfileOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "results": [
                        {
                            "uid": uid,
                            "module": module,
                            "result": {
                                "status": "ok",
                                "data": {
                                    "summary": f"{uid}-{module}-ok",
                                    "structured_result": {"uid": uid, "module": module},
                                },
                            },
                        }
                        for uid in (input_data.uids or [])
                        for module in (input_data.modules or [])
                    ],
                    "cache_hits": 0,
                    "cache_misses": len((input_data.uids or [])) * len((input_data.modules or [])),
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("query-profile clarification flow should not call legacy registry path")

    async def _legacy_resume(*args, **kwargs):
        called["legacy_resume"] = True
        yield {"type": "final", "final_message": "legacy-resume-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)
    monkeypatch.setattr(agent_loop, "check_data_availability", _availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _run_profile)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "_run_clarification_resume_legacy", _legacy_resume)
    return session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, ack_requests


def _setup_first_turn_query_profile_baseline(
    monkeypatch,
    *,
    ack_status: str = "approved",
    query_ack_status: str | None = None,
    repair_ack_status: str | None = None,
    repair_execute_exception: Exception | None = None,
    preview_result: dict[str, object] | None = None,
    preview_exception: Exception | None = None,
    complete_result: dict[str, object] | None = None,
    complete_exception: Exception | None = None,
    availability: DataAvailability | None = None,
    post_repair_availability: DataAvailability | None = None,
    modules: list[str] | None = None,
    allow_profile_run: bool = True,
    allow_repair_run: bool = False,
    seen_query_requests: list[tuple[str, str]] | None = None,
    seen_ack_requests: list[dict[str, object]] | None = None,
    seen_completed_sql_texts: list[str] | None = None,
):
    session = create_session(country="mx")
    assistant_before = len([msg for msg in session.messages if msg.role == "assistant"])
    called = {"legacy": False}
    seen_profile_inputs: list[dict[str, object]] = []
    seen_repair_inputs: list[dict[str, object]] = []
    ack_requests: list[dict[str, object]] = []
    ack_status_sequence = [
        query_ack_status or ack_status,
        repair_ack_status or ack_status,
    ]
    active_modules = list(modules or ["app", "behavior"])
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=list(active_modules),
            trace_days=7,
            request_summary="查询 cohort 并画像",
            query_request="找墨西哥最近 7 天高流失用户并自动画像",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )

    class _FakeHumanInput:
        async def request_resolution(self, **kwargs):
            raise AssertionError("first-turn query_data_then_profile should not request clarification")

        async def wait_for_resolution(self, **kwargs):
            raise AssertionError("first-turn query_data_then_profile should not wait for clarification")

        async def request_ack(self, **kwargs):
            ack_requests.append(dict(kwargs))
            if seen_ack_requests is not None:
                seen_ack_requests.append(dict(kwargs))
            return HumanInputResult(status="resolved", action="ack_requested")

        async def wait_for_ack(self, **kwargs):
            status = ack_status_sequence.pop(0) if ack_status_sequence else ack_status
            return HumanInputResult(status=status)

    monkeypatch.setattr(agent_loop, "HumanInputController", lambda: _FakeHumanInput())
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _preview(*args, **kwargs):
        if seen_query_requests is not None:
            seen_query_requests.append((args[1], args[2]))
        if preview_exception is not None:
            raise preview_exception
        if preview_result is not None:
            return preview_result
        return {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        }

    def _complete(*args, **kwargs):
        if seen_completed_sql_texts is not None and len(args) >= 3:
            seen_completed_sql_texts.append(str(args[2]))
        if complete_exception is not None:
            raise complete_exception
        if complete_result is not None:
            return complete_result
        return {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        }

    def _availability(resolved_uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1 and availability is not None:
            return availability
        if availability_calls["count"] > 1 and post_repair_availability is not None:
            return post_repair_availability
        return _availability_for_rows(
            [(uid, True, True, True) for uid in resolved_uids],
            country=country or "mx",
        )

    def _prepare_repair_query(input_data):
        if not allow_repair_run:
            raise AssertionError("repair_profile_data should not run for this first-turn path")
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {
                    "bucket": input_data.bucket,
                    "uids": list(input_data.uids),
                },
            },
        )()

    def _execute_repair_query(prepared):
        if not allow_repair_run:
            raise AssertionError("execute_repair_query should not run for this first-turn path")
        if repair_execute_exception is not None:
            raise repair_execute_exception
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["bucket"],
                    "requested_uids": list(prepared["uids"]),
                    "written_uids": list(prepared["uids"]),
                    "filenames": [f"{uid}_{prepared['bucket']}.csv" for uid in prepared["uids"]],
                    "sql_text": f"SELECT * FROM {prepared['bucket']}_source",
                    "rows_estimated": len(prepared["uids"]),
                    "rows_actual": len(prepared["uids"]),
                },
            },
        )()

    def _run_profile(input_data, progress_callback=None):
        if not allow_profile_run:
            raise AssertionError("run_profile should not run for this first-turn path")
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "RunProfileOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "results": [
                        {
                            "uid": uid,
                            "module": module,
                            "result": {
                                "status": "ok",
                                "data": {
                                    "summary": f"{uid}-{module}-ok",
                                    "structured_result": {"uid": uid, "module": module},
                                },
                            },
                        }
                        for uid in (input_data.uids or [])
                        for module in (input_data.modules or [])
                    ],
                    "cache_hits": 0,
                    "cache_misses": len((input_data.uids or [])) * len((input_data.modules or [])),
                },
            },
        )()

    def _fail_registry(*args, **kwargs):
        raise AssertionError("first-turn query_data_then_profile flow should not call legacy registry path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        raise AssertionError("first-turn query_data_then_profile should not fall back to legacy _run_known_request")
        yield {}

    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)
    monkeypatch.setattr(agent_loop, "check_data_availability", _availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _run_profile)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    return session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, ack_requests


def _assert_no_clarify_scope(events):
    assert not any(
        step["step_id"] == "clarify_scope"
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_no_ack_completed_runs_profile(monkeypatch):
    seen_query_requests: list[tuple[str, str]] = []
    session, assistant_before, called, seen_profile_inputs, _, ack_requests = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        preview_result={
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 2,
            "sql_text": "SELECT uid FROM t",
        },
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, True)],
        ),
        seen_query_requests=seen_query_requests,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert review_evt["status"] == "pass"
    assert not any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "query_data" for evt in events)
    assert any(evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data" for evt in events)
    assert any(
        evt["type"] == "plan_step_status"
        and evt.get("step_id") == "check_data"
        and evt.get("status") == "done"
        for evt in events
    )
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert seen_profile_inputs
    assert not ack_requests
    assert seen_query_requests == [(
        "找墨西哥最近 7 天高流失用户并自动画像\n\n[Normalized query hints]\ncountry: mx\ntime_window: last_7_days\nquery_mode: query_profile\nauto_profile: true",
        "mx",
    )]


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_prefers_flow_country_over_normalized_country(monkeypatch):
    seen_query_requests: list[tuple[str, str]] = []
    session, _, called, seen_profile_inputs, _, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        seen_query_requests=seen_query_requests,
    )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.flows.query_data_then_profile.normalize_query_request",
        lambda **kwargs: NormalizedQueryRequest(
            original_text=kwargs["request_text"],
            effective_request_text="normalized query profile request",
            country="th",
            time_window_key=None,
            time_window_label=None,
            query_mode="query_profile",
            auto_profile=True,
            filters_summary=[],
            warnings=[],
        ),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())

    assert called["legacy"] is False
    assert seen_profile_inputs
    assert [evt["type"] for evt in events].count("final") == 1
    assert seen_query_requests == [("normalized query profile request", "mx")]


@pytest.mark.timeout(3)
@pytest.mark.parametrize("ack_status", ["rejected", "expired", "cancelled"])
def test_run_agent_loop_query_data_then_profile_first_turn_query_non_approved_cancels_without_final(monkeypatch, ack_status):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        ack_status=ack_status,
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert not any(evt["type"] == "review_result" for evt in events)
    assert not any(evt["type"] == "final" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert assistant_after == assistant_before
    assert run.pending_ack is None
    assert run.status == "cancelled"
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_multi_bucket_missing_blocks_without_repair(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, False, False), ("u2", True, False, False)],
        ),
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert review_evt["status"] == "fail"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(
        step["step_id"].startswith("repair_")
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs
    assert not seen_repair_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_blocked_unavailable_stops_before_profile(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        availability=_availability_for_rows(
            [("u1", False, False, False), ("u2", False, False, False)],
        ),
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_blocked = next(
        evt
        for evt in events
        if evt["type"] == "plan_step_status"
        and evt.get("step_id") == "run_profile"
        and evt.get("status") == "blocked"
    )

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert review_evt["status"] == "fail"
    assert run_profile_blocked["status"] == "blocked"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_single_bucket_repair_runs_approved_success_path(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, ack_requests = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        post_repair_availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, True)],
        ),
        allow_repair_run=True,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    repair_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data")
    repair_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data")
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert review_evt["status"] == "pass"
    assert events.index(repair_completed) < events.index(run_profile_started)
    assert repair_started["input"]["uids"] == ["u2"]
    assert repair_started["input"]["bucket"] == "credit"
    assert seen_repair_inputs == [
        {
            "uids": ["u2"],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert seen_profile_inputs == [
        {
            "uids": ["u1", "u2"],
            "app_time": None,
            "modules": ["app", "behavior", "credit"],
            "strict_data_mode": True,
        },
    ]
    assert len(ack_requests) == 2
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_repair_rejected_cancels_without_final(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        allow_profile_run=False,
        allow_repair_run=True,
        query_ack_status="approved",
        repair_ack_status="rejected",
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert len([evt for evt in events if evt["type"] == "awaiting_user_ack"]) == 2
    assert not any(evt["type"] == "review_result" for evt in events)
    assert not any(evt["type"] == "final" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert assistant_after == assistant_before
    assert run.pending_ack is None
    assert run.status == "cancelled"
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)
    assert seen_repair_inputs
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_repair_failure_enters_terminal_fail(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        allow_profile_run=False,
        allow_repair_run=True,
        repair_execute_exception=RuntimeError("repair exploded"),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    repair_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert repair_completed["status"] == "error"
    assert review_evt["status"] == "fail"
    assert "tool_error" in {issue["type"] for issue in review_evt["issues"]}
    assert not any(evt["type"] == "run_cancelled" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert seen_repair_inputs
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_post_repair_partial_runs_partial_profile(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        post_repair_availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, False, False)],
        ),
        allow_profile_run=True,
        allow_repair_run=True,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    repair_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data")
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert events.index(repair_completed) < events.index(run_profile_started)
    assert review_evt["status"] == "warning"
    assert {issue["type"] for issue in review_evt["issues"]} >= {"data_acquisition_unavailable", "partial_repair"}
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert seen_repair_inputs
    assert seen_profile_inputs == [
        {
            "uids": ["u1"],
            "app_time": None,
            "modules": ["app", "behavior", "credit"],
            "strict_data_mode": True,
        },
        {
            "uids": ["u2"],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_query_failure_returns_fail_final(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        preview_exception=RuntimeError("preview boom"),
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert review_evt["status"] == "fail"
    assert "tool_error" in {issue["type"] for issue in review_evt["issues"]}
    assert not any(evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_empty_cohort_blocks_before_check_data(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        complete_result={
            "uids": [],
            "rows_actual": 0,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        },
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert review_evt["status"] == "fail"
    assert "empty_cohort" in {issue["type"] for issue in review_evt["issues"]}
    assert "没有可继续画像的 UID" in final_evt["final_message"]
    assert "不会启动画像分析" in final_evt["final_message"]
    assert "放宽筛选条件" in final_evt["final_message"]
    assert not any(evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_query_data_then_profile_first_turn_large_cohort_blocks_before_check_data(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_first_turn_query_profile_baseline(
        monkeypatch,
        complete_result={
            "uids": [f"u{i:03d}" for i in range(201)],
            "rows_actual": 201,
            "rows_estimated": 201,
            "sql_text": "SELECT uid FROM t",
        },
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找墨西哥最近 7 天高流失用户并分析", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy"] is False
    _assert_no_clarify_scope(events)
    assert review_evt["status"] == "fail"
    assert "cohort_too_large" in {issue["type"] for issue in review_evt["issues"]}
    assert "缩小范围" in final_evt["final_message"]
    assert not any(evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_false_uses_query_data_flow_and_skips_legacy_resume(monkeypatch):
    session = create_session(country="mx")
    assistant_before = len([msg for msg in session.messages if msg.role == "assistant"])
    called = {"legacy_resume": False}
    ack_requests: list[dict[str, object]] = []
    completed_sql_texts: list[str] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=["app", "behavior"],
            trace_days=7,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并分析",
        }),
    )

    class _FakeHumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            return HumanInputResult(
                status="resolved",
                payload={"country": "mx", "time_window": "最近 7 天", "auto_profile": False},
            )

        async def request_ack(self, **kwargs):
            ack_requests.append(dict(kwargs))
            return HumanInputResult(status="resolved", action="ack_requested")

        async def wait_for_ack(self, **kwargs):
            return HumanInputResult(status="approved")

    monkeypatch.setattr(agent_loop, "HumanInputController", lambda: _FakeHumanInput())
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_query_data_cohort",
        lambda *args, **kwargs: {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        },
    )
    monkeypatch.setattr(
        agent_loop,
        "_complete_query_data_cohort",
        lambda *args, **kwargs: (
            completed_sql_texts.append(str(args[2])),
            {
                "uids": ["u1", "u2"],
                "rows_actual": 2,
                "rows_estimated": 5,
                "sql_text": "SELECT uid FROM t",
            },
        )[-1],
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when auto_profile=false")),
    )
    def _fail():
        raise AssertionError("get_tool_registry should not be called for query-only clarification flow")

    async def _legacy_resume(*args, **kwargs):
        called["legacy_resume"] = True
        yield {"type": "final", "final_message": "legacy-resume-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "_run_clarification_resume_legacy", _legacy_resume)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    awaiting_evt = next(evt for evt in events if evt["type"] == "awaiting_user_ack")

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "pass"
    assert not review_evt["issues"]
    assert "如需继续画像" in final_evt["final_message"]
    assert "UID 数量" in final_evt["final_message"]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert not any(
        step["step_id"] == "check_data"
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )
    assert [evt["type"] for evt in events].count("awaiting_user_ack") == 1
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert "查询摘要" in awaiting_evt["sql_text"]
    assert "筛选条件" in awaiting_evt["sql_text"]
    assert "确认提示" in awaiting_evt["sql_text"]
    assert "原始 SQL" in awaiting_evt["sql_text"]
    assert "SELECT uid FROM t" in awaiting_evt["sql_text"]
    assert ack_requests and ack_requests[0]["sql_text"] == awaiting_evt["sql_text"]
    assert completed_sql_texts == ["SELECT uid FROM t"]
    assert run.pending_ack is None
    assert run.status == "completed"
    assert session.tool_calls
    assert session.tool_calls[0].tool_name == "query_data"
    assert session.tool_calls[0].status == "done"


@pytest.mark.timeout(3)
@pytest.mark.parametrize("ack_status", ["rejected", "expired", "cancelled"])
def test_run_agent_loop_clarification_auto_profile_false_non_approved_cancels_without_final(monkeypatch, ack_status):
    session = create_session(country="mx")
    assistant_before = len([msg for msg in session.messages if msg.role == "assistant"])
    called = {"legacy_resume": False}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=["app"],
            trace_days=7,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并分析",
        }),
    )

    class _FakeHumanInput:
        async def request_resolution(self, **kwargs):
            return HumanInputResult(status="resolved", action="resolution_requested")

        async def wait_for_resolution(self, **kwargs):
            return HumanInputResult(
                status="resolved",
                payload={"country": "mx", "time_window": "最近 7 天", "auto_profile": False},
            )

        async def request_ack(self, **kwargs):
            return HumanInputResult(status="resolved", action="ack_requested")

        async def wait_for_ack(self, **kwargs):
            return HumanInputResult(status=ack_status)

    monkeypatch.setattr(agent_loop, "HumanInputController", lambda: _FakeHumanInput())
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_query_data_cohort",
        lambda *args, **kwargs: {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        },
    )
    monkeypatch.setattr(
        agent_loop,
        "_complete_query_data_cohort",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("complete should not run for non-approved path")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for non-approved query-only path")),
    )

    async def _legacy_resume(*args, **kwargs):
        called["legacy_resume"] = True
        yield {"type": "final", "final_message": "legacy-resume-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_clarification_resume_legacy", _legacy_resume)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]

    assert called["legacy_resume"] is False
    assert any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert not any(evt["type"] == "review_result" for evt in events)
    assert not any(evt["type"] == "final" for evt in events)
    assert assistant_after == assistant_before
    assert run.pending_ack is None
    assert run.status == "cancelled"
    assert session.tool_calls
    assert session.tool_calls[0].tool_name == "query_data"
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": ack_status, "executed": False}


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_false_preview_failure_returns_fail_final(monkeypatch):
    session, assistant_before, called = _setup_query_only_clarification_resume_baseline(
        monkeypatch,
        preview_exception=RuntimeError("preview boom"),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_completed = next(
        evt for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data"
    )

    assert called["legacy_resume"] is False
    assert query_completed["status"] == "error"
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "tool_error" for issue in review_evt["issues"])
    assert [evt["type"] for evt in events].count("final") == 1
    assert not any(evt["type"] == "run_cancelled" for evt in events)
    assert not any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert not any(
        step["step_id"] == "check_data"
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )
    assert assistant_after - assistant_before == 1
    assert run.pending_ack is None
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)
    assert "请调整取数条件" in final_evt["final_message"]


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_false_execute_failure_returns_fail_final(monkeypatch):
    session, assistant_before, called = _setup_query_only_clarification_resume_baseline(
        monkeypatch,
        complete_exception=RuntimeError("complete boom"),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    query_completed = next(
        evt for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data"
    )

    assert called["legacy_resume"] is False
    assert any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert query_completed["status"] == "error"
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "tool_error" for issue in review_evt["issues"])
    assert [evt["type"] for evt in events].count("final") == 1
    assert not any(evt["type"] == "run_cancelled" for evt in events)
    assert assistant_after - assistant_before == 1
    assert run.pending_ack is None
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_false_empty_cohort_returns_query_only_final(monkeypatch):
    session, assistant_before, called = _setup_query_only_clarification_resume_baseline(
        monkeypatch,
        complete_result={
            "uids": [],
            "rows_actual": 0,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        },
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "pass"
    assert not review_evt["issues"]
    assert "没有命中用户" in final_evt["final_message"]
    assert "UID 数量：0" in final_evt["final_message"]
    assert "UID 列表：无" in final_evt["final_message"]
    assert "放宽筛选条件" in final_evt["final_message"]
    assert [evt["type"] for evt in events].count("final") == 1
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert not any(
        step["step_id"] == "check_data"
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )
    assert assistant_after - assistant_before == 1
    assert run.pending_ack is None
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_false_large_cohort_blocks_with_fail_review(monkeypatch):
    session, assistant_before, called = _setup_query_only_clarification_resume_baseline(
        monkeypatch,
        complete_result={
            "uids": [f"u{i:03d}" for i in range(201)],
            "rows_actual": 201,
            "rows_estimated": 201,
            "sql_text": "SELECT uid FROM t",
        },
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "cohort_too_large" for issue in review_evt["issues"])
    assert "200" in final_evt["final_message"]
    assert [evt["type"] for evt in events].count("final") == 1
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert assistant_after - assistant_before == 1
    assert run.pending_ack is None
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_false_completed_preview_skips_ack_and_returns_query_only_final(monkeypatch):
    session, assistant_before, called = _setup_query_only_clarification_resume_baseline(
        monkeypatch,
        preview_result={
            "uids": ["u1"],
            "rows_actual": 1,
            "rows_estimated": 1,
            "sql_text": "SELECT uid FROM t",
        },
        complete_exception=AssertionError("complete should not run for direct-completed preview"),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_started = [
        evt for evt in events
        if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data"
    ]
    query_completed = [
        evt for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data"
    ]

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "pass"
    assert not any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert len(query_started) == 1
    assert len(query_completed) == 1
    assert query_completed[0]["status"] == "ok"
    assert "UID 数量：1" in final_evt["final_message"]
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert run.pending_ack is None
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_uses_query_profile_flow_and_skips_legacy_resume(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_started = [
        evt for evt in events
        if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data"
    ]
    query_completed = [
        evt for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data"
    ]
    run_profile_started = [
        evt for evt in events
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    ]
    run_profile_completed = [
        evt for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"
    ]

    assert called["legacy_resume"] is False
    assert len(query_started) == 1
    assert len(query_completed) == 1
    assert len(run_profile_started) == 1
    assert len(run_profile_completed) == 1
    assert any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert review_evt["status"] == "pass"
    assert not any(
        issue["type"] in {"data_acquisition_unavailable", "partial_repair", "cohort_too_large", "empty_cohort", "tool_error"}
        for issue in review_evt["issues"]
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert run.pending_ack is None
    assert run.status == "completed"
    assert seen_profile_inputs == [
        {
            "uids": ["u1", "u2"],
            "app_time": None,
            "modules": ["app", "behavior"],
            "strict_data_mode": True,
        }
    ]
    assert "## 执行结果" in final_evt["final_message"]
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_empty_cohort_blocks_without_profile(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        complete_result={
            "uids": [],
            "rows_actual": 0,
            "rows_estimated": 0,
            "sql_text": "SELECT uid FROM t",
        },
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "empty_cohort" for issue in review_evt["issues"])
    assert "没有可继续画像的 UID" in final_evt["final_message"]
    assert "不会启动画像分析" in final_evt["final_message"]
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert not any(
        step["step_id"] == "check_data"
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_large_cohort_blocks_without_profile(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        complete_result={
            "uids": [f"u{i:03d}" for i in range(201)],
            "rows_actual": 201,
            "rows_estimated": 201,
            "sql_text": "SELECT uid FROM t",
        },
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "cohort_too_large" for issue in review_evt["issues"])
    assert "缩小范围" in final_evt["final_message"]
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert not any(
        step["step_id"] == "check_data"
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_blocked_unavailable_stops_before_profile(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, _, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        availability=_availability_for_rows(
            [("u1", False, False, False), ("u2", False, False, False)],
        ),
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    check_data_done = next(
        evt
        for evt in events
        if evt["type"] == "plan_step_status"
        and evt.get("step_id") == "check_data"
        and evt.get("status") == "done"
    )
    run_profile_blocked = next(
        evt
        for evt in events
        if evt["type"] == "plan_step_status"
        and evt.get("step_id") == "run_profile"
        and evt.get("status") == "blocked"
    )

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "fail"
    assert check_data_done["status"] == "done"
    assert run_profile_blocked["status"] == "blocked"
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert not any(
        evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"
        for evt in events
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_single_bucket_repair_runs_approved_success_path(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, ack_requests = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        post_repair_availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, True)],
        ),
        allow_repair_run=True,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run_record = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    check_data_done = next(
        evt
        for evt in events
        if evt["type"] == "plan_step_status"
        and evt.get("step_id") == "check_data"
        and evt.get("status") == "done"
    )
    repair_started = next(
        evt
        for evt in events
        if evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"
    )
    repair_completed = next(
        evt
        for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    run_profile_started = next(
        evt
        for evt in events
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )
    run_profile_completed = next(
        evt
        for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"
    )
    awaiting_acks = [evt for evt in events if evt["type"] == "awaiting_user_ack"]
    query_tool_call = next(call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "query_data")
    repair_tool_call = next(call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data")
    query_ack = next(evt for evt in awaiting_acks if evt.get("tool_call_id") == query_tool_call.tool_call_id)
    repair_ack = next(evt for evt in awaiting_acks if evt.get("tool_call_id") == repair_tool_call.tool_call_id)

    assert called["legacy_resume"] is False
    assert check_data_done["status"] == "done"
    assert len(awaiting_acks) == 2
    assert events.index(query_ack) < events.index(repair_ack)
    assert events.index(repair_ack) < events.index(repair_completed) < events.index(run_profile_started)
    assert review_evt["status"] == "pass"
    issue_types = {issue["type"] for issue in review_evt["issues"]}
    assert "data_acquisition_unavailable" not in issue_types
    assert "partial_repair" not in issue_types
    assert "repair_ready_not_supported" not in issue_types
    assert "cohort_too_large" not in issue_types
    assert "empty_cohort" not in issue_types
    assert "tool_error" not in issue_types
    assert repair_started["input"]["uids"] == ["u2"]
    assert repair_started["input"]["bucket"] == "credit"
    assert run_profile_started["input"]["uids"] == ["u1", "u2"]
    assert run_profile_started["input"]["strict_data_mode"] is True
    assert run_profile_completed["status"] == "ok"
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert run_record.pending_ack is None
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run_record.run_id)
    assert seen_repair_inputs == [
        {
            "uids": ["u2"],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert seen_profile_inputs == [
        {
            "uids": ["u1", "u2"],
            "app_time": None,
            "modules": ["app", "behavior", "credit"],
            "strict_data_mode": True,
        },
    ]
    assert len(ack_requests) == 2


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_multi_bucket_missing_blocks_without_repair(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, False, False), ("u2", True, False, False)],
        ),
        allow_profile_run=False,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "fail"
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"
        for evt in events
    )
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert not any(
        step["step_id"].startswith("repair_")
        for evt in plan_events
        for step in evt["steps"]
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert not seen_profile_inputs
    assert not seen_repair_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_post_repair_blocked_stops_before_profile(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        post_repair_availability=_availability_for_rows(
            [("u1", False, False, False), ("u2", False, False, False)],
        ),
        allow_profile_run=False,
        allow_repair_run=True,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_blocked = next(
        evt
        for evt in events
        if evt["type"] == "plan_step_status"
        and evt.get("step_id") == "run_profile"
        and evt.get("status") == "blocked"
    )

    assert called["legacy_resume"] is False
    assert review_evt["status"] == "fail"
    assert run_profile_blocked["status"] == "blocked"
    assert any(
        evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
        for evt in events
    )
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert seen_repair_inputs
    assert not seen_profile_inputs


@pytest.mark.parametrize("repair_ack_status", ["rejected", "expired", "cancelled"])
@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_repair_non_approved_cancels_without_final(monkeypatch, repair_ack_status):
    session, _, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        allow_profile_run=False,
        allow_repair_run=True,
        query_ack_status="approved",
        repair_ack_status=repair_ack_status,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    run_record = session.turns[0].runs[0]

    assert called["legacy_resume"] is False
    assert any(
        evt["type"] == "awaiting_user_ack" and evt.get("tool_call_id")
        for evt in events
    )
    assert not any(evt["type"] == "review_result" for evt in events)
    assert not any(evt["type"] == "final" for evt in events)
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run_record.run_id)
    assert seen_repair_inputs
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_repair_failure_enters_terminal_fail(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        allow_profile_run=False,
        allow_repair_run=True,
        repair_execute_exception=RuntimeError("repair exploded"),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    run_record = session.turns[0].runs[0]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    repair_completed = next(
        evt
        for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    repair_failed = next(
        evt
        for evt in events
        if evt["type"] == "plan_step_status"
        and evt.get("step_id") == "repair_credit"
        and evt.get("status") == "failed"
    )

    assert called["legacy_resume"] is False
    assert repair_completed["status"] == "error"
    assert repair_failed["status"] == "failed"
    assert review_evt["status"] == "fail"
    issue_types = {issue["type"] for issue in review_evt["issues"]}
    assert "tool_error" in issue_types
    assert "data_acquisition_unavailable" not in issue_types
    assert "partial_repair" not in issue_types
    assert "cohort_too_large" not in issue_types
    assert not any(evt["type"] == "run_cancelled" for evt in events)
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
        for evt in events
    )
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert run_record.pending_ack is None
    assert run_record.status != "cancelled"
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run_record.run_id)
    assert seen_repair_inputs
    assert not seen_profile_inputs


@pytest.mark.timeout(3)
def test_run_agent_loop_clarification_auto_profile_true_post_repair_partial_runs_partial_profile(monkeypatch):
    session, assistant_before, called, seen_profile_inputs, seen_repair_inputs, _ = _setup_query_profile_clarification_resume_baseline(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        post_repair_availability=_availability_for_rows(
            [("u1", True, True, True), ("u2", True, False, False)],
        ),
        allow_profile_run=True,
        allow_repair_run=True,
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "找一批高流失用户并自动画像", country="mx")]

    events = asyncio.run(collect())
    assistant_after = len([msg for msg in session.messages if msg.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    repair_completed = next(
        evt
        for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    run_profile_started = next(
        evt
        for evt in events
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )
    run_profile_completed = next(
        evt
        for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"
    )

    assert called["legacy_resume"] is False
    assert events.index(repair_completed) < events.index(run_profile_started) < events.index(run_profile_completed)
    assert review_evt["status"] == "warning"
    assert {issue["type"] for issue in review_evt["issues"]} >= {"data_acquisition_unavailable", "partial_repair"}
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1
    assert seen_repair_inputs == [
        {
            "uids": ["u2"],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert seen_profile_inputs == [
        {
            "uids": ["u1"],
            "app_time": None,
            "modules": ["app", "behavior", "credit"],
            "strict_data_mode": True,
        },
        {
            "uids": ["u2"],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]


@pytest.mark.timeout(3)
def test_run_agent_loop_run_trace_flow_skips_legacy_and_persists_single_final(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )

    def _fake_run_trace(input_data):
        seen_inputs.append(input_data.model_dump(mode="json"))
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uid": input_data.uid,
                "status": "ok",
                "events": [],
                "summary": {"churn_story": "轨迹正常"},
            },
        })()

    def _fail_get_tool_registry():
        raise AssertionError("RunTraceFlow must not call get_tool_registry")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_trace", _fake_run_trace)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我分析 UID 824812551379353600 最近 30 天轨迹", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = events[-1]

    assert called["legacy"] is False
    assert seen_inputs == [{"uid": "824812551379353600", "days": 30}]
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1
    assert review_evt["status"] == "pass"
    assert final_evt["type"] == "final"
    assert final_evt["confidence"] == 0.88
    assert "可继续结合左侧画像模块核对关键风险信号。" in final_evt["final_message"]
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_run_trace_flow_failure_keeps_legacy_error_semantics(monkeypatch):
    session = create_session(country="mx")

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )

    def _boom(input_data):
        raise RuntimeError(f"trace boom for {input_data.uid}")

    def _fail_get_tool_registry():
        raise AssertionError("RunTraceFlow must not call get_tool_registry")

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_trace", _boom)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我分析 UID 824812551379353600 最近 7 天轨迹", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]
    tool_completed = next(evt for evt in events if evt["type"] == "tool_completed")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = events[-1]

    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1
    assert tool_completed["status"] == "error"
    assert review_evt["status"] == "fail"
    assert final_evt["confidence"] == 0.0
    assert "请稍后重试或改为查看已有画像模块。" in final_evt["final_message"]
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_run_trace_flow_cancel_after_tool_completion_skips_review_and_final(monkeypatch):
    from app.services.orchestrator_agent.session import request_run_cancel

    session = create_session(country="mx")

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )

    def _cancelled_run_trace(input_data):
        request_run_cancel(session.session_id, session.active_run_id)
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uid": input_data.uid,
                "status": "ok",
                "events": [],
                "summary": {"churn_story": "轨迹正常"},
            },
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_trace", _cancelled_run_trace)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我分析 UID 824812551379353600 最近 7 天轨迹", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]

    assert "run_cancelled" in types
    assert "review_result" not in types
    assert "final" not in types
    assert assistant_after == assistant_before


@pytest.mark.timeout(3)
def test_run_agent_loop_run_trace_without_uid_falls_back_to_legacy(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: None})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="run_trace",
            country="mx",
            uids=[],
            trace_days=7,
            request_summary="分析轨迹",
        ),
    )

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        args[0].final_message = "legacy-final"
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我分析轨迹", country="mx")]

    events = asyncio.run(collect())
    assert called["legacy"] is True
    assert events[-1]["type"] == "final"
    assert events[-1]["final_message"] == "legacy-final"


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_skips_legacy_and_persists_single_final(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid("824812551379353600", app=True, behavior=False, credit=False, country=country or "mx"),
    )

    def _fake_run_profile(input_data, progress_callback=None):
        seen_inputs.append(input_data.model_dump(mode="json"))
        if progress_callback is not None:
            progress_callback(
                {
                    "progress_type": "profile_module_completed",
                    "uid": input_data.uids[0],
                    "module": input_data.modules[0],
                    "status": "ok",
                    "completed": 1,
                    "total": 1,
                }
            )
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": input_data.uids[0],
                        "module": input_data.modules[0],
                        "result": {
                            "status": "ok",
                            "data": {
                                "summary": "app 画像正常",
                                "structured_result": {"risk_level": "low"},
                            },
                        },
                    }
                ],
                "cache_hits": 0,
                "cache_misses": 1,
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("should not be called for ProfileFlow minimal success path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr(agent_loop, "repair_profile_data", _fail)
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=["824812551379353600"],
            modules=["app"],
            request_summary="分析这个 UID 的 app 画像",
        ),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的 app 画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = events[-1]
    tool_started_evt = next(evt for evt in events if evt["type"] == "tool_started")
    trace = session.execution_traces[-1]

    assert called["legacy"] is False
    assert seen_inputs == [{"uids": ["824812551379353600"], "app_time": None, "modules": ["app"], "strict_data_mode": True}]
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1
    assert tool_started_evt["input"]["strict_data_mode"] is True
    assert tool_started_evt["input"]["modules"] == ["app"]
    assert review_evt["status"] == "pass"
    assert final_evt["type"] == "final"
    assert final_evt["confidence"] == 0.89
    assert "可继续追问具体模块或切到左侧 dashboard 查看结构化结果。" in final_evt["final_message"]
    assert assistant_after - assistant_before == 1
    _assert_metadata_includes(trace.internal_metadata, {
        "flow_name": "ProfileFlow",
        "decision_mode": "success",
        "uid_count": 1,
        "country": "mx",
        "execution_group_count": 1,
    })


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_flow_falls_back_to_legacy_when_repair_capability_enabled(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    uid = "824812551379353600"

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: None})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit"],
            request_summary="批量分析这个 UID 的完整画像",
        ),
    )

    def _fail(*args, **kwargs):
        raise AssertionError("ProfileFlow should not run when repair-capable legacy path is required")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        args[0].final_message = "legacy-final"
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    assert called["legacy"] is True
    assert events[-1]["type"] == "final"
    assert events[-1]["final_message"] == "legacy-final"


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_handles_partial_unavailable_without_legacy(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_modules: list[str] = []
    uid = "824812551379353600"

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_by_config"),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )

    def _fake_run_profile(input_data, progress_callback=None):
        seen_modules.extend(input_data.modules or [])
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("should not be called for ProfileFlow unavailable partial path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "repair_profile_data", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    trace = session.execution_traces[-1]

    assert called["legacy"] is False
    assert any("data_acquisition_unavailable" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert not any("repair_credit" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert seen_modules == ["app", "behavior"]
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1
    assert review_evt["status"] == "warning"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])
    assert assistant_after - assistant_before == 1
    _assert_metadata_includes(trace.internal_metadata, {
        "flow_name": "ProfileFlow",
        "decision_mode": "partial_unavailable",
        "uid_count": 1,
        "country": "mx",
        "requested_missing": ["credit"],
        "execution_group_count": 1,
        "capability_enabled": False,
    })


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_blocks_unavailable_without_legacy(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    uid = "824812551379353600"

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=False, behavior=False, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_by_config"),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile should not run for blocked unavailable path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy"] is False
    assert any("data_acquisition_unavailable" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert types.count("tool_started") == 0
    assert types.count("tool_completed") == 0
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])
    assert "请直接提供 UID/UID 文件，或补齐本地 bucket 后重试。" in final_evt["final_message"]
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_repair_ready_runs_approved_success_path(monkeypatch):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    call_order: list[str] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx")
        return _availability_for_uid(uid, app=True, behavior=True, credit=True, country=country or "mx")

    def _fake_prepare_repair_query(input_data):
        assert input_data.uids == [uid]
        assert input_data.bucket == "credit"
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": True},
            },
        )()

    def _fake_execute_repair_query(prepared):
        assert prepared == {"prepared": True}
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        events = []
        async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    tool_starts = [evt for evt in events if evt["type"] == "tool_started"]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed"]
    trace = session.execution_traces[-1]
    repair_step_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "done"
    )

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert any(
        evt["type"] == "execution_plan" and "repair_credit" in [step["step_id"] for step in evt["steps"]]
        for evt in events
    )
    assert event_types.count("awaiting_user_ack") == 1
    assert [evt["tool_name"] for evt in tool_starts] == ["repair_profile_data", "run_profile"]
    assert [evt["tool_name"] for evt in tool_completed] == ["repair_profile_data", "run_profile"]
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]
    assert repair_step_done["tool_call_id"]
    assert seen_profile_inputs == [
        {
            "uids": [uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        }
    ]
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1
    _assert_metadata_includes(trace.internal_metadata, {
        "flow_name": "ProfileFlow",
        "decision_mode": "repair_ready",
        "uid_count": 1,
        "country": "mx",
        "requested_missing": ["credit"],
        "repair_buckets": ["credit"],
        "execution_group_count": 1,
        "capability_enabled": True,
    })


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_single_bucket_repair_ready_runs_approved_success_path(monkeypatch):
    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    call_order: list[str] = []
    seen_repair_inputs: list[dict[str, object]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, repair_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (repair_uid, True, True, False),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (repair_uid, True, True, True),
            ],
            country=country or "mx",
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        assert input_data.bucket == "credit"
        assert input_data.uids == [repair_uid]
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fake_execute_repair_query(prepared):
        assert prepared == {"prepared": "credit"}
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [repair_uid],
                    "written_uids": [repair_uid],
                    "filenames": [f"{repair_uid}_credit.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        events = []
        async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    tool_starts = [evt for evt in events if evt["type"] == "tool_started"]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed"]
    repair_completed_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    run_profile_started_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert any(
        evt["type"] == "execution_plan" and "repair_credit" in [step["step_id"] for step in evt["steps"]]
        for evt in events
    )
    assert event_types.count("awaiting_user_ack") == 1
    assert [evt["tool_name"] for evt in tool_starts] == ["repair_profile_data", "run_profile"]
    assert [evt["tool_name"] for evt in tool_completed] == ["repair_profile_data", "run_profile"]
    assert repair_completed_index < run_profile_started_index
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]
    assert seen_repair_inputs == [
        {
            "uids": [repair_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert seen_profile_inputs == [
        {
            "uids": [full_uid, repair_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        }
    ]
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_multi_uid_single_bucket_repair_ready_runs_approved_success_path(monkeypatch):
    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    call_order: list[str] = []
    seen_repair_inputs: list[dict[str, object]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[full_uid, repair_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (repair_uid, True, True, False),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (repair_uid, True, True, True),
            ],
            country=country or "mx",
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        assert input_data.bucket == "credit"
        assert input_data.uids == [repair_uid]
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fake_execute_repair_query(prepared):
        assert prepared == {"prepared": "credit"}
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [repair_uid],
                    "written_uids": [repair_uid],
                    "filenames": [f"{repair_uid}_credit.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        events = []
        async for evt in agent_loop.run_agent_loop(session, "分析这两个 UID 的完整画像", country="mx"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    tool_starts = [evt for evt in events if evt["type"] == "tool_started"]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed"]
    repair_completed_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    run_profile_started_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert event_types.count("awaiting_user_ack") == 1
    assert [evt["tool_name"] for evt in tool_starts] == ["repair_profile_data", "run_profile"]
    assert [evt["tool_name"] for evt in tool_completed] == ["repair_profile_data", "run_profile"]
    assert repair_completed_index < run_profile_started_index
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]
    assert seen_repair_inputs == [
        {
            "uids": [repair_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert seen_profile_inputs == [
        {
            "uids": [full_uid, repair_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        }
    ]
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_two_bucket_repair_ready_runs_approved_success_path(monkeypatch):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    call_order: list[str] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_uid(uid, app=True, behavior=False, credit=False, country=country or "mx")
        return _availability_for_uid(uid, app=True, behavior=True, credit=True, country=country or "mx")

    def _fake_prepare_repair_query(input_data):
        assert input_data.uids == [uid]
        assert input_data.bucket in {"behavior", "credit"}
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        assert prepared in ({"prepared": "behavior"}, {"prepared": "credit"})
        bucket = prepared["prepared"]
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        events = []
        async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    repair_tool_starts = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    run_profile_starts = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"]
    run_profile_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"]
    repair_behavior_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_behavior" and evt["status"] == "done"
    )
    repair_credit_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "done"
    )
    awaiting_indices = [idx for idx, evt in enumerate(events) if evt["type"] == "awaiting_user_ack"]
    repair_completed_indices = [
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    ]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert any(
        evt["type"] == "execution_plan"
        and {"repair_behavior", "repair_credit"}.issubset({step["step_id"] for step in evt["steps"]})
        for evt in events
    )
    assert event_types.count("awaiting_user_ack") == 2
    assert len(repair_tool_starts) == 2
    assert len(repair_tool_completed) == 2
    assert len(run_profile_starts) == 1
    assert len(run_profile_completed) == 1
    assert awaiting_indices[0] < repair_completed_indices[0] < awaiting_indices[1] < repair_completed_indices[1]
    assert call_order[:6] == ["open_ack", "awaiting_user_ack", "wait_ack", "open_ack", "awaiting_user_ack", "wait_ack"]
    assert repair_behavior_done["tool_call_id"]
    assert repair_credit_done["tool_call_id"]
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert seen_profile_inputs == [
        {
            "uids": [uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        }
    ]
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_mixed_bucket_repair_ready_runs_approved_success_path(monkeypatch):
    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    call_order: list[str] = []
    seen_repair_inputs: list[dict[str, object]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这三个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (credit_uid, True, True, False),
                    (behavior_uid, True, False, True),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (credit_uid, True, True, True),
                (behavior_uid, True, True, True),
            ],
            country=country or "mx",
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        events = []
        async for evt in agent_loop.run_agent_loop(session, "批量分析这三个 UID 的完整画像", country="mx"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    tool_starts = [evt for evt in events if evt["type"] == "tool_started"]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    first_repair_completed_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    second_ack_index = [idx for idx, evt in enumerate(events) if evt["type"] == "awaiting_user_ack"][1]
    second_repair_completed_index = [
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    ][1]
    run_profile_started_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert any(
        evt["type"] == "execution_plan"
        and {"repair_credit", "repair_behavior"}.issubset({step["step_id"] for step in evt["steps"]})
        for evt in events
    )
    assert event_types.count("awaiting_user_ack") == 2
    assert [evt["tool_name"] for evt in tool_starts] == ["repair_profile_data", "repair_profile_data", "run_profile"]
    assert [evt["tool_name"] for evt in tool_completed] == ["repair_profile_data", "repair_profile_data", "run_profile"]
    assert first_repair_completed_index < second_ack_index < second_repair_completed_index < run_profile_started_index
    assert call_order[:6] == ["open_ack", "awaiting_user_ack", "wait_ack", "open_ack", "awaiting_user_ack", "wait_ack"]
    assert seen_repair_inputs == [
        {
            "uids": [credit_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        },
        {
            "uids": [behavior_uid],
            "country": "mx",
            "bucket": "behavior",
            "reason": "behavior bucket 缺失，需继续执行画像",
        },
    ]
    assert seen_profile_inputs == [
        {
            "uids": [full_uid, credit_uid, behavior_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive"],
            "strict_data_mode": True,
        }
    ]
    assert review_evt["status"] == "pass"
    assert not any(issue["type"] in {"data_acquisition_unavailable", "partial_repair"} for issue in review_evt["issues"])
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_multi_uid_mixed_bucket_repair_ready_runs_approved_success_path(monkeypatch):
    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    call_order: list[str] = []
    seen_repair_inputs: list[dict[str, object]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[full_uid, credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这三个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (credit_uid, True, True, False),
                    (behavior_uid, True, False, True),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (credit_uid, True, True, True),
                (behavior_uid, True, True, True),
            ],
            country=country or "mx",
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected legacy/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        events = []
        async for evt in agent_loop.run_agent_loop(session, "批量分析这三个 UID 的完整画像", country="mx"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert any(
        evt["type"] == "execution_plan"
        and {"repair_credit", "repair_behavior", "run_profile"}.issubset({step["step_id"] for step in evt["steps"]})
        for evt in events
    )
    assert event_types.count("awaiting_user_ack") == 2
    assert seen_repair_inputs == [
        {
            "uids": [credit_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        },
        {
            "uids": [behavior_uid],
            "country": "mx",
            "bucket": "behavior",
            "reason": "behavior bucket 缺失，需继续执行画像",
        },
    ]
    assert seen_profile_inputs == [
        {
            "uids": [full_uid, credit_uid, behavior_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive"],
            "strict_data_mode": True,
        }
    ]
    assert review_evt["status"] == "pass"
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1
    assert call_order[:6] == ["open_ack", "awaiting_user_ack", "wait_ack", "open_ack", "awaiting_user_ack", "wait_ack"]


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_mixed_bucket_repair_stops_before_second_repair_when_first_repair_fails(monkeypatch):
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}
    execute_calls: list[str] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (credit_uid, True, True, False),
                (behavior_uid, True, False, True),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )(),
    )

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        raise PermissionError(f"{bucket} repair failed")

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for first mixed repair failure")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    repair_tool_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert execute_calls == ["credit"]
    assert event_types.count("awaiting_user_ack") == 1
    assert len(repair_tool_started) == 1
    assert len(repair_tool_completed) == 1
    assert repair_tool_completed[0]["status"] == "error"
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_mixed_bucket_repair_stops_before_run_profile_when_second_repair_fails(monkeypatch):
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}
    execute_calls: list[str] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (credit_uid, True, True, False),
                (behavior_uid, True, False, True),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )(),
    )

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        if bucket == "behavior":
            raise PermissionError("behavior repair failed")
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for second mixed repair failure")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert execute_calls == ["credit", "behavior"]
    assert len(repair_tool_completed) == 2
    assert repair_tool_completed[0]["status"] == "ok"
    assert repair_tool_completed[1]["status"] == "error"
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_mixed_bucket_first_repair_rejected_does_not_enter_run_profile(monkeypatch):
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (credit_uid, True, True, False),
                (behavior_uid, True, False, True),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )(),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for rejected first repair")),
    )

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for rejected first mixed repair")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: False)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert event_types.count("awaiting_user_ack") == 1
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_profile_batch_mixed_bucket_second_repair_non_approved_does_not_enter_run_profile(monkeypatch, ack_value, wait_path):
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}
    execute_calls: list[str] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (credit_uid, True, True, False),
                (behavior_uid, True, False, True),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )(),
    )

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for second non-approved mixed repair")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)

    ack_counter = {"count": 0}
    if wait_path == "ack_bus":
        def _wait_ack(sid, timeout_sec=600.0):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return True
            return ack_value

        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", _wait_ack)
    else:
        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return HumanInputResult(status="approved")
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert execute_calls == ["credit"]
    assert event_types.count("awaiting_user_ack") == 2
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_mixed_bucket_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["behavior", "credit"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        return _availability_for_rows(
            [
                (credit_uid, True, False, False),
                (behavior_uid, True, False, False),
            ],
            country=country or "mx",
        )

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(
        agent_loop,
        "prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )(),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [credit_uid if prepared["prepared"] == "credit" else behavior_uid],
                    "written_uids": [credit_uid if prepared["prepared"] == "credit" else behavior_uid],
                    "filenames": [f"{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for mixed still-unavailable path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_mixed_bucket_repair_partial_unavailable_runs_partial_profile(monkeypatch):
    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    seen_repair_inputs: list[dict[str, object]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这三个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (credit_uid, True, True, False),
                    (behavior_uid, True, False, True),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (credit_uid, True, True, True),
                (behavior_uid, True, False, True),
            ],
            country=country or "mx",
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(input_data.uids) * len(input_data.modules or [])},
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected legacy/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这三个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert seen_repair_inputs == [
        {
            "uids": [credit_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        },
        {
            "uids": [behavior_uid],
            "country": "mx",
            "bucket": "behavior",
            "reason": "behavior bucket 缺失，需继续执行画像",
        },
    ]
    assert seen_profile_inputs
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "warning"
    assert {issue["type"] for issue in review_evt["issues"]} >= {"data_acquisition_unavailable", "partial_repair"}
    assert event_types.count("final") == 1
    assert ("部分" in final_evt["final_message"]) or ("降级" in final_evt["final_message"])
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_single_bucket_repair_partial_unavailable_runs_partial_profile(monkeypatch):
    full_uid = "824812551379353600"
    partial_uid = "824812551379353601"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    seen_repair_inputs: list[dict[str, object]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, partial_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (partial_uid, True, True, False),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (partial_uid, True, False, False),
            ],
            country=country or "mx",
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        assert input_data.bucket == "credit"
        assert input_data.uids == [partial_uid]
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fake_execute_repair_query(prepared):
        assert prepared == {"prepared": "credit"}
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [partial_uid],
                    "written_uids": [partial_uid],
                    "filenames": [f"{partial_uid}_credit.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert seen_repair_inputs == [
        {
            "uids": [partial_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert seen_profile_inputs == [
        {
            "uids": [full_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        },
        {
            "uids": [partial_uid],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]
    assert not any(
        evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" and evt.get("input", {}).get("uids") == [full_uid, partial_uid]
        for evt in events
    )
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "warning"
    issue_types = {issue.get("type") for issue in review_evt["issues"]}
    assert "data_acquisition_unavailable" in issue_types
    assert "partial_repair" in issue_types
    assert event_types.count("final") == 1
    assert ("部分" in final_evt["final_message"]) or ("降级" in final_evt["final_message"])
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_multi_uid_single_bucket_repair_partial_unavailable_runs_partial_profile(monkeypatch):
    full_uid = "824812551379353600"
    partial_uid = "824812551379353601"
    session = create_session(country="mx")
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[full_uid, partial_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    availability_calls = {"count": 0}

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (partial_uid, True, True, False),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (partial_uid, True, False, False),
            ],
            country=country or "mx",
        )

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(
        agent_loop,
        "prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )(),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [partial_uid],
                    "written_uids": [partial_uid],
                    "filenames": [f"{partial_uid}_credit.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("RunProfileOut", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(input_data.uids) * len(input_data.modules or [])},
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这两个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert availability_calls["count"] >= 2
    assert review_evt["status"] == "warning"
    assert seen_profile_inputs == [
        {
            "uids": [full_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        },
        {
            "uids": [partial_uid],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_single_bucket_repair_stops_before_run_profile_when_recheck_not_success(monkeypatch):
    first_uid = "824812551379353600"
    second_uid = "824812551379353601"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    seen_repair_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[first_uid, second_uid],
            modules=["credit"],
            request_summary="批量分析这两个 UID 的 credit 画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (first_uid, True, True, False),
                    (second_uid, True, True, False),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (first_uid, True, True, False),
                (second_uid, True, True, False),
            ],
            country=country or "mx",
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        assert input_data.uids == [first_uid, second_uid]
        assert input_data.bucket == "credit"
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fake_execute_repair_query(prepared):
        assert prepared == {"prepared": "credit"}
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [first_uid, second_uid],
                    "written_uids": [first_uid, second_uid],
                    "filenames": [f"{first_uid}_credit.csv", f"{second_uid}_credit.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 2,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的 credit 画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert seen_repair_inputs == [
        {
            "uids": [first_uid, second_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert "run_cancelled" not in event_types
    assert "run_profile" not in [evt.get("tool_name") for evt in events if evt["type"] in {"tool_started", "tool_completed"}]
    assert event_types.count("final") == 1
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_profile_batch_single_bucket_repair_non_approved_does_not_enter_run_profile(monkeypatch, ack_value, wait_path):
    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_repair_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, repair_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (full_uid, True, True, True),
                (repair_uid, True, True, False),
            ],
            country=country or "mx",
        ),
    )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for batch non-approved repair path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for non-approved ack")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    if wait_path == "ack_bus":
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: ack_value)
    else:
        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]
    run_profile_steps = [
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    ]

    assert called["legacy"] is False
    assert seen_repair_inputs == [
        {
            "uids": [repair_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert "awaiting_user_ack" in event_types
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_steps == []
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_single_bucket_repair_failure_enters_terminal_fail(monkeypatch):
    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_repair_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, repair_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析这两个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (full_uid, True, True, True),
                (repair_uid, True, True, False),
            ],
            country=country or "mx",
        ),
    )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for batch repair failure")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(PermissionError("credit repair failed")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "批量分析这两个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    repair_completed = [
        evt for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    ]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert seen_repair_inputs == [
        {
            "uids": [repair_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert len(repair_completed) == 1
    assert repair_completed[0]["status"] == "error"
    assert "run_cancelled" not in event_types
    assert "data_acquisition_unavailable" not in [evt.get("step_id") for evt in events if evt["type"] == "plan_step_status"]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_two_bucket_repair_stops_before_run_profile_when_second_repair_fails(monkeypatch):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        return _availability_for_uid(uid, app=True, behavior=False, credit=False, country=country or "mx")

    def _fake_prepare_repair_query(input_data):
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    execute_calls: list[str] = []

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        if bucket == "behavior":
            raise PermissionError("behavior repair failed")
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected registry/query path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when second repair fails")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert execute_calls == ["credit", "behavior"]
    assert availability_calls["count"] == 1
    assert len(repair_tool_completed) == 2
    assert repair_tool_completed[0]["status"] == "ok"
    assert repair_tool_completed[1]["status"] == "error"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_two_bucket_repair_stops_before_second_repair_when_first_repair_fails(monkeypatch):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}
    execute_calls: list[str] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        return _availability_for_uid(uid, app=True, behavior=False, credit=False, country=country or "mx")

    def _fake_prepare_repair_query(input_data):
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        raise PermissionError(f"{bucket} repair failed")

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/second repair should not run when first repair fails")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    repair_tool_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert execute_calls == ["credit"]
    assert availability_calls["count"] == 1
    assert event_types.count("awaiting_user_ack") == 1
    assert len(repair_tool_started) == 1
    assert len(repair_tool_completed) == 1
    assert repair_tool_completed[0]["status"] == "error"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_profile_flow_repair_non_approved_does_not_enter_run_profile(monkeypatch, ack_value, wait_path):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": True}},
        )(),
    )
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for non-approved ack")),
    )

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for non-approved repair path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    if wait_path == "ack_bus":
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: ack_value)
    else:
        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert "run_profile" not in [evt.get("tool_name") for evt in events if evt["type"] in {"tool_started", "tool_completed"}]
    assert "awaiting_user_ack" in event_types
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_profile_flow_two_bucket_second_repair_non_approved_does_not_enter_run_profile(monkeypatch, ack_value, wait_path):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}
    execute_calls: list[str] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(uid, app=True, behavior=False, credit=False, country=country or "mx"),
    )

    def _fake_prepare_repair_query(input_data):
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for two-bucket non-approved path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    ack_counter = {"count": 0}
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    if wait_path == "ack_bus":
        def _wait_ack(sid, timeout_sec=600.0):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return True
            return ack_value
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", _wait_ack)
    else:
        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return HumanInputResult(status="approved")
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    events = asyncio.run(collect())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert called["legacy"] is False
    assert execute_calls == ["credit"]
    assert event_types.count("awaiting_user_ack") == 2
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        return _availability_for_uid(uid, app=True, behavior=True, credit=False, country=country or "mx")

    def _fake_prepare_repair_query(input_data):
        return type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": True}},
        )()

    def _fake_execute_repair_query(prepared):
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data should not run when repair recheck still unavailable")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert "run_profile" not in [evt.get("tool_name") for evt in events if evt["type"] in {"tool_started", "tool_completed"}]
    assert event_types.count("final") == 1
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_flow_uses_mixed_uid_execution_groups(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_inputs: list[dict[str, object]] = []
    seen_progress: list[tuple[int, int]] = []
    full_uid = "824812551379353600"
    partial_uid = "824812551379353601"

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (full_uid, True, True, True),
                (partial_uid, True, False, False),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_for_test"),
    )

    def _fake_run_profile(input_data, progress_callback=None):
        seen_inputs.append(input_data.model_dump(mode="json"))
        total = len(input_data.uids) * len(input_data.modules or [])
        for index, module in enumerate(input_data.modules or [], start=1):
            if progress_callback is not None:
                progress_callback(
                    {
                        "progress_type": "profile_module_completed",
                        "uid": input_data.uids[0],
                        "module": module,
                        "status": "ok",
                        "completed": index,
                        "total": total,
                    }
                )
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {
                                "summary": f"{module} 画像正常",
                                "structured_result": {"module": module},
                            },
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": total,
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("should not be called for ProfileFlow batch unavailable-guard path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr(agent_loop, "repair_profile_data", _fail)
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, partial_uid],
            modules=[],
            request_summary="批量分析 2 个 UID",
        ),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我批量分析两个 UID", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]
    for evt in events:
        if evt["type"] == "tool_progress":
            seen_progress.append((int(evt["completed"]), int(evt["total"])))
    tool_started_evt = next(evt for evt in events if evt["type"] == "tool_started")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = events[-1]

    assert called["legacy"] is False
    assert seen_inputs == [
        {
            "uids": [full_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        },
        {
            "uids": [partial_uid],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1
    assert any(
        evt["type"] == "execution_plan"
        and "data_acquisition_unavailable" in [step["step_id"] for step in evt["steps"]]
        for evt in events
    )
    assert tool_started_evt["input"]["strict_data_mode"] is True
    assert tool_started_evt["input"]["modules"] == ["app", "behavior", "credit", "comprehensive", "product", "ops"]
    assert review_evt["status"] == "warning"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])
    assert assistant_after - assistant_before == 1
    assert final_evt["type"] == "final"
    assert all(completed <= total for completed, total in seen_progress)
    assert seen_progress == sorted(seen_progress, key=lambda item: item[0])


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_batch_uid_file_flow_runs_parse_then_single_bucket_repair_when_capability_enabled(monkeypatch):
    session = create_session(country="mx")
    parsed_uids = [
        "824812551379353600",
        "824812551379353601",
        "824812551379353602",
    ]
    repaired_uid = parsed_uids[1]
    availability_calls = {"count": 0}
    seen_prepare_inputs: list[dict[str, object]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (parsed_uids[0], True, True, True),
                    (parsed_uids[1], True, True, False),
                    (parsed_uids[2], True, True, True),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [(uid, True, True, True) for uid in parsed_uids],
            country=country or "mx",
        )

    def _fake_parse_uid_file(input_data):
        assert input_data.file_path == "./data/id_files/mx/sample.txt"
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_prepare_repair_query(input_data):
        seen_prepare_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [repaired_uid],
                    "written_uids": [repaired_uid],
                    "filenames": [f"{repaired_uid}_{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("Result", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("legacy/query/registry path should not run for uid_file repair success")

    monkeypatch.setattr(agent_loop, "check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 ./data/id_files/mx/sample.txt", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    tool_started = [evt for evt in events if evt["type"] == "tool_started"]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed"]
    run_record = session.turns[-1].runs[-1]

    assert len(plan_events) == 2
    assert [evt["tool_name"] for evt in tool_started[:3]] == [
        "parse_uid_file",
        "repair_profile_data",
        "run_profile",
    ]
    assert [evt["tool_name"] for evt in tool_completed[:3]] == [
        "parse_uid_file",
        "repair_profile_data",
        "run_profile",
    ]
    assert seen_prepare_inputs == [
        {
            "uids": [repaired_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert seen_profile_inputs == [
        {
            "uids": parsed_uids,
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        }
    ]
    assert availability_calls["count"] >= 2
    assert run_record.pending_ack is None
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data")
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_flow_runs_parse_then_single_uid_repair_when_capability_enabled(monkeypatch):
    session = create_session(country="mx")
    parsed_uid = "824812551379353600"
    availability_calls = {"count": 0}
    seen_prepare_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析 UID 文件",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_uid(parsed_uid, app=True, behavior=True, credit=False, country=country or "mx")
        return _availability_for_uid(parsed_uid, app=True, behavior=True, credit=True, country=country or "mx")

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": [parsed_uid],
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_prepare_repair_query(input_data):
        seen_prepare_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [parsed_uid],
                    "written_uids": [parsed_uid],
                    "filenames": [f"{parsed_uid}_{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        return type("Result", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": parsed_uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("legacy/query/registry path should not run for uid_file single UID repair success")

    monkeypatch.setattr(agent_loop, "check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 UID 文件", country="mx")]

    events = asyncio.run(collect())
    assert seen_prepare_inputs == [
        {
            "uids": [parsed_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert availability_calls["count"] >= 2
    assert not any(evt["type"] == "review_result" and evt["status"] == "fail" for evt in events)
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_profile_uid_file_batch_repair_non_approved_does_not_enter_run_profile(monkeypatch, ack_value, wait_path):
    session = create_session(country="mx")
    parsed_uids = [
        "824812551379353600",
        "824812551379353601",
        "824812551379353602",
    ]
    repaired_uid = parsed_uids[1]
    seen_prepare_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (parsed_uids[0], True, True, True),
                (parsed_uids[1], True, True, False),
                (parsed_uids[2], True, True, True),
            ],
            country=country or "mx",
        ),
    )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_prepare_repair_query(input_data):
        seen_prepare_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for uid_file non-approved repair path")

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for uid_file non-approved repair path")),
    )
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    if wait_path == "ack_bus":
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: ack_value)
    else:
        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 ./data/id_files/mx/sample.txt", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    parse_tool_completed = [
        evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "parse_uid_file"
    ]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert seen_prepare_inputs == [
        {
            "uids": [repaired_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert len(parse_tool_completed) == 1
    assert "awaiting_user_ack" in event_types
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert assistant_after - assistant_before == 0
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_batch_repair_tool_failure_stops_before_run_profile(monkeypatch):
    session = create_session(country="mx")
    parsed_uids = [
        "824812551379353600",
        "824812551379353601",
        "824812551379353602",
    ]
    repaired_uid = parsed_uids[1]
    seen_prepare_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (parsed_uids[0], True, True, True),
                (parsed_uids[1], True, True, False),
                (parsed_uids[2], True, True, True),
            ],
            country=country or "mx",
        ),
    )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_prepare_repair_query(input_data):
        seen_prepare_inputs.append(input_data.model_dump(mode="json"))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for uid_file repair failure")

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(PermissionError("User rejected SQL execution")),
    )
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 ./data/id_files/mx/sample.txt", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    repair_tool_completed = [
        evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    ]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert seen_prepare_inputs == [
        {
            "uids": [repaired_uid],
            "country": "mx",
            "bucket": "credit",
            "reason": "credit bucket 缺失，需继续执行画像",
        }
    ]
    assert len(repair_tool_completed) == 1
    assert repair_tool_completed[0]["status"] == "error"
    assert "run_cancelled" not in event_types
    assert "data_acquisition_unavailable" not in [
        evt.get("step_id") for evt in events if evt["type"] == "plan_step_status"
    ]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_batch_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    session = create_session(country="mx")
    parsed_uids = [
        "824812551379353600",
        "824812551379353601",
    ]
    availability_calls = {"count": 0}
    seen_prepare_inputs: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=["credit"],
            request_summary="分析 UID 文件",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        return _availability_for_rows(
            [
                (parsed_uids[0], True, True, False),
                (parsed_uids[1], True, True, False),
            ],
            country=country or "mx",
        )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_prepare_repair_query(input_data):
        seen_prepare_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for uid_file still-unavailable repair path")

    monkeypatch.setattr(agent_loop, "check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": parsed_uids,
                    "written_uids": parsed_uids,
                    "filenames": [f"{uid}.csv" for uid in parsed_uids],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": len(parsed_uids),
                    "rows_actual": len(parsed_uids),
                },
            },
        )(),
    )
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 ./data/id_files/mx/sample.txt", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )

    assert availability_calls["count"] >= 2
    assert seen_prepare_inputs == [("credit", parsed_uids)]
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_batch_repair_partial_unavailable_runs_profile(monkeypatch):
    session = create_session(country="mx")
    full_uid = "824812551379353600"
    partial_uid = "824812551379353601"
    parsed_uids = [full_uid, partial_uid]
    availability_calls = {"count": 0}
    seen_prepare_inputs: list[tuple[str, list[str]]] = []
    seen_profile_inputs: list[dict[str, object]] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (partial_uid, True, True, False),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [
                (full_uid, True, True, True),
                (partial_uid, True, False, False),
            ],
            country=country or "mx",
        )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_prepare_repair_query(input_data):
        seen_prepare_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": "SELECT * FROM credit_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": "credit"},
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("Result", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("query_data/legacy should not run for uid_file repair partial path")

    monkeypatch.setattr(agent_loop, "check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        agent_loop,
        "execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [partial_uid],
                    "written_uids": [partial_uid],
                    "filenames": [f"{partial_uid}.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 ./data/id_files/mx/sample.txt", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    run_profile_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"]
    run_profile_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"]

    assert availability_calls["count"] >= 2
    assert seen_prepare_inputs == [("credit", [partial_uid])]
    assert seen_profile_inputs == [
        {
            "uids": [full_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        },
        {
            "uids": [partial_uid],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]
    assert len(run_profile_started) == 1
    assert len(run_profile_completed) == 1
    assert review_evt["status"] == "warning"
    issue_types = {issue.get("type") for issue in review_evt["issues"]}
    assert "data_acquisition_unavailable" in issue_types
    assert "partial_repair" in issue_types
    assert event_types.count("final") == 1
    assert ("部分" in final_evt["final_message"]) or ("降级" in final_evt["final_message"])
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_mixed_bucket_repair_runs_approved_success_path(monkeypatch):
    session = create_session(country="mx")
    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    parsed_uids = [full_uid, credit_uid, behavior_uid]
    availability_calls = {"count": 0}
    seen_prepare_inputs: list[tuple[str, list[str]]] = []
    execute_calls: list[str] = []

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="分析 UID 文件",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return _availability_for_rows(
                [
                    (full_uid, True, True, True),
                    (credit_uid, True, True, False),
                    (behavior_uid, True, False, True),
                ],
                country=country or "mx",
            )
        return _availability_for_rows(
            [(uid, True, True, True) for uid in parsed_uids],
            country=country or "mx",
        )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_prepare_repair_query(input_data):
        seen_prepare_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fake_run_profile(input_data, progress_callback=None):
        return type("Result", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("query_data/legacy should not run for uid_file mixed-bucket success path")

    monkeypatch.setattr(agent_loop, "check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 ./data/id_files/mx/sample.txt", country="mx")]

    events = asyncio.run(collect())
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    second_plan_step_ids = [step["step_id"] for step in plan_events[1]["steps"]]
    repair_tool_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    run_profile_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"]
    run_profile_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"]

    assert len(plan_events) == 2
    assert [step["step_id"] for step in plan_events[0]["steps"]] == ["parse_uid_file"]
    assert "parse_uid_file" not in second_plan_step_ids
    assert {"repair_credit", "repair_behavior", "run_profile", "review_final"}.issubset(set(second_plan_step_ids))
    assert seen_prepare_inputs == [
        ("credit", [credit_uid]),
        ("behavior", [behavior_uid]),
    ]
    assert execute_calls == ["credit", "behavior"]
    assert len(repair_tool_started) == 2
    assert len(repair_tool_completed) == 2
    assert [evt["type"] for evt in events].count("awaiting_user_ack") == 2
    assert len(run_profile_started) == 1
    assert len(run_profile_completed) == 1
    assert [evt["type"] for evt in events].count("final") == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_flow_runs_parse_then_profile_when_capability_disabled(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_profile_inputs: list[dict[str, object]] = []
    parsed_uids = ["824812551379353600", "824812551379353601"]

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_for_test"),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_rows(
            [
                (parsed_uids[0], True, True, True),
                (parsed_uids[1], True, True, True),
            ],
            country=country or "mx",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件",
        ),
    )

    def _fake_parse_uid_file(input_data):
        assert input_data.file_path == "./data/id_files/mx/sample.txt"
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_profile_inputs.append(input_data.model_dump(mode="json"))
        return type("Result", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for uid in input_data.uids
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.uids) * len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected legacy or registry/repair path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "repair_profile_data", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 ./data/id_files/mx/sample.txt", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    tool_starts = [evt["tool_name"] for evt in events if evt["type"] == "tool_started"]
    tool_completed = [evt["tool_name"] for evt in events if evt["type"] == "tool_completed"]
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    parse_running_index = next(index for index, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "parse_uid_file" and evt["status"] == "running")
    parse_done_index = next(index for index, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "parse_uid_file" and evt["status"] == "done")
    first_plan_index = next(index for index, evt in enumerate(events) if evt is plan_events[0])
    second_plan_index = next(index for index, evt in enumerate(events) if evt is plan_events[1])
    second_plan_step_ids = [step["step_id"] for step in plan_events[1]["steps"]]

    assert called["legacy"] is False
    assert len(plan_events) == 2
    assert first_plan_index < parse_running_index
    assert second_plan_index > parse_done_index
    assert "check_data" in second_plan_step_ids
    assert "run_profile" in second_plan_step_ids
    assert "review_final" in second_plan_step_ids
    assert tool_starts[:2] == ["parse_uid_file", "run_profile"]
    assert tool_completed[:2] == ["parse_uid_file", "run_profile"]
    assert seen_profile_inputs == [
        {
            "uids": parsed_uids,
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        }
    ]
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_flow_two_bucket_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    uid = "824812551379353600"
    session = create_session(country="mx")
    called = {"legacy": False}
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析这个 UID 的完整画像",
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )

    def _fake_check_data_availability(uids, country=None):
        availability_calls["count"] += 1
        return _availability_for_uid(uid, app=True, behavior=False, credit=False, country=country or "mx")

    def _fake_prepare_repair_query(input_data):
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data should not run when two-bucket repair recheck still unavailable")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "check_data_availability", _fake_check_data_availability)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID 的完整画像", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )

    assert called["legacy"] is False
    assert availability_calls["count"] >= 2
    assert len(repair_tool_completed) == 2
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_flow_handles_partial_unavailable_when_capability_disabled(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    seen_modules: list[str] = []
    parsed_uids = ["824812551379353600"]

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_by_config"),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(parsed_uids[0], app=True, behavior=True, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析 UID 文件",
        ),
    )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fake_run_profile(input_data, progress_callback=None):
        seen_modules.extend(input_data.modules or [])
        return type("Result", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": parsed_uids[0],
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}},
                        },
                    }
                    for module in (input_data.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(input_data.modules or []),
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected legacy or registry/repair path")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "repair_profile_data", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 UID 文件", country="mx")]

    events = asyncio.run(collect())
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    assert called["legacy"] is False
    assert seen_modules == ["app", "behavior"]
    assert review_evt["status"] == "warning"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])
    assert [evt["tool_name"] for evt in events if evt["type"] == "tool_started"][:2] == ["parse_uid_file", "run_profile"]


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_flow_blocks_unavailable_when_capability_disabled(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}
    parsed_uids = ["824812551379353600"]

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="disabled", enabled=False, reason="disabled_by_config"),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(parsed_uids[0], app=False, behavior=False, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析 UID 文件",
        ),
    )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/legacy/registry/repair should not run for blocked unavailable uid_file path")

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "repair_profile_data", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 UID 文件", country="mx")]

    events = asyncio.run(collect())
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    parse_tool_started = [evt for evt in events if evt["type"] == "tool_started" and evt["tool_name"] == "parse_uid_file"]
    parse_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt["tool_name"] == "parse_uid_file"]
    run_profile_started = [evt for evt in events if evt["type"] == "tool_started" and evt["tool_name"] == "run_profile"]
    run_profile_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt["tool_name"] == "run_profile"]

    assert len(parse_tool_started) == 1
    assert len(parse_tool_completed) == 1
    assert len(run_profile_started) == 0
    assert len(run_profile_completed) == 0
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_flow_blocks_when_parse_returns_empty_uids(monkeypatch):
    session = create_session(country="mx")

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件",
        ),
    )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": [],
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/legacy should not run when parse returns empty uids")

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 UID 文件", country="mx")]

    events = asyncio.run(collect())
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    run_profile_started = [evt for evt in events if evt["type"] == "tool_started" and evt["tool_name"] == "run_profile"]
    second_plan_step_ids = [step["step_id"] for step in plan_events[1]["steps"]]

    assert len(plan_events) == 2
    assert len(run_profile_started) == 0
    assert second_plan_step_ids[-1] == "review_final"
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "empty_uid_file" for issue in review_evt["issues"])
    assert "请检查 UID 文件内容是否有效，或改为直接输入 UID。" in final_evt["final_message"]


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_flow_fails_when_parse_tool_errors(monkeypatch):
    session = create_session(country="mx")

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件",
        ),
    )

    def _fake_parse_uid_file(input_data):
        raise FileNotFoundError("missing test file")

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/legacy should not run when parse tool errors")

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 UID 文件", country="mx")]

    events = asyncio.run(collect())
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    parse_completed = next(
        evt for evt in events if evt["type"] == "tool_completed" and evt["tool_name"] == "parse_uid_file"
    )
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    run_profile_started = [evt for evt in events if evt["type"] == "tool_started" and evt["tool_name"] == "run_profile"]
    second_plan_step_ids = [step["step_id"] for step in plan_events[1]["steps"]]

    assert len(plan_events) == 2
    assert parse_completed["status"] == "error"
    assert len(run_profile_started) == 0
    assert second_plan_step_ids[-1] == "review_final"
    assert review_evt["status"] == "fail"
    assert "请检查文件路径是否正确，且文件位于 data/id_files/ 下。" in final_evt["final_message"]


@pytest.mark.timeout(3)
def test_run_agent_loop_profile_uid_file_flow_blocks_post_parse_unsupported_repair_scope_without_legacy_fallback(monkeypatch):
    session = create_session(country="mx")
    parsed_uids = ["824812551379353600"]

    monkeypatch.setattr(
        agent_loop,
        "ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_data_acquisition_capability",
        lambda: DataAcquisitionCapability(mode="required", enabled=True, reason=None),
    )
    monkeypatch.setattr(
        agent_loop,
        "check_data_availability",
        lambda uids, country=None: _availability_for_uid(parsed_uids[0], app=False, behavior=False, credit=False, country=country or "mx"),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="分析 UID 文件",
        ),
    )

    def _fake_parse_uid_file(input_data):
        return type("Parsed", (), {
            "model_dump": lambda self, mode="json": {
                "uids": parsed_uids,
                "source_path": input_data.file_path,
                "duplicates_removed": 0,
            },
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("repair/run_profile/legacy/query should not run for unsupported post-parse repair scope")

    monkeypatch.setattr("app.services.orchestrator_agent.tools.parse_uid_file", _fake_parse_uid_file)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _fail)
    monkeypatch.setattr(agent_loop, "prepare_repair_query", _fail)
    monkeypatch.setattr(agent_loop, "execute_repair_query", _fail)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析 UID 文件", country="mx")]

    events = asyncio.run(collect())
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "profile_flow_gate_mismatch" for issue in review_evt["issues"])
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)


@pytest.mark.timeout(3)
def test_run_agent_loop_workspace_reuse_does_not_load_tool_registry(monkeypatch):
    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {
                "uid": "824812551379353600",
                "module": "behavior",
                "summary": "行为画像：近30天登录偏低，流失风险高。",
                "structured_result": {"risk_level": "high"},
            }
        ],
    }

    class _EvidenceClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "这是基于已有画像证据的回答。",
                    "confidence": 0.9,
                },
            }

    def _fail_get_tool_registry():
        raise AssertionError("get_tool_registry should not be called for workspace reuse")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _EvidenceClient())
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我总结一下这个用户的行为画像特点", country="mx")]

    events = asyncio.run(collect())
    assert events[-1]["type"] == "final"


@pytest.mark.timeout(3)
def test_run_agent_loop_workspace_flow_skips_legacy_and_persists_single_final(monkeypatch):
    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {
                "uid": "824812551379353600",
                "module": "behavior",
                "summary": "行为画像：近30天登录偏低，流失风险高。",
                "structured_result": {"risk_level": "high"},
            }
        ],
    }
    called = {"legacy": False}

    class _EvidenceClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "这是基于已有画像证据的回答。",
                    "confidence": 0.9,
                },
            }

    def _fail(*args, **kwargs):
        raise AssertionError("should not be called for AnswerWorkspaceFlow")

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _EvidenceClient())
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail)
    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail)
    monkeypatch.setattr(agent_loop, "repair_profile_data", _fail)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我总结一下这个用户的行为画像特点", country="mx")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(collect())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    types = [evt["type"] for evt in events]

    assert called["legacy"] is False
    assert types.count("turn_started") == 1
    assert types.count("run_started") == 1
    assert types.count("execution_plan") == 1
    assert types.count("final") == 1
    assert events[-1]["type"] == "final"
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_answer_workspace_falls_back_to_legacy_when_flow_cannot_handle(monkeypatch):
    session = create_session(country="mx")
    called = {"legacy": False}

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {"status": "ok", "structured_result": {"final_message": "unused", "confidence": 0.3}}

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="answer_from_workspace",
            country="mx",
            uids=["824812551379353600"],
            modules=["behavior"],
            request_summary="总结行为画像",
        ),
    )

    async def _legacy(*args, **kwargs):
        called["legacy"] = True
        args[0].final_message = "legacy-final"
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我总结一下这个用户的行为画像特点", country="mx")]

    events = asyncio.run(collect())
    assert called["legacy"] is True
    assert events[-1]["type"] == "final"
    assert events[-1]["final_message"] == "legacy-final"


@pytest.mark.timeout(3)
def test_run_agent_loop_known_intent_does_not_load_tool_registry(monkeypatch):
    session = create_session(country="mx")

    def _fail_get_tool_registry():
        raise AssertionError("get_tool_registry should not be called for known-intent legacy path")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: None})())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=["824812551379353600"],
            modules=["app"],
            request_summary="分析一个 UID",
        ),
    )
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)

    async def _legacy(*args, **kwargs):
        args[0].final_message = "legacy-final"
        yield {"type": "final", "final_message": "legacy-final", "confidence": 1.0}

    monkeypatch.setattr(agent_loop, "_run_known_request", _legacy)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "分析这个 UID", country="mx")]

    events = asyncio.run(collect())
    assert events[-1]["type"] == "final"


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_loads_tool_registry_lazily(monkeypatch):
    session = create_session(country="mx")
    loaded = {"called": False}
    seen_inputs: list[dict[str, object]] = []
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
            },
        },
        {
            "status": "ok",
            "structured_result": {
                "final_message": "done",
                "confidence": 0.8,
            },
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    def _fake_run_trace(inp):
        seen_inputs.append(inp.model_dump(mode="json"))
        return type("X", (), {"model_dump": lambda self, mode="json": {"events": [], "summary": {}}})()

    def _fake_get_tool_registry():
        loaded["called"] = True
        return {"run_trace": _fake_run_trace}

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="general",
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(
        agent_loop,
        "get_tool_registry",
        lambda: (_ for _ in ()).throw(AssertionError("agent_loop registry alias should not run for migrated run_trace tool loop")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fake_get_tool_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你好，先帮我查轨迹", country="mx")]

    events = asyncio.run(collect())
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    assert loaded["called"] is True
    assert seen_inputs == [{"uid": "824812551379353600", "days": 7}]
    run_trace_starts = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_trace"]
    run_trace_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_trace"]
    assert len(run_trace_starts) == 1
    assert len(run_trace_completed) == 1
    assert run_trace_completed[0]["status"] == "ok"
    assert len(session.tool_calls) == 1
    assert session.tool_calls[0].tool_name == "run_trace"
    assert session.tool_calls[0].status == "done"
    assert sum(1 for message in session.messages if message.role == "tool") == 1
    assert assistant_after - assistant_before == 1
    assert events[-1]["type"] == "final"


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_trace_like_direct_final_does_not_load_registry(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {"final_message": "可以，我先解释轨迹能力。", "confidence": 0.75},
            }

    def _fail_registry():
        raise AssertionError("registry should not load when trace-like prompt gets direct final")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="查轨迹",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你好，先帮我查轨迹", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types.count("tool_started") == 0
    assert types.count("tool_completed") == 0
    assert types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    "structured_result",
    [
        {"tool_call": {"name": "run_profile", "arguments": {"uids": ["824812551379353600"]}}},
        {"tool_call": {"name": "run_trace", "arguments": {"days": 7}}},
    ],
)
def test_run_agent_loop_general_chat_trace_tool_loop_rejects_unsupported_or_invalid_without_tool(monkeypatch, structured_result):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {"status": "ok", "structured_result": structured_result}

    def _fail_registry():
        raise AssertionError("registry should not load before supported run_trace input is valid")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="查轨迹",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你好，先帮我查轨迹", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert assistant_after - assistant_before == 0
    assert session.tool_calls == []


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_trace_tool_loop_registry_missing_fails_without_tool_started(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
                },
            }

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="查轨迹",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", lambda: {})

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你好，先帮我查轨迹", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert assistant_after - assistant_before == 0
    assert session.tool_calls == []


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_trace_tool_loop_tool_error_has_no_final(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
                },
            }

    def _boom(inp):
        raise RuntimeError(f"trace exploded for {inp.uid}")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="查轨迹",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", lambda: {"run_trace": _boom})

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你好，先帮我查轨迹", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_trace"]

    assert len(tool_completed) == 1
    assert tool_completed[0]["status"] == "error"
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_trace_tool_loop_second_tool_call_does_not_execute(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
            },
        },
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
            },
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    def _fake_run_trace(inp):
        return type("X", (), {"model_dump": lambda self, mode="json": {"events": [], "summary": {}}})()

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="查轨迹",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", lambda: {"run_trace": _fake_run_trace})

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你好，先帮我查轨迹", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_tool_loop_success_uses_ack_without_registry(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")
    previews: list[tuple[str, str]] = []
    completes: list[tuple[object, str]] = []
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "query_data",
                    "arguments": {
                        "request": "筛选最近 7 天高风险用户",
                        "country": "mx",
                    },
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "已找到 2 个用户。", "confidence": 0.81},
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    child = object()

    async def _preview(session_arg, request_text, country):
        previews.append((request_text, country))
        return {"child": child, "sql_text": "select uid from users", "rows_estimated": 2}

    async def _complete(session_arg, child_arg, sql_text):
        completes.append((child_arg, sql_text))
        return {
            "uids": ["UID_A", "UID_B"],
            "rows_actual": 2,
            "sql_text": sql_text,
            "rows_estimated": 2,
        }

    def _fail_registry():
        raise AssertionError("query_data GeneralChatFlow path must not call get_tool_registry")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    query_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data"]
    query_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data"]
    awaiting_evt = next(evt for evt in events if evt["type"] == "awaiting_user_ack")

    assert previews == [(
        "筛选最近 7 天高风险用户\n\n[Normalized query hints]\ncountry: mx\ntime_window: last_7_days\nquery_mode: query_only\nauto_profile: false",
        "mx",
    )]
    assert completes == [(child, "select uid from users")]
    assert len(query_started) == 1
    assert len([evt for evt in events if evt["type"] == "awaiting_user_ack"]) == 1
    assert len(query_completed) == 1
    assert query_completed[0]["status"] == "ok"
    assert "查询摘要" in awaiting_evt["sql_text"]
    assert "筛选条件" in awaiting_evt["sql_text"]
    assert "确认提示" in awaiting_evt["sql_text"]
    assert "原始 SQL" in awaiting_evt["sql_text"]
    assert "select uid from users" in awaiting_evt["sql_text"]
    assert awaiting_evt["sql_text"] != "select uid from users"
    assert types.count("final") == 1
    assert assistant_after - assistant_before == 1
    assert sum(1 for message in session.messages if message.role == "tool") == 1
    assert session.tool_calls[0].tool_name == "query_data"
    assert session.tool_calls[0].status == "done"


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_tool_loop_prefers_input_country_over_normalized_country(monkeypatch):
    session = create_session(country="mx")
    previews: list[tuple[str, str]] = []
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "query_data",
                    "arguments": {
                        "request": "show the cohort",
                        "country": "mx",
                    },
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "已找到 2 个用户。", "confidence": 0.81},
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    async def _preview(session_arg, request_text, country):
        previews.append((request_text, country))
        return {"child": object(), "sql_text": "select uid from users", "rows_estimated": 2}

    async def _complete(session_arg, child_arg, sql_text):
        return {
            "uids": ["UID_A", "UID_B"],
            "rows_actual": 2,
            "sql_text": sql_text,
            "rows_estimated": 2,
        }

    def _fail_registry():
        raise AssertionError("query_data GeneralChatFlow path must not call get_tool_registry")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.flows.general_chat.normalize_query_request",
        lambda **kwargs: NormalizedQueryRequest(
            original_text=kwargs["request_text"],
            effective_request_text="normalized request text",
            country="th",
            time_window_key=None,
            time_window_label=None,
            query_mode="query_only",
            auto_profile=False,
            filters_summary=[],
            warnings=[],
        ),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "show the cohort", country="mx")]

    events = asyncio.run(collect())

    assert [evt["type"] for evt in events].count("final") == 1
    assert previews == [("normalized request text", "mx")]


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_direct_final_does_not_start_query(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {"final_message": "我可以帮你设计筛选条件。", "confidence": 0.7},
            }

    def _fail_query(*args, **kwargs):
        raise AssertionError("query_data should not run when query-like prompt receives direct final")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail_query)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types.count("tool_started") == 0
    assert types.count("awaiting_user_ack") == 0
    assert types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    "structured_result",
    [
        {"tool_call": {"name": "run_profile", "arguments": {"uids": ["824812551379353600"]}}},
        {"tool_call": {"name": "query_data", "arguments": {"country": "mx"}}},
    ],
)
def test_run_agent_loop_general_chat_query_data_rejects_unsupported_or_invalid_without_tool(monkeypatch, structured_result):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {"status": "ok", "structured_result": structured_result}

    def _fail_query(*args, **kwargs):
        raise AssertionError("invalid query_data branch should not start DataQueryRunner")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _fail_query)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert assistant_after - assistant_before == 0
    assert session.tool_calls == []


@pytest.mark.timeout(3)
@pytest.mark.parametrize("ack_result", [False, None, "cancelled"])
def test_run_agent_loop_general_chat_query_data_ack_non_approved_cancels_without_final(monkeypatch, ack_result):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "query_data",
                        "arguments": {"request": "筛选用户", "country": "mx"},
                    },
                },
            }

    async def _preview(session_arg, request_text, country):
        return {"child": object(), "sql_text": "select uid from users", "rows_estimated": 2}

    async def _complete(*args, **kwargs):
        raise AssertionError("query_data execute should not run without ACK approval")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda *args, **kwargs: None)
    if ack_result == "cancelled":
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: (_ for _ in ()).throw(asyncio.CancelledError()))
    else:
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: ack_result)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    run = session.turns[-1].runs[-1]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "awaiting_user_ack" in types
    assert "run_cancelled" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0
    assert run.pending_ack is None
    assert run.status == "cancelled"
    assert all(call.status != "running" for call in session.tool_calls if call.run_id == run.run_id)


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_no_ack_completed_continues_to_final(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "query_data",
                    "arguments": {"request": "筛选用户", "country": "mx"},
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "没有匹配用户。", "confidence": 0.66},
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    async def _preview(session_arg, request_text, country):
        return {"uids": [], "rows_actual": 0, "sql_text": "select uid from users", "rows_estimated": 0}

    async def _complete(*args, **kwargs):
        raise AssertionError("complete should not run when preview already completed")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    tool_message = next(message for message in session.messages if message.role == "tool")

    assert "awaiting_user_ack" not in types
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1
    assert assistant_after - assistant_before == 1
    assert sum(1 for message in session.messages if message.role == "tool") == 1
    assert "没有命中用户" in tool_message.content
    assert "放宽筛选条件" in tool_message.content


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_no_ack_completed_large_cohort_uses_prose_observation(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "query_data",
                    "arguments": {"request": "筛选用户", "country": "mx"},
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "请缩小范围后重试。", "confidence": 0.66},
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    async def _preview(session_arg, request_text, country):
        return {
            "uids": [f"u{i:03d}" for i in range(201)],
            "rows_actual": 201,
            "rows_estimated": 201,
            "sql_text": "select uid from users",
        }

    async def _complete(*args, **kwargs):
        raise AssertionError("complete should not run when preview already completed")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    tool_message = next(message for message in session.messages if message.role == "tool")

    assert "awaiting_user_ack" not in types
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1
    assert assistant_after - assistant_before == 1
    assert sum(1 for message in session.messages if message.role == "tool") == 1
    assert "命中的用户数量" in tool_message.content
    assert "缩小范围" in tool_message.content
    assert "不会继续画像或后续分析" in tool_message.content


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_execute_failed_has_no_final(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "query_data",
                        "arguments": {"request": "筛选用户", "country": "mx"},
                    },
                },
            }

    async def _preview(session_arg, request_text, country):
        return {"child": object(), "sql_text": "select uid from users", "rows_estimated": 2}

    async def _complete(*args, **kwargs):
        raise RuntimeError("query exploded")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr(agent_loop, "_complete_query_data_cohort", _complete)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: True)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data"]

    assert len(tool_completed) == 1
    assert tool_completed[0]["status"] == "error"
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_second_tool_call_does_not_execute(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "query_data",
                    "arguments": {"request": "筛选用户", "country": "mx"},
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "query_data", "arguments": {"request": "继续查询", "country": "mx"}},
            },
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    async def _preview(session_arg, request_text, country):
        return {"uids": ["UID_A"], "rows_actual": 1, "sql_text": "select uid from users", "rows_estimated": 1}

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_query_data_context_fit_failure_has_no_final(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "query_data",
                        "arguments": {"request": "筛选用户", "country": "mx"},
                    },
                },
            }

    async def _preview(session_arg, request_text, country):
        return {"uids": ["UID_A"], "rows_actual": 1, "sql_text": "select uid from users", "rows_estimated": 1}

    def _boom(*args, **kwargs):
        raise RuntimeError("context too large")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "execute_query_data_cohort", _preview)
    monkeypatch.setattr("app.services.orchestrator_agent.flows.general_chat.ensure_context_fits", _boom)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户列表", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_run_profile_tool_loop_success_uses_profile_runner_without_registry(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")
    seen_inputs: list[dict[str, object]] = []
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "run_profile",
                    "arguments": {
                        "uids": ["824812551379353600"],
                        "modules": ["behavior"],
                        "strict_data_mode": False,
                    },
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "画像已完成。", "confidence": 0.78},
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    def _fake_run_profile(input_data, progress_callback=None):
        seen_inputs.append(input_data.model_dump(mode="json"))
        if progress_callback is not None:
            progress_callback({
                "progress_type": "profile_module_completed",
                "uid": input_data.uids[0],
                "module": (input_data.modules or ["app"])[0],
                "status": "ok",
                "completed": 1,
                "total": 1,
            })
        return {
            "results": [{"uid": input_data.uids[0], "module": (input_data.modules or ["app"])[0], "result": {"status": "ok"}}],
            "cache_hits": 0,
            "cache_misses": 1,
        }

    def _fail_registry():
        raise AssertionError("run_profile GeneralChatFlow path must not call get_tool_registry")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="执行用户画像",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请执行这个用户的画像分析", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    profile_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"]
    profile_progress = [evt for evt in events if evt["type"] == "tool_progress" and evt.get("tool_name") == "run_profile"]
    profile_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"]

    assert seen_inputs == [{
        "uids": ["824812551379353600"],
        "app_time": None,
        "modules": ["behavior"],
        "strict_data_mode": True,
    }]
    assert len(profile_started) == 1
    assert len(profile_progress) >= 1
    assert len(profile_completed) == 1
    assert profile_completed[0]["status"] == "ok"
    assert session.tool_calls[0].tool_name == "run_profile"
    assert session.tool_calls[0].status == "done"
    assert sum(1 for message in session.messages if message.role == "tool") == 1
    assert types.count("final") == 1
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    "structured_result",
    [
        {"tool_call": {"name": "query_data", "arguments": {"request": "筛选用户", "country": "mx"}}},
        {"tool_call": {"name": "run_profile", "arguments": {"modules": ["app"]}}},
        {"tool_call": {"name": "run_profile", "arguments": {"uids": ["824812551379353600"], "modules": ["unknown"]}}},
    ],
)
def test_run_agent_loop_general_chat_run_profile_rejects_unsupported_or_invalid_without_tool(monkeypatch, structured_result):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {"status": "ok", "structured_result": structured_result}

    def _fail_run_profile(*args, **kwargs):
        raise AssertionError("invalid run_profile branch should not start ProfileRunner")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="执行用户画像",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail_run_profile)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请执行这个用户的画像分析", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert assistant_after - assistant_before == 0
    assert session.tool_calls == []


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_run_profile_tool_error_has_no_final(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_profile", "arguments": {"uids": ["824812551379353600"], "modules": ["app"]}},
                },
            }

    def _boom(input_data, progress_callback=None):
        raise RuntimeError(f"profile exploded for {input_data.uids[0]}")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="执行用户画像",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _boom)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请执行这个用户的画像分析", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile"]

    assert len(tool_completed) == 1
    assert tool_completed[0]["status"] == "error"
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_run_profile_second_tool_call_does_not_execute(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "run_profile", "arguments": {"uids": ["824812551379353600"], "modules": ["app"]}},
            },
        },
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "run_profile", "arguments": {"uids": ["824812551379353600"], "modules": ["app"]}},
            },
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    def _fake_run_profile(input_data, progress_callback=None):
        if progress_callback is not None:
            progress_callback({
                "progress_type": "profile_module_completed",
                "uid": input_data.uids[0],
                "module": "app",
                "status": "ok",
                "completed": 1,
                "total": 1,
            })
        return {"results": [], "cache_hits": 0, "cache_misses": 1}

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="执行用户画像",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请执行这个用户的画像分析", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_run_profile_context_fit_failure_has_no_final(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_profile", "arguments": {"uids": ["824812551379353600"], "modules": ["app"]}},
                },
            }

    def _fake_run_profile(input_data, progress_callback=None):
        if progress_callback is not None:
            progress_callback({
                "progress_type": "profile_module_completed",
                "uid": input_data.uids[0],
                "module": "app",
                "status": "ok",
                "completed": 1,
                "total": 1,
            })
        return {"results": [], "cache_hits": 0, "cache_misses": 1}

    def _boom(*args, **kwargs):
        raise RuntimeError("context too large")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="执行用户画像",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.flows.general_chat.ensure_context_fits", _boom)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请执行这个用户的画像分析", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_no_tool_success_uses_flow_without_tool_registry(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            assert "--- 对话历史 ---" in kwargs["prompt"]
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "我是当前的画像分析助手。",
                    "confidence": 0.7,
                },
            }

    def _fail_get_tool_registry():
        raise AssertionError("get_tool_registry should not be called for no-tool GeneralChatFlow")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你是谁？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert types[:4] == ["session_started", "turn_started", "run_started", "execution_plan"]
    assert types.count("tool_started") == 0
    assert types.count("tool_completed") == 0
    assert types.count("run_completed") == 1
    assert types.count("final") == 1
    assert session.tool_calls == []
    assert assistant_after - assistant_before == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_no_tool_exception_fails_without_final(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FailingClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            raise RuntimeError("llm exploded")

    def _fail_get_tool_registry():
        raise AssertionError("get_tool_registry should not be called after no-tool GeneralChatFlow starts")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FailingClient())
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你是谁？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert any(evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "failed" for evt in events)
    assert assistant_after - assistant_before == 0
    assert session.tool_calls == []


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    "structured_result",
    [
        {},
        {"final_message": None},
        {"final_message": ""},
    ],
)
def test_run_agent_loop_general_chat_no_tool_empty_final_fails_without_final(monkeypatch, structured_result):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {"status": "ok", "structured_result": structured_result}

    def _fail_get_tool_registry():
        raise AssertionError("get_tool_registry should not be called for no-tool GeneralChatFlow failure")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你是谁？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert assistant_after - assistant_before == 0
    assert session.tool_calls == []


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_no_tool_tool_call_mismatch_does_not_fallback_to_legacy(monkeypatch):
    session = create_session(country="mx")
    assistant_before = sum(1 for message in session.messages if message.role == "assistant")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
                },
            }

    def _fail_get_tool_registry():
        raise AssertionError("get_tool_registry should not be called for no-tool tool-call mismatch")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_get_tool_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你是谁？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    assistant_after = sum(1 for message in session.messages if message.role == "assistant")

    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert assistant_after - assistant_before == 0
    assert session.tool_calls == []


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_write_direct_final_fails_without_tool(monkeypatch):
    session = create_session(country="mx")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {"final_message": "已记住。", "confidence": 0.95},
            }

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(write=lambda input_obj: {"ok": True, "path": "/tmp/memory.sqlite3"}),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请记住：我偏好中文输出。", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]

    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_read_direct_final_fails_without_tool(monkeypatch):
    session = create_session(country="mx")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {"final_message": "我记得你偏好中文输出。", "confidence": 0.95},
            }

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(read=lambda input_obj: {"items": [{"content": "用户偏好中文输出"}]}),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你还记得我之前的输出偏好吗？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]

    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_write_success_uses_scoped_facade_without_registry(monkeypatch):
    session = create_session(country="mx")
    seen_inputs: list[dict[str, str]] = []

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "memory_write",
                        "arguments": {
                            "key": "user_output_preference",
                            "value": "请记住：我偏好中文输出，并且回答要简洁。",
                        },
                    }
                },
            }

    def _fake_write(input_obj):
        seen_inputs.append(input_obj.model_dump(mode="json"))
        return {"ok": True, "path": "/tmp/memory.sqlite3"}

    def _fail_registry():
        raise AssertionError("memory GeneralChatFlow path must not call get_tool_registry")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(write=_fake_write),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请记住：我偏好中文输出，并且回答要简洁。", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    tool_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "memory_write"]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "memory_write"]

    assert seen_inputs == [{
        "key": "user_output_preference",
        "value": "请记住：我偏好中文输出，并且回答要简洁。",
    }]
    assert len(tool_started) == 1
    assert len(tool_completed) == 1
    assert tool_completed[0]["status"] == "ok"
    assert types.count("final") == 1
    assert events[-1]["final_message"] == "已记住。"


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_read_success_uses_scoped_facade_without_registry(monkeypatch):
    session = create_session(country="mx")
    seen_inputs: list[dict[str, str]] = []
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "memory_read",
                    "arguments": {"key_pattern": "output_preference"},
                }
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "我记得你偏好中文输出。", "confidence": 0.83},
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    def _fake_read(input_obj):
        seen_inputs.append(input_obj.model_dump(mode="json"))
        return {"items": [{"content": "用户偏好中文输出"}]}

    def _fail_registry():
        raise AssertionError("memory GeneralChatFlow path must not call get_tool_registry")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(read=_fake_read),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(agent_loop, "get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你还记得我之前的输出偏好吗？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    tool_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "memory_read"]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "memory_read"]

    assert seen_inputs == [{"key_pattern": "output_preference"}]
    assert len(tool_started) == 1
    assert len(tool_completed) == 1
    assert tool_completed[0]["status"] == "ok"
    assert sum(1 for message in session.messages if message.role == "tool") == 1
    assert types.count("final") == 1


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_read_empty_result_still_continues_to_final(monkeypatch):
    session = create_session(country="mx")
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "memory_read",
                    "arguments": {"key_pattern": "missing-memory"},
                }
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "我没有找到相关记忆。", "confidence": 0.61},
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(read=lambda input_obj: {"items": []}),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", lambda: (_ for _ in ()).throw(AssertionError("registry should not load for memory_read")))

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你还记得我之前说过什么吗？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]

    assert "run_failed" not in types
    assert "error" not in types
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert types.count("final") == 1


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("prompt", "structured_result"),
    [
        (
            "请记住：我偏好中文输出。",
            {"tool_call": {"name": "memory_read", "arguments": {"key_pattern": "output_preference"}}},
        ),
        (
            "你还记得我之前的输出偏好吗？",
            {"tool_call": {"name": "memory_write", "arguments": {"key": "pref-key", "value": "请记住：偏好中文输出"}}},
        ),
        (
            "请记住：我偏好中文输出。",
            {"tool_call": {"name": "write_memory", "arguments": {"key": "pref-key", "value": "请记住：偏好中文输出"}}},
        ),
        (
            "请记住：我偏好中文输出。",
            {"tool_call": {"name": "memory_write", "arguments": {"value": "缺少 key"}}},
        ),
    ],
)
def test_run_agent_loop_general_chat_memory_rejects_mismatched_alias_or_invalid_without_tool(monkeypatch, prompt, structured_result):
    session = create_session(country="mx")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {"status": "ok", "structured_result": structured_result}

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(
            write=lambda input_obj: (_ for _ in ()).throw(AssertionError("memory_write should not run")),
            read=lambda input_obj: (_ for _ in ()).throw(AssertionError("memory_read should not run")),
        ),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, prompt, country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]

    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_write_ok_false_has_no_final(monkeypatch):
    session = create_session(country="mx")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "memory_write",
                        "arguments": {"key": "pref-key", "value": "请记住：偏好中文输出"},
                    }
                },
            }

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(write=lambda input_obj: {"ok": False, "path": "/tmp/memory.sqlite3"}),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请记住：偏好中文输出", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "memory_write"]

    assert len(tool_completed) == 1
    assert tool_completed[0]["status"] == "ok"
    assert tool_completed[0]["output"]["ok"] is False
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_write_exception_has_no_final(monkeypatch):
    session = create_session(country="mx")

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "memory_write",
                        "arguments": {"key": "pref-key", "value": "请记住：偏好中文输出"},
                    }
                },
            }

    def _boom(input_obj):
        raise RuntimeError("memory exploded")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(write=_boom),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请记住：偏好中文输出", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]
    tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "memory_write"]

    assert len(tool_completed) == 1
    assert tool_completed[0]["status"] == "error"
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_memory_read_second_tool_call_does_not_execute(monkeypatch):
    session = create_session(country="mx")
    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "memory_read", "arguments": {"key_pattern": "pref-key"}},
            },
        },
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "memory_read", "arguments": {"key_pattern": "pref-key"}},
            },
        },
    ])

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(read=lambda input_obj: {"items": [{"content": "用户偏好中文输出"}]}),
    )
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你还记得我之前的输出偏好吗？", country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]

    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types


@pytest.mark.timeout(3)
def test_run_agent_loop_general_chat_multi_family_prompt_uses_defensive_fallback_not_legacy_loop(monkeypatch):
    session = create_session(country="mx")

    class _FailingClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            raise AssertionError("defensive fallback should not call general-chat LLM loop")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FailingClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: _general_chat_request(request_understanding=None),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(
        agent_loop,
        "_build_llm_input",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy general-chat loop should not run for multi-family prompts")),
    )
    monkeypatch.setattr(
        agent_loop,
        "get_tool_registry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("defensive fallback should not touch tool registry")),
    )

    async def collect():
        return [
            evt
            async for evt in agent_loop.run_agent_loop(
                session,
                "请先筛选最近 7 天高风险用户，再把结果记住。",
                country="mx",
            )
        ]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]

    assert "tool_started" not in types
    assert "tool_completed" not in types
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types


@pytest.mark.timeout(3)
@pytest.mark.parametrize(
    ("case_name", "prompt"),
    [
        ("no_tool", "你是谁？"),
        ("run_trace", "请帮我查一下这个用户的轨迹"),
        ("query_data", "帮我筛选最近 7 天高风险用户"),
        ("run_profile", "请执行这个用户的画像分析"),
        ("memory_write", "请记住：我偏好中文输出。"),
        ("memory_read", "你还记得我之前的输出偏好吗？"),
    ],
)
def test_run_agent_loop_migrated_general_chat_paths_do_not_use_legacy_build_llm_input(monkeypatch, case_name, prompt):
    session = create_session(country="mx")

    if case_name == "no_tool":
        decisions = iter([
            {
                "status": "ok",
                "structured_result": {"final_message": "我是当前的画像分析助手。", "confidence": 0.61},
            },
        ])
        normalized_request = _general_chat_request()
    elif case_name == "run_trace":
        decisions = iter([
            {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
                },
            },
            {
                "status": "ok",
                "structured_result": {"final_message": "轨迹分析完成。", "confidence": 0.82},
            },
        ])
        normalized_request = _general_chat_request(request_understanding=None)
        monkeypatch.setattr(
            "app.services.orchestrator_agent.tools.get_tool_registry",
            lambda: {
                "run_trace": lambda input_data: type("TraceOut", (), {
                    "model_dump": lambda self, mode="json": {
                        "uid": input_data.uid,
                        "status": "ok",
                        "events": [],
                        "summary": {},
                    },
                })(),
            },
        )
    elif case_name == "query_data":
        decisions = iter([
            {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "query_data",
                        "arguments": {"request": "筛选最近 7 天高风险用户", "country": "mx"},
                    },
                },
            },
            {
                "status": "ok",
                "structured_result": {"final_message": "已完成筛选。", "confidence": 0.8},
            },
        ])
        normalized_request = _general_chat_request(request_understanding=None)
        monkeypatch.setattr(
            agent_loop,
            "execute_query_data_cohort",
            lambda session_arg, request_text, country: {
                "child": object(),
                "sql_text": "select uid from users",
                "rows_estimated": 2,
            },
        )
        monkeypatch.setattr(
            agent_loop,
            "_complete_query_data_cohort",
            lambda session_arg, child_arg, sql_text: {
                "uids": ["UID_A", "UID_B"],
                "rows_actual": 2,
                "sql_text": sql_text,
                "rows_estimated": 2,
            },
        )
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda *args, **kwargs: None)
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: True)
    elif case_name == "run_profile":
        decisions = iter([
            {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "run_profile",
                        "arguments": {"uids": ["824812551379353600"], "modules": ["app"]},
                    },
                },
            },
            {
                "status": "ok",
                "structured_result": {"final_message": "画像完成。", "confidence": 0.82},
            },
        ])
        normalized_request = _general_chat_request(request_understanding=None)
        monkeypatch.setattr(
            "app.services.orchestrator_agent.tools.run_profile",
            lambda input_data, progress_callback=None: {"results": [], "cache_hits": 0, "cache_misses": 1},
        )
    elif case_name == "memory_write":
        decisions = iter([
            {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "memory_write",
                        "arguments": {
                            "key": "user_output_preference",
                            "value": "请记住：我偏好中文输出。",
                        },
                    },
                },
            },
        ])
        normalized_request = _general_chat_request(request_understanding=None)
        monkeypatch.setattr(
            agent_loop,
            "_build_memory_facade",
            lambda *args, **kwargs: MemoryFacade(write=lambda input_obj: {"ok": True, "path": "/tmp/memory.sqlite3"}),
        )
    else:
        decisions = iter([
            {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "memory_read",
                        "arguments": {"key_pattern": "output_preference"},
                    },
                },
            },
            {
                "status": "ok",
                "structured_result": {"final_message": "我记得你偏好中文输出。", "confidence": 0.83},
            },
        ])
        normalized_request = _general_chat_request(request_understanding=None)
        monkeypatch.setattr(
            agent_loop,
            "_build_memory_facade",
            lambda *args, **kwargs: MemoryFacade(read=lambda input_obj: {"items": [{"content": "用户偏好中文输出"}]}),
        )

    class _FakeClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _FakeClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: normalized_request,
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(
        agent_loop,
        "_build_llm_input",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy general-chat loop should not run for migrated paths")),
    )

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, prompt, country="mx")]

    events = asyncio.run(collect())
    types = [evt["type"] for evt in events]

    assert "run_failed" not in types
    assert "error" not in types
    assert types.count("final") == 1


def test_runtime_session_and_event_helpers_persist(monkeypatch):
    session = create_session(country="mx")
    saves: list[str] = []

    monkeypatch.setattr(session_lifecycle, "save_session", lambda sess: saves.append("lifecycle"))
    monkeypatch.setattr(event_recorder, "save_session", lambda sess: saves.append("event"))

    session_lifecycle.create_turn(session, turn_id="t1", client_turn_id=None, prompt="hello")
    session_lifecycle.create_turn_run(session, turn_id="t1", run_id="r1")
    session_lifecycle.set_pending_ack(
        session,
        run_id="r1",
        ack_id="ack1",
        tool_call_id="tool1",
        sql_text="select 1",
        rows_estimated=1,
    )
    session_lifecycle.clear_pending_ack(session, run_id="r1")
    session_lifecycle.set_pending_resolution(
        session,
        run_id="r1",
        resolution_id="res1",
        step_id="clarify",
        resolution_type="clarification",
        message="please clarify",
    )
    session_lifecycle.clear_pending_resolution(session, run_id="r1")
    session_lifecycle.set_run_status(session, run_id="r1", status="running")
    event_recorder.record_run_event(
        session,
        turn_id="t1",
        run_id="r1",
        event_type="custom",
        payload={"ok": True},
    )

    assert saves.count("lifecycle") >= 6
    assert "event" in saves


def test_session_lifecycle_append_tool_observation_preserves_message_shape_and_order(monkeypatch):
    session = create_session(country="mx")
    lifecycle = session_lifecycle.SessionLifecycle(session)
    saves: list[str] = []

    monkeypatch.setattr(session_lifecycle, "save_session", lambda sess: saves.append("saved"))

    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")

    before_len = len(session.messages)
    lifecycle.append_tool_observation(
        turn_id="t1",
        run_id="r1",
        tool_call_id="tc-1",
        content='{"items": []}',
    )

    assert len(session.messages) == before_len + 1
    message = session.messages[-1]
    assert message.role == "tool"
    assert message.tool_call_id == "tc-1"
    assert message.turn_id == "t1"
    assert message.run_id == "r1"
    assert message.content == '{"items": []}'
    assert message.timestamp is not None
    assert saves.count("saved") == 3


def test_session_lifecycle_mark_run_failed_matches_general_chat_fail_side_effects(monkeypatch):
    session = create_session(country="mx")
    lifecycle = session_lifecycle.SessionLifecycle(session)
    saves: list[str] = []

    monkeypatch.setattr(session_lifecycle, "save_session", lambda sess: saves.append("saved"))

    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")

    lifecycle.mark_run_failed(run_id="r1", session_status="error")

    run = session_lifecycle.find_run(session, "r1")
    assert run is not None
    assert run.status == "failed"
    assert run.ended_at is not None
    assert session.active_run_id is None
    assert session.active_turn_id is None
    assert session.active_run_status == "failed"
    assert session.status == "error"
    assert saves.count("saved") == 4


def test_general_chat_module_does_not_import_or_call_session_store():
    path = Path("app/services/orchestrator_agent/flows/general_chat.py")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.orchestrator_agent.session_store":
            raise AssertionError("general_chat.py must not import session_store directly")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services.orchestrator_agent.session_store":
                    raise AssertionError("general_chat.py must not import session_store directly")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "save_session":
            raise AssertionError("general_chat.py must not call save_session directly")


def test_trace_store_updates_persist(monkeypatch):
    session = create_session(country="mx")
    saves: list[str] = []
    monkeypatch.setattr(trace_store, "save_session", lambda sess: saves.append("trace"))

    trace = trace_store.create_execution_trace(
        session,
        execution_id="exec1",
        turn_id="t1",
        run_id="r1",
        prompt="hello",
        normalized_request=NormalizedRequest(
            intent="general_chat",
            request_summary="hello",
        ),
        availability=None,
        steps=[PlanStep(step_id="s1", title="step", kind="demo")],
    )
    trace_store.update_trace_step(session, trace, step_id="s1", status="done", result_summary="ok")
    trace_store.finalize_trace(session, trace, final_status="completed", final_message="done")

    assert saves.count("trace") >= 3


def test_new_refactor_modules_do_not_import_agent_loop():
    base = Path("app/services/orchestrator_agent")
    targets = [
        base / "runtime",
        base / "finalization",
        base / "planning",
        base / "flows",
        base / "execution",
    ]
    for directory in targets:
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "app.services.orchestrator_agent.agent_loop":
                    raise AssertionError(f"{path} imports agent_loop directly")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.orchestrator_agent.agent_loop":
                            raise AssertionError(f"{path} imports agent_loop directly")


def test_agent_loop_phase_7b_contract_keeps_compat_surface_and_removes_local_profile_shims():
    assert hasattr(agent_loop, "_build_llm_input")
    assert hasattr(agent_loop, "get_tool_registry")
    assert hasattr(agent_loop, "execute_query_data_cohort")
    assert hasattr(agent_loop, "_complete_query_data_cohort")
    assert not hasattr(agent_loop, "_call_tool_with_optional_progress")
    assert not hasattr(agent_loop, "_log_run_profile_progress")
