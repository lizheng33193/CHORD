"""Golden Test runner: drive run_agent_loop with deterministic mock LLM,
collect session log, feed to mock Judge, assert verdict == 'pass'.

V1 用 mock LLM + mock Judge 验证 runner 链路真跑通（不依赖真实 LLM 配额）。
Plan #03 [complete] 后再做 5-10 次手工对齐校准（独立迭代，非本 Plan）。
"""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest


GOLDEN_DIR = Path(__file__).parent / "golden"

# Data Agent capability test convention:
# - fake query_data / repair success paths must patch capability as enabled
# - unavailable behavior tests must set DATA_ACQUISITION_ENABLED=false or patch disabled capability
# - fake Data Agent tests must not depend on local DA dependencies being installed


def _patch_enabled_data_acquisition(monkeypatch):
    from app.core.data_acquisition_capability import DataAcquisitionCapability

    cap = DataAcquisitionCapability(mode="auto", enabled=True, reason=None)
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.agent_loop"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.repair_profile_data"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.tools.query_data"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    return cap


def _build_mock_decisions(case: dict) -> list[dict]:
    """根据 case.expected_tools 拼出 deterministic LLM decision 序列。

    每个工具一轮 tool_call decision，最后一轮 final decision。
    """
    decisions = []
    case_tool_arguments = case.get("tool_arguments") or {}
    for tool in case["expected_tools"]:
        if tool in case_tool_arguments:
            args = case_tool_arguments[tool]
        elif tool == "parse_uid_file":
            args = {"file_path": f"data/id_files/{case['country']}/sample.txt"}
        elif tool == "run_profile":
            args = {
                "uids": case["seed_uids"] or ["MOCK_UID"],
                "app_time": "2026-04-30",
                "modules": ["app"],
            }
        elif tool == "run_trace":
            args = {"uid": case["seed_uids"][0], "days": 7}
        elif tool == "query_data":
            args = {"request": case["prompt"], "country": case["country"]}
        else:
            args = {}
        decisions.append({
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": tool, "arguments": args},
            },
        })
    # Final
    final_md = "\n".join(f"## {t}\n占位\n" for t in case["expected_final_topics"])
    decisions.append({
        "status": "ok",
        "structured_result": {
            "final_message": final_md,
            "confidence": 0.7,
        },
    })
    return decisions


def _mock_judge(case: dict, session_log: list) -> dict:
    """Mock Judge：检查工具序列与 case.expected_tools 一致 → verdict=pass。

    R7 P1-3 KNOWN LIMITATIONS（V1 mock Judge 范围明示）：
    - 仅检查工具名序列严格匹配 expected_tools
    - 不验证 tool 入参（country / app_time / uid 提取准确性）
    - 不验证 final_message 是否覆盖 expected_final_topics
    - 不检测幻觉（如 LLM 反返伪造不存在的 UID）
    - mock=pass 不等于“真实 LLM Judge=pass”

    真实 LLM Judge 5-10 次手工对齐校准 → Plan #03 [complete] 后独立迭代
    （见 “Plan #03 [complete] 后的延伸工作” §2）。
    """
    actual_tools = [
        e["tool_name"] for e in session_log
        if e.get("type") == "tool_started"
    ]
    expected_args = case.get("expected_tool_arguments") or {}
    argument_errors = []
    for e in session_log:
        if e.get("type") != "tool_started":
            continue
        tool_name = e.get("tool_name")
        if tool_name not in expected_args:
            continue
        if not _contains_subset(e.get("input") or {}, expected_args[tool_name]):
            argument_errors.append({
                "tool": tool_name,
                "actual": e.get("input") or {},
                "expected_subset": expected_args[tool_name],
            })
    if actual_tools == case["expected_tools"] and not argument_errors:
        return {
            "scores": {
                "tool_selection": 5,
                "tool_order": 5,
                "param_extract": 5,
                "no_hallucination": 5,
            },
            "total": 20,
            "verdict": "pass",
            "rationale": "mock Judge: tool sequence matches exactly",
        }
    rationale = f"actual={actual_tools} expected={case['expected_tools']}"
    if argument_errors:
        rationale += f" argument_errors={argument_errors}"
    return {
        "scores": {"tool_selection": 1, "tool_order": 1, "param_extract": 1, "no_hallucination": 1},
        "total": 4,
        "verdict": "fail",
        "rationale": rationale,
    }


def _contains_subset(actual, expected) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _contains_subset(actual[k], v) for k, v in expected.items())
    return actual == expected


@pytest.mark.parametrize("case_path", sorted(GOLDEN_DIR.glob("case_*.json")))
def test_golden_case(case_path, monkeypatch):
    case = json.loads(case_path.read_text(encoding="utf-8"))

    # 跳过 V1 不支持的国别（country in co/pe/cl/br + tool 含 query_data）
    if "query_data" in case["expected_tools"] and case["country"] in {"co", "pe", "cl", "br", "th"}:
        pytest.skip(f"V1 query_data only supports mexico; case country={case['country']}")

    decisions = iter(_build_mock_decisions(case))

    class _FakeClient:
        last_token_usage = {"prompt": 100, "completion": 50, "total": 150}
        def generate_structured(self, **kwargs):
            return next(decisions)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _FakeClient(),
    )

    # Mock 各工具：返回固定结构，避免真实数据依赖
    def _mk_output(tool_name):
        if tool_name == "parse_uid_file":
            return type("X", (), {"model_dump": lambda self, mode="json": {
                "uids": case.get("seed_uids", []), "source_path": "mock", "duplicates_removed": 0,
            }})()
        if tool_name == "run_profile":
            return type("X", (), {"model_dump": lambda self, mode="json": {
                "results": [], "cache_hits": 0, "cache_misses": 0,
            }})()
        if tool_name == "run_trace":
            return type("X", (), {"model_dump": lambda self, mode="json": {
                "events": [], "summary": {},
            }})()
        return type("X", (), {"model_dump": lambda self, mode="json": {}})()

    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file",
        lambda inp: _mk_output("parse_uid_file"),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp: _mk_output("run_profile"),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_trace",
        lambda inp: _mk_output("run_trace"),
    )

    if "run_profile" in case["expected_tools"]:
        from app.services.orchestrator_agent.schemas import (
            BucketAvailability,
            DataAvailability,
            UidAvailability,
        )

        monkeypatch.setattr(
            "app.services.orchestrator_agent.agent_loop.check_data_availability",
            lambda uids, country=None: DataAvailability(
                country=country,
                checked_uids=list(uids),
                per_uid=[
                    UidAvailability(
                        uid=str(uid),
                        app=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/app.csv"),
                        behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/behavior.csv"),
                        credit=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/credit.csv"),
                        available_buckets=["app", "behavior", "credit"],
                        missing_buckets=[],
                    )
                    for uid in uids
                ],
            ),
        )

    # query_data ACK 分支：mock _ChildAgent + auto-resolve ACK
    if "query_data" in case["expected_tools"]:
        _patch_enabled_data_acquisition(monkeypatch)
        from unittest.mock import MagicMock
        mock_qr = MagicMock()
        mock_qr.sql_text = "SELECT uid FROM users LIMIT 10"
        mock_qr.rows_estimated = 10

        class _MockChild:
            def __init__(self, country): pass
            def run_query(self, req): return mock_qr
            def execute(self, sql): return {"uids": ["MOCK_UID"], "rows_actual": 1}
        import importlib
        _qd_mod = importlib.import_module("app.services.orchestrator_agent.tools.query_data")
        monkeypatch.setattr(_qd_mod, "_ChildAgent", _MockChild)

        # auto-resolve ACK
        import threading
        from app.services.orchestrator_agent.ack_bus import resolve_ack
        def _auto_ack():
            import time as _t
            _t.sleep(0.1)
            resolve_ack(_session_id_holder["sid"], True)
        _session_id_holder = {"sid": None}

        original_open_ack = None
        from app.services.orchestrator_agent import ack_bus
        original_open_ack = ack_bus.open_ack
        def _patched_open_ack(sid):
            _session_id_holder["sid"] = sid
            ev = original_open_ack(sid)
            threading.Thread(target=_auto_ack, daemon=True).start()
            return ev
        monkeypatch.setattr(ack_bus, "open_ack", _patched_open_ack)

    # Drive agent loop
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session
    sess = create_session()

    async def _drive():
        events = []
        async for evt in run_agent_loop(session=sess, prompt=case["prompt"]):
            events.append(evt)
        return events

    events = asyncio.run(_drive())

    # Feed to mock Judge
    verdict_obj = _mock_judge(case, events)
    assert verdict_obj["verdict"] == "pass", (
        f"Golden case {case['case_id']} failed: {verdict_obj['rationale']}"
    )
