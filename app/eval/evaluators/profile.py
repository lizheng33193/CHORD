"""Profile DAG regression evaluator backed by deterministic runtime seams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.eval.evaluators.base import BaseEvaluator
from app.eval.schemas import EvalCase, EvalResult
from app.services.memory.adapters import profile_snapshot_to_memory_candidate
from app.services.memory.contracts import MemoryUsePurpose
from app.services.memory.isolation import validate_memory_use
from app.services.profile_dag.adapters import (
    node_run_to_module_result,
    snapshot_to_run_profile_rows,
    snapshot_to_user_analysis_result,
)
from app.services.profile_dag.contracts import (
    ProfileNodeRun,
    ProfileNodeSpec,
    ProfileRun,
    ProfileRunResultSnapshot,
)
from app.services.profile_dag.executor import ProfileDagExecutor
from app.services.profile_dag.memory_snapshot import build_profile_memory_snapshot
from app.services.profile_dag.node_registry import NODE_KEY_TO_SPEC, PROFILE_NODE_SPECS, resolve_execution_closure


_EXPECTED_NODE_CONTRACT: dict[str, dict[str, Any]] = {
    "app": {"stage": 0, "depends_on": [], "skill_name": "app_profile", "result_key": "app_profile"},
    "behavior": {
        "stage": 0,
        "depends_on": [],
        "skill_name": "behavior_profile",
        "result_key": "behavior_profile",
    },
    "credit": {"stage": 0, "depends_on": [], "skill_name": "credit_profile", "result_key": "credit_profile"},
    "comprehensive": {
        "stage": 1,
        "depends_on": ["app", "behavior", "credit"],
        "skill_name": "comprehensive_profile",
        "result_key": "comprehensive_profile",
    },
    "product": {
        "stage": 2,
        "depends_on": ["comprehensive"],
        "skill_name": "product_advice",
        "result_key": "product_advice",
    },
    "ops": {
        "stage": 2,
        "depends_on": ["comprehensive"],
        "skill_name": "ops_advice",
        "result_key": "ops_advice",
    },
}
_CANONICAL_NODE_ORDER = [spec.node_key for spec in PROFILE_NODE_SPECS]
_USER_ANALYSIS_OUTPUT_KEYS = [
    "app_profile",
    "behavior_profile",
    "credit_profile",
    "comprehensive_profile",
    "product_advice",
    "ops_advice",
]


@dataclass(slots=True)
class _RuntimeArtifacts:
    run: ProfileRun
    snapshot: ProfileRunResultSnapshot
    events: list[dict[str, Any]]
    memory_snapshot: dict[str, Any]


class ProfileEvaluator(BaseEvaluator):
    evaluator_id = "profile"

    def evaluate_case(self, case: EvalCase) -> EvalResult:
        check_kind = str(case.input.get("check_kind") or "").strip()
        if check_kind == "node_registry":
            return self._evaluate_node_registry(case)
        if check_kind == "execution_closure":
            return self._evaluate_execution_closure(case)
        if check_kind in {"dag_execution", "dependency_skip", "degraded_execution", "structured_output"}:
            return self._evaluate_runtime_execution(case)
        if check_kind == "event_contract":
            return self._evaluate_event_contract(case)
        if check_kind == "snapshot_contract":
            return self._evaluate_snapshot_contract(case)
        if check_kind == "legacy_adapter":
            return self._evaluate_legacy_adapter(case)
        if check_kind == "memory_boundary":
            return self._evaluate_memory_boundary(case)
        raise ValueError(f"unsupported profile dag check_kind: {check_kind}")

    def build_suite_metrics(self, results: list[EvalResult]) -> dict[str, Any]:
        suite_id = results[0].suite if results else "profile"
        if suite_id == "profile_dag_contract":
            return {
                "profile_dag_contract_pass_rate": _pass_rate(results),
                "node_registry_contract_pass_rate": _pass_rate(
                    [result for result in results if result.metrics.get("check_kind") == "node_registry"]
                ),
                "execution_closure_pass_rate": _pass_rate(
                    [result for result in results if result.metrics.get("check_kind") == "execution_closure"]
                ),
                "dag_execution_pass_rate": _pass_rate(
                    [result for result in results if result.metrics.get("check_kind") == "dag_execution"]
                ),
                "dependency_skip_pass_rate": _pass_rate(
                    [result for result in results if result.metrics.get("check_kind") == "dependency_skip"]
                ),
                "degraded_execution_pass_rate": _pass_rate(
                    [result for result in results if result.metrics.get("check_kind") == "degraded_execution"]
                ),
                "event_contract_pass_rate": _pass_rate(
                    [result for result in results if result.metrics.get("check_kind") == "event_contract"]
                ),
                "structured_output_pass_rate": _pass_rate(
                    [result for result in results if result.metrics.get("check_kind") == "structured_output"]
                ),
            }
        return {
            "profile_memory_snapshot_pass_rate": _pass_rate(results),
            "snapshot_contract_pass_rate": _pass_rate(
                [result for result in results if result.metrics.get("check_kind") == "snapshot_contract"]
            ),
            "legacy_adapter_pass_rate": _pass_rate(
                [result for result in results if result.metrics.get("check_kind") == "legacy_adapter"]
            ),
            "profile_memory_boundary_block_rate": _pass_rate(
                [
                    result
                    for result in results
                    if result.metrics.get("check_kind") == "memory_boundary"
                    and result.metrics.get("expected_decision") == "blocked"
                ]
            ),
            "profile_evidence_status_coverage": _ratio(
                results,
                lambda result: bool((result.artifacts.get("memory_snapshot") or {}).get("evidence_status")),
            ),
        }

    def _evaluate_node_registry(self, case: EvalCase) -> EvalResult:
        raw_failures: list[str] = []
        actual_nodes = [spec.node_key for spec in PROFILE_NODE_SPECS]
        if actual_nodes != _CANONICAL_NODE_ORDER:
            raw_failures.append("PROFILE_DAG_NODE_SPEC_MISSING")

        for spec in PROFILE_NODE_SPECS:
            expected_contract = _EXPECTED_NODE_CONTRACT.get(spec.node_key)
            if expected_contract is None:
                raw_failures.append("PROFILE_DAG_NODE_SPEC_MISSING")
                continue
            if spec.stage != expected_contract["stage"]:
                raw_failures.append("PROFILE_DAG_DEPENDENCY_MISMATCH")
            if list(spec.depends_on) != list(expected_contract["depends_on"]):
                raw_failures.append("PROFILE_DAG_DEPENDENCY_MISMATCH")
            if spec.skill_name != expected_contract["skill_name"] or spec.result_key != expected_contract["result_key"]:
                raw_failures.append("PROFILE_DAG_NODE_SPEC_MISSING")

        raw_failures = _dedupe(raw_failures)
        actual_decision = "blocked" if raw_failures else "allowed"
        normalized_failures = list(raw_failures)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=[],
            actual_failure_codes=normalized_failures,
        )
        failures.extend(
            _compare_required_values(
                label="nodes",
                expected=case.expected.get("required_nodes", []),
                actual=actual_nodes,
            )
        )
        return _build_result(
            case=case,
            check_kind="node_registry",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "node_registry",
                "raw_decision": actual_decision,
                "run_status": None,
                "node_statuses": {},
                "requested_modules": [],
                "execution_closure": [],
                "event_types": [],
                "module_output_keys": [],
                "memory_boundary_decisions": {},
                "node_specs": {
                    spec.node_key: {
                        "stage": spec.stage,
                        "depends_on": list(spec.depends_on),
                        "skill_name": spec.skill_name,
                        "result_key": spec.result_key,
                    }
                    for spec in PROFILE_NODE_SPECS
                },
            },
        )

    def _evaluate_execution_closure(self, case: EvalCase) -> EvalResult:
        requested_modules = [str(module) for module in case.input.get("requested_modules", [])]
        closure = resolve_execution_closure(requested_modules)
        actual_nodes = [node_key for node_key in _CANONICAL_NODE_ORDER if node_key in closure]
        actual_decision = "allowed"
        raw_failures: list[str] = []
        expected_nodes = [str(node) for node in case.expected.get("required_nodes", [])]
        if expected_nodes and actual_nodes != expected_nodes:
            raw_failures.append("PROFILE_DAG_EXECUTION_CLOSURE_MISMATCH")
            actual_decision = "blocked"

        normalized_failures = list(raw_failures)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=[],
            actual_failure_codes=normalized_failures,
        )
        failures.extend(_compare_required_values("nodes", expected_nodes, actual_nodes))
        return _build_result(
            case=case,
            check_kind="execution_closure",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "execution_closure",
                "raw_decision": actual_decision,
                "run_status": None,
                "node_statuses": {},
                "requested_modules": requested_modules,
                "execution_closure": actual_nodes,
                "event_types": [],
                "module_output_keys": [],
                "memory_boundary_decisions": {},
            },
        )

    def _evaluate_runtime_execution(self, case: EvalCase) -> EvalResult:
        runtime = _execute_runtime_case(case.input, capture_events=False)
        node_statuses = {node_run.node_key: node_run.status for node_run in runtime.snapshot.node_runs}
        raw_failures = _runtime_contract_failures(case, runtime)
        actual_decision = "blocked" if raw_failures else "allowed"
        normalized_failures = _dedupe(raw_failures)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=[],
            actual_failure_codes=normalized_failures,
        )
        failures.extend(
            _compare_runtime_statuses(
                case.expected,
                node_statuses=node_statuses,
                closure=resolve_execution_closure([str(item) for item in case.input.get("requested_modules", [])]),
                snapshot=runtime.snapshot,
            )
        )

        return _build_result(
            case=case,
            check_kind=str(case.input.get("check_kind") or ""),
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=normalized_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": str(case.input.get("check_kind") or ""),
                "raw_decision": runtime.run.status,
                "run_status": runtime.run.status,
                "node_statuses": node_statuses,
                "requested_modules": list(runtime.snapshot.requested_modules),
                "execution_closure": [
                    node_key
                    for node_key in _CANONICAL_NODE_ORDER
                    if node_key in resolve_execution_closure(list(runtime.snapshot.requested_modules))
                ],
                "event_types": [],
                "module_output_keys": list(runtime.snapshot.module_outputs.keys()),
                "memory_boundary_decisions": {},
                "memory_snapshot": runtime.memory_snapshot,
            },
        )

    def _evaluate_event_contract(self, case: EvalCase) -> EvalResult:
        runtime = _execute_runtime_case(case.input, capture_events=True)
        event_types = [str(event.get("type") or "") for event in runtime.events]
        raw_failures = _event_contract_failures(case.expected.get("required_event_types", []), runtime.events)
        actual_decision = "blocked" if raw_failures else "allowed"
        normalized_failures = _dedupe(raw_failures)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=[],
            actual_failure_codes=normalized_failures,
        )
        failures.extend(
            _compare_required_values(
                label="event_types",
                expected=case.expected.get("required_event_types", []),
                actual=event_types,
            )
        )
        return _build_result(
            case=case,
            check_kind="event_contract",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=normalized_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "event_contract",
                "raw_decision": runtime.run.status,
                "run_status": runtime.run.status,
                "node_statuses": {node_run.node_key: node_run.status for node_run in runtime.snapshot.node_runs},
                "requested_modules": list(runtime.snapshot.requested_modules),
                "execution_closure": [
                    node_key
                    for node_key in _CANONICAL_NODE_ORDER
                    if node_key in resolve_execution_closure(list(runtime.snapshot.requested_modules))
                ],
                "event_types": event_types,
                "module_output_keys": list(runtime.snapshot.module_outputs.keys()),
                "memory_boundary_decisions": {},
                "memory_snapshot": runtime.memory_snapshot,
            },
        )

    def _evaluate_snapshot_contract(self, case: EvalCase) -> EvalResult:
        runtime = _execute_runtime_case(case.input, capture_events=False)
        node_statuses = {node_run.node_key: node_run.status for node_run in runtime.snapshot.node_runs}
        raw_failures: list[str] = []
        actual_output_keys = list(runtime.snapshot.module_outputs.keys())
        expected_output_keys = [str(item) for item in case.expected.get("required_output_keys", [])]
        if expected_output_keys:
            failures = _compare_required_values("output_keys", expected_output_keys, actual_output_keys)
            if failures:
                raw_failures.append("PROFILE_DAG_SNAPSHOT_CONTRACT_MISSING")
        snapshot_fields = [str(item) for item in case.input.get("metadata", {}).get("snapshot_fields", [])]
        for field in snapshot_fields or [str(item) for item in case.expected.get("required_structured_fields", [])]:
            if not runtime.memory_snapshot.get(field):
                raw_failures.append(
                    "PROFILE_DAG_EVIDENCE_STATUS_MISSING"
                    if field == "evidence_status"
                    else "PROFILE_DAG_SNAPSHOT_CONTRACT_MISSING"
                )

        actual_decision = "blocked" if raw_failures else "allowed"
        normalized_failures = _dedupe(raw_failures)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=[],
            actual_failure_codes=normalized_failures,
        )
        failures.extend(
            _compare_runtime_statuses(
                case.expected,
                node_statuses=node_statuses,
                closure=resolve_execution_closure([str(item) for item in case.input.get("requested_modules", [])]),
                snapshot=runtime.snapshot,
            )
        )
        failures.extend(_compare_required_values("output_keys", expected_output_keys, actual_output_keys))
        return _build_result(
            case=case,
            check_kind="snapshot_contract",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=normalized_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "snapshot_contract",
                "raw_decision": runtime.run.status,
                "run_status": runtime.run.status,
                "node_statuses": node_statuses,
                "requested_modules": list(runtime.snapshot.requested_modules),
                "execution_closure": [
                    node_key
                    for node_key in _CANONICAL_NODE_ORDER
                    if node_key in resolve_execution_closure(list(runtime.snapshot.requested_modules))
                ],
                "event_types": [],
                "module_output_keys": actual_output_keys,
                "memory_boundary_decisions": {},
                "memory_snapshot": runtime.memory_snapshot,
            },
        )

    def _evaluate_legacy_adapter(self, case: EvalCase) -> EvalResult:
        runtime = _execute_runtime_case(case.input, capture_events=False)
        target = str(case.input.get("metadata", {}).get("adapter_target") or "user_analysis_result")
        raw_failures: list[str] = []

        if target == "run_profile_rows":
            rows = snapshot_to_run_profile_rows(runtime.snapshot)
            row_modules = [str(row.get("module") or "") for row in rows]
            for row in rows:
                result = row.get("result") if isinstance(row.get("result"), dict) else {}
                if str(row.get("uid") or "") != runtime.snapshot.uid:
                    raw_failures.append("PROFILE_DAG_LEGACY_ADAPTER_MISMATCH")
                if str(result.get("module") or "") != str(row.get("module") or ""):
                    raw_failures.append("PROFILE_DAG_LEGACY_ADAPTER_MISMATCH")
                if str(result.get("status") or "") not in {"ok", "error"}:
                    raw_failures.append("PROFILE_DAG_LEGACY_ADAPTER_MISMATCH")
                data = result.get("data")
                if data is not None and not _has_agent_output_shape(data):
                    raw_failures.append("PROFILE_DAG_LEGACY_ADAPTER_MISMATCH")
            actual_decision = "blocked" if raw_failures else "allowed"
            normalized_failures = _dedupe(raw_failures)
            failures = _compare_common_expectations(
                expected=case.expected,
                actual_decision=actual_decision,
                actual_warning_codes=[],
                actual_failure_codes=normalized_failures,
            )
            failures.extend(_compare_required_values("row_modules", case.expected.get("required_nodes", []), row_modules))
            return _build_result(
                case=case,
                check_kind="legacy_adapter",
                actual_decision=actual_decision,
                raw_warnings=[],
                normalized_warnings=[],
                raw_failures=normalized_failures,
                normalized_failures=normalized_failures,
                failures=failures,
                artifacts={
                    "policy_source": "adapter",
                    "check_kind": "legacy_adapter",
                    "raw_decision": actual_decision,
                    "run_status": runtime.run.status,
                    "node_statuses": {node_run.node_key: node_run.status for node_run in runtime.snapshot.node_runs},
                    "requested_modules": list(runtime.snapshot.requested_modules),
                    "execution_closure": [
                        node_key
                        for node_key in _CANONICAL_NODE_ORDER
                        if node_key in resolve_execution_closure(list(runtime.snapshot.requested_modules))
                    ],
                    "event_types": [],
                    "module_output_keys": [],
                    "row_modules": row_modules,
                    "legacy_adapter_target": target,
                    "memory_boundary_decisions": {},
                    "memory_snapshot": runtime.memory_snapshot,
                },
            )

        user_result = snapshot_to_user_analysis_result(
            runtime.snapshot,
            standardized_labels=runtime.memory_snapshot.get("standardized_labels"),
        )
        payload = user_result.model_dump(mode="json")
        module_output_keys = [key for key in _USER_ANALYSIS_OUTPUT_KEYS if key in payload]
        if str(payload.get("uid") or "") != runtime.snapshot.uid:
            raw_failures.append("PROFILE_DAG_LEGACY_ADAPTER_MISMATCH")
        for key in module_output_keys:
            if payload.get(key) is not None and not _has_agent_output_shape(payload[key]):
                raw_failures.append("PROFILE_DAG_LEGACY_ADAPTER_MISMATCH")
        actual_decision = "blocked" if raw_failures else "allowed"
        normalized_failures = _dedupe(raw_failures)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=[],
            actual_failure_codes=normalized_failures,
        )
        failures.extend(_compare_required_values("output_keys", case.expected.get("required_output_keys", []), module_output_keys))
        return _build_result(
            case=case,
            check_kind="legacy_adapter",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=normalized_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "adapter",
                "check_kind": "legacy_adapter",
                "raw_decision": actual_decision,
                "run_status": runtime.run.status,
                "node_statuses": {node_run.node_key: node_run.status for node_run in runtime.snapshot.node_runs},
                "requested_modules": list(runtime.snapshot.requested_modules),
                "execution_closure": [
                    node_key
                    for node_key in _CANONICAL_NODE_ORDER
                    if node_key in resolve_execution_closure(list(runtime.snapshot.requested_modules))
                ],
                "event_types": [],
                "module_output_keys": module_output_keys,
                "legacy_adapter_target": target,
                "memory_boundary_decisions": {},
                "memory_snapshot": runtime.memory_snapshot,
            },
        )

    def _evaluate_memory_boundary(self, case: EvalCase) -> EvalResult:
        runtime = _execute_runtime_case(case.input, capture_events=False)
        memory_snapshot = runtime.memory_snapshot
        candidate = profile_snapshot_to_memory_candidate(memory_snapshot)
        requested_use = MemoryUsePurpose(str(case.input.get("metadata", {}).get("requested_use") or ""))
        decision = validate_memory_use(candidate, requested_use)
        actual_decision = "allowed" if decision.allowed else "blocked"
        raw_failures = [decision.blocked_by] if decision.blocked_by else []
        normalized_failures = _normalize_memory_boundary_codes(raw_failures, requested_use=requested_use)
        failures = _compare_common_expectations(
            expected=case.expected,
            actual_decision=actual_decision,
            actual_warning_codes=[],
            actual_failure_codes=normalized_failures,
        )
        failures.extend(
            _compare_required_values(
                "allowed_memory_uses",
                case.expected.get("allowed_memory_uses", []),
                memory_snapshot.get("allowed_memory_use", []),
            )
        )
        failures.extend(
            _compare_required_values(
                "forbidden_memory_uses",
                case.expected.get("forbidden_memory_uses", []),
                memory_snapshot.get("forbidden_memory_use", []),
            )
        )
        return _build_result(
            case=case,
            check_kind="memory_boundary",
            actual_decision=actual_decision,
            raw_warnings=[],
            normalized_warnings=[],
            raw_failures=raw_failures,
            normalized_failures=normalized_failures,
            failures=failures,
            artifacts={
                "policy_source": "runtime",
                "check_kind": "memory_boundary",
                "raw_decision": actual_decision,
                "run_status": runtime.run.status,
                "node_statuses": {node_run.node_key: node_run.status for node_run in runtime.snapshot.node_runs},
                "requested_modules": list(runtime.snapshot.requested_modules),
                "execution_closure": [
                    node_key
                    for node_key in _CANONICAL_NODE_ORDER
                    if node_key in resolve_execution_closure(list(runtime.snapshot.requested_modules))
                ],
                "event_types": [],
                "module_output_keys": list(runtime.snapshot.module_outputs.keys()),
                "memory_boundary_decisions": {
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "blocked_by": decision.blocked_by,
                    "requested_use": requested_use.value,
                },
                "raw_memory_use_decision": {
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "blocked_by": decision.blocked_by,
                    "requested_use": decision.requested_use.value,
                    "memory_source_type": decision.memory_source_type.value,
                    "authority_level": decision.authority_level.value,
                },
                "memory_snapshot": memory_snapshot,
            },
        )


class _FakeProfileSkill:
    def __init__(self, *, skill_name: str, payload: dict[str, Any] | None, failure_message: str | None) -> None:
        self._skill_name = skill_name
        self._payload = payload
        self._failure_message = failure_message

    def analyze(self, uid: str, **_: Any) -> dict[str, Any]:
        if self._failure_message:
            raise RuntimeError(self._failure_message)
        payload = dict(self._payload or _default_agent_output(self._skill_name))
        structured = payload.get("structured_result")
        if isinstance(structured, dict):
            payload["structured_result"] = dict(structured)
        payload.setdefault("summary", f"{self._skill_name} ok")
        payload.setdefault("charts", [])
        payload.setdefault("report_markdown", str(payload.get("summary") or f"{self._skill_name} ok"))
        return payload


def _execute_runtime_case(payload: dict[str, Any], *, capture_events: bool) -> _RuntimeArtifacts:
    events: list[dict[str, Any]] = []
    skill_map = {
        spec.skill_name: _FakeProfileSkill(
            skill_name=spec.skill_name,
            payload=dict((payload.get("fake_skill_outputs") or {}).get(spec.skill_name) or {})
            or None,
            failure_message=_extract_failure_message((payload.get("fake_skill_failures") or {}).get(spec.skill_name)),
        )
        for spec in PROFILE_NODE_SPECS
    }
    executor = ProfileDagExecutor(node_specs=PROFILE_NODE_SPECS, skill_map=skill_map, max_workers=1)
    run, snapshots = executor.run(
        uids=[str(uid) for uid in payload.get("uids", ["uid_001"])],
        requested_modules=[str(module) for module in payload.get("requested_modules", ["comprehensive"])],
        application_time=str(payload.get("application_time") or "2026-06-01T00:00:00"),
        country_code=str(payload.get("country_code") or "mx"),
        strict_data_mode=bool(payload.get("strict_data_mode", False)),
        source="test",
        progress_callback=events.append if capture_events else None,
    )
    snapshot = snapshots[0]
    memory_snapshot = build_profile_memory_snapshot(run, snapshot)
    return _RuntimeArtifacts(run=run, snapshot=snapshot, events=events, memory_snapshot=memory_snapshot)


def _runtime_contract_failures(case: EvalCase, runtime: _RuntimeArtifacts) -> list[str]:
    node_statuses = {node_run.node_key: node_run.status for node_run in runtime.snapshot.node_runs}
    raw_failures: list[str] = []
    expected_run_status = str(case.expected.get("required_run_status") or "").strip()
    if expected_run_status and runtime.run.status != expected_run_status:
        raw_failures.append("PROFILE_DAG_NODE_STATUS_MISMATCH")

    required_fields = [str(field) for field in case.expected.get("required_structured_fields", [])]
    if required_fields:
        for node_run in runtime.snapshot.node_runs:
            if node_run.status not in {"completed", "degraded"}:
                continue
            output_ref = node_run.output_ref if isinstance(node_run.output_ref, dict) else {}
            structured = output_ref.get("structured_result")
            if not isinstance(structured, dict):
                raw_failures.append("PROFILE_DAG_STRUCTURED_RESULT_MISSING")
                continue
            for field in required_fields:
                if field == "evidence_status" and not structured.get(field):
                    raw_failures.append("PROFILE_DAG_EVIDENCE_STATUS_MISSING")
                elif field not in structured:
                    raw_failures.append("PROFILE_DAG_STRUCTURED_RESULT_MISSING")

    if str(case.input.get("check_kind") or "") == "structured_output":
        for node_run in runtime.snapshot.node_runs:
            if node_run.node_key not in resolve_execution_closure(list(runtime.snapshot.requested_modules)):
                continue
            if node_run.status not in {"completed", "degraded"}:
                continue
            output_ref = node_run.output_ref if isinstance(node_run.output_ref, dict) else {}
            if not isinstance(output_ref.get("structured_result"), dict):
                raw_failures.append("PROFILE_DAG_STRUCTURED_RESULT_MISSING")

    expected_completed = [str(item) for item in case.expected.get("completed_nodes", [])]
    expected_failed = [str(item) for item in case.expected.get("failed_nodes", [])]
    expected_degraded = [str(item) for item in case.expected.get("degraded_nodes", [])]
    expected_skipped = [str(item) for item in case.expected.get("skipped_nodes", [])]
    for node_key in expected_completed:
        if node_statuses.get(node_key) != "completed":
            raw_failures.append("PROFILE_DAG_NODE_STATUS_MISMATCH")
    for node_key in expected_failed:
        if node_statuses.get(node_key) != "failed":
            raw_failures.append("PROFILE_DAG_NODE_STATUS_MISMATCH")
    for node_key in expected_degraded:
        if node_statuses.get(node_key) != "degraded":
            raw_failures.append("PROFILE_DAG_DEGRADED_STATUS_MISSING")
    closure = resolve_execution_closure(list(runtime.snapshot.requested_modules))
    for node_key in expected_skipped:
        if node_key in closure and node_statuses.get(node_key) != "skipped":
            raw_failures.append("PROFILE_DAG_DEPENDENCY_SKIP_MISSING")
        if node_key not in closure and node_key not in node_statuses:
            continue
        if node_key not in closure and node_statuses.get(node_key, "skipped") == "skipped":
            continue
    return _dedupe(raw_failures)


def _event_contract_failures(required_event_types: list[Any], events: list[dict[str, Any]]) -> list[str]:
    raw_failures: list[str] = []
    event_types = [str(event.get("type") or "") for event in events]
    for event_type in [str(item) for item in required_event_types]:
        if event_type not in event_types:
            raw_failures.append("PROFILE_DAG_EVENT_CONTRACT_MISSING")

    for event in events:
        event_type = str(event.get("type") or "")
        if event_type.startswith("profile_node_"):
            for key in ("profile_run_id", "node_run_id", "uid", "node_key", "skill_name", "stage", "status"):
                if event.get(key) is None:
                    raw_failures.append("PROFILE_DAG_EVENT_CONTRACT_MISSING")
        if event_type.startswith("profile_run_"):
            for key in ("profile_run_id", "requested_modules", "run_status"):
                if event.get(key) is None:
                    raw_failures.append("PROFILE_DAG_EVENT_CONTRACT_MISSING")
    return _dedupe(raw_failures)


def _compare_runtime_statuses(
    expected: dict[str, Any],
    *,
    node_statuses: dict[str, str],
    closure: set[str],
    snapshot: ProfileRunResultSnapshot,
) -> list[str]:
    failures: list[str] = []
    for node_key in [str(item) for item in expected.get("completed_nodes", [])]:
        if node_statuses.get(node_key) != "completed":
            failures.append(f"expected node {node_key} completed but got {node_statuses.get(node_key)}")
    for node_key in [str(item) for item in expected.get("failed_nodes", [])]:
        if node_statuses.get(node_key) != "failed":
            failures.append(f"expected node {node_key} failed but got {node_statuses.get(node_key)}")
    for node_key in [str(item) for item in expected.get("degraded_nodes", [])]:
        if node_statuses.get(node_key) != "degraded":
            failures.append(f"expected node {node_key} degraded but got {node_statuses.get(node_key)}")
    for node_key in [str(item) for item in expected.get("skipped_nodes", [])]:
        if node_key in closure and node_statuses.get(node_key) != "skipped":
            failures.append(f"expected node {node_key} skipped but got {node_statuses.get(node_key)}")
        if node_key not in closure and node_key not in node_statuses:
            continue
        if node_key not in closure and node_statuses.get(node_key, "skipped") == "skipped":
            continue

    expected_run_status = str(expected.get("required_run_status") or "").strip()
    if expected_run_status and snapshot.node_runs and snapshot.node_runs[0].profile_run_id:
        # run status is validated separately in runtime failures; keep human-readable text here too.
        pass
    return failures


def _compare_common_expectations(
    *,
    expected: dict[str, Any],
    actual_decision: str,
    actual_warning_codes: list[str],
    actual_failure_codes: list[str],
) -> list[str]:
    failures: list[str] = []
    expected_decision = str(expected.get("decision") or "").strip()
    if expected_decision and expected_decision != actual_decision:
        failures.append(f"expected decision {expected_decision} but got {actual_decision}")
    required_warning_codes = [str(code) for code in expected.get("required_warning_codes", [])]
    required_failure_codes = [str(code) for code in expected.get("required_failure_codes", [])]
    for code in required_warning_codes:
        if code not in actual_warning_codes:
            failures.append(f"expected warning code {code} but got {actual_warning_codes}")
    for code in required_failure_codes:
        if code not in actual_failure_codes:
            failures.append(f"expected failure code {code} but got {actual_failure_codes}")
    return failures


def _compare_required_values(label: str, expected: list[Any], actual: list[Any]) -> list[str]:
    expected_values = [str(value) for value in expected]
    actual_values = [str(value) for value in actual]
    failures: list[str] = []
    for value in expected_values:
        if value not in actual_values:
            failures.append(f"expected {label} to include {value} but got {actual_values}")
    return failures


def _normalize_memory_boundary_codes(raw_codes: list[str], *, requested_use: MemoryUsePurpose) -> list[str]:
    if not raw_codes:
        return []
    if requested_use is MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING:
        return ["PROFILE_DAG_PROFILE_RESULT_NOT_DATA_GROUNDING"]
    if requested_use is MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT:
        return ["PROFILE_DAG_PROFILE_RESULT_NOT_RISK_QA_SOURCE"]
    return ["PROFILE_DAG_MEMORY_BOUNDARY_VIOLATION"]


def _build_result(
    *,
    case: EvalCase,
    check_kind: str,
    actual_decision: str,
    raw_warnings: list[str],
    normalized_warnings: list[str],
    raw_failures: list[str],
    normalized_failures: list[str],
    failures: list[str],
    artifacts: dict[str, Any],
) -> EvalResult:
    return EvalResult(
        case_id=case.case_id,
        suite=case.suite,
        status="PASS" if not failures else "FAIL",
        passed=not failures,
        score=1.0 if not failures else 0.0,
        metrics={
            "check_kind": check_kind,
            "expected_decision": case.expected.get("decision"),
            "actual_decision": actual_decision,
            "actual_warning_codes": list(normalized_warnings),
            "actual_failure_codes": list(normalized_failures),
            "decision_match": not failures,
        },
        failures=failures,
        warnings=[],
        artifacts={
            **artifacts,
            "raw_warnings": list(raw_warnings),
            "normalized_warnings": list(normalized_warnings),
            "raw_failures": list(raw_failures),
            "normalized_failures": list(normalized_failures),
        },
    )


def _default_agent_output(skill_name: str) -> dict[str, Any]:
    return {
        "summary": f"{skill_name} ok",
        "structured_result": {
            "status": "ok",
            "evidence_status": "grounded",
        },
        "charts": [],
        "report_markdown": f"{skill_name} ok",
    }


def _extract_failure_message(value: Any) -> str | None:
    if isinstance(value, dict):
        message = str(value.get("message") or "").strip()
        return message or None
    text = str(value or "").strip()
    return text or None


def _has_agent_output_shape(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("summary"), str):
        return False
    if not isinstance(payload.get("report_markdown"), str):
        return False
    if not isinstance(payload.get("structured_result"), dict):
        return False
    return True


def _pass_rate(results: list[EvalResult]) -> float:
    if not results:
        return 1.0
    return round(sum(1 for result in results if result.passed) / len(results), 6)


def _ratio(results: list[EvalResult], predicate) -> float:
    if not results:
        return 1.0
    return round(sum(1 for result in results if predicate(result)) / len(results), 6)


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped
