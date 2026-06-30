"""Static module-level Profile DAG executor."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any, Callable

from app.services.profile_dag.adapters import classify_module_payload
from app.services.profile_dag.contracts import (
    ProfileNodeRun,
    ProfileRun,
    ProfileRunResultSnapshot,
    make_profile_node_run_id,
    make_profile_run_id,
    utcnow,
)
from app.services.profile_dag.events import (
    build_profile_node_started_event,
    build_profile_node_terminal_event,
    build_profile_run_started_event,
    build_profile_run_terminal_event,
)
from app.services.profile_dag.node_registry import (
    NODE_KEY_TO_SPEC,
    PROFILE_NODE_SPECS,
    resolve_execution_closure,
)


class ProfileDagExecutor:
    def __init__(
        self,
        *,
        node_specs=PROFILE_NODE_SPECS,
        skill_map: dict[str, Any],
        cache_get: Callable[[str, str, str | None, str], dict[str, Any] | None] | None = None,
        cache_set: Callable[[str, str, str | None, str, dict[str, Any]], None] | None = None,
        max_workers: int = 3,
    ) -> None:
        self.node_specs = tuple(node_specs)
        self.skill_map = dict(skill_map)
        self.cache_get = cache_get
        self.cache_set = cache_set
        self.max_workers = max_workers

    @staticmethod
    def _can_run_with_failed_dependencies(spec, node_runs: dict[str, ProfileNodeRun]) -> bool:
        if spec.node_key != "comprehensive":
            return False
        return any(
            node_runs.get(dep) is not None and node_runs[dep].status == "failed"
            for dep in spec.depends_on
        )

    def run(
        self,
        *,
        uids: list[str],
        requested_modules: list[str],
        application_time: str | None,
        country_code: str,
        strict_data_mode: bool,
        source: str,
        repository: Any | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        request_id: str | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[ProfileRun, list[ProfileRunResultSnapshot]]:
        requested = list(dict.fromkeys(requested_modules))
        run = ProfileRun(
            run_id=make_profile_run_id(),
            source=source,
            uids=list(uids),
            requested_modules=requested,
            country_code=country_code,
            application_time=application_time,
            strict_data_mode=strict_data_mode,
            status="running",
            trace_id=trace_id,
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            created_at=utcnow(),
            started_at=utcnow(),
        )
        if progress_callback is not None:
            progress_callback(build_profile_run_started_event(run).to_payload())

        snapshots = [
            self._run_uid(
                uid=uid,
                profile_run=run,
                requested_modules=requested,
                application_time=application_time,
                country_code=country_code,
                repository=repository,
                progress_callback=progress_callback,
            )
            for uid in uids
        ]

        run.status = self._resolve_run_status(snapshots, requested)
        run.finished_at = utcnow()
        if run.status == "failed":
            run.error = {"message": "All requested profile roots failed."}
        if progress_callback is not None:
            progress_callback(build_profile_run_terminal_event(run).to_payload())
        return run, snapshots

    def _run_uid(
        self,
        *,
        uid: str,
        profile_run: ProfileRun,
        requested_modules: list[str],
        application_time: str | None,
        country_code: str,
        repository: Any | None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> ProfileRunResultSnapshot:
        closure = resolve_execution_closure(requested_modules)
        outputs: dict[str, dict[str, Any] | None] = {}
        node_runs: dict[str, ProfileNodeRun] = {}
        cache_hits = 0
        cache_misses = 0

        for spec in self.node_specs:
            if spec.node_key in closure:
                continue
            node_run = ProfileNodeRun(
                node_run_id=make_profile_node_run_id(),
                profile_run_id=profile_run.run_id,
                uid=uid,
                node_key=spec.node_key,
                skill_name=spec.skill_name,
                stage=spec.stage,
                depends_on=list(spec.depends_on),
                upstream_node_run_ids=[],
                status="skipped",
                attempt=0,
                started_at=utcnow(),
                finished_at=utcnow(),
                skip_reason="not_requested",
            )
            node_runs[spec.node_key] = node_run
            outputs[spec.node_key] = None
            if progress_callback is not None:
                progress_callback(build_profile_node_terminal_event(node_run).to_payload())

        stages = sorted({spec.stage for spec in self.node_specs})
        for stage in stages:
            runnable_specs = []
            for spec in self.node_specs:
                if spec.stage != stage or spec.node_key not in closure:
                    continue
                blocked_deps = [
                    dep for dep in spec.depends_on
                    if node_runs.get(dep) is not None and node_runs[dep].status == "failed"
                ]
                if blocked_deps and not self._can_run_with_failed_dependencies(spec, node_runs):
                    node_run = ProfileNodeRun(
                        node_run_id=make_profile_node_run_id(),
                        profile_run_id=profile_run.run_id,
                        uid=uid,
                        node_key=spec.node_key,
                        skill_name=spec.skill_name,
                        stage=spec.stage,
                        depends_on=list(spec.depends_on),
                        upstream_node_run_ids=[node_runs[dep].node_run_id for dep in blocked_deps if dep in node_runs],
                        status="skipped",
                        attempt=0,
                        started_at=utcnow(),
                        finished_at=utcnow(),
                        skip_reason=f"dependency_failed:{','.join(blocked_deps)}",
                        error={"message": f"Dependency failed: {', '.join(blocked_deps)}"},
                    )
                    node_runs[spec.node_key] = node_run
                    outputs[spec.node_key] = None
                    if progress_callback is not None:
                        progress_callback(build_profile_node_terminal_event(node_run).to_payload())
                    continue
                runnable_specs.append(spec)

            if not runnable_specs:
                continue

            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(runnable_specs))) as pool:
                futures = [
                    pool.submit(
                        self._execute_node,
                        spec=spec,
                        uid=uid,
                        profile_run=profile_run,
                        outputs=outputs,
                        node_runs=node_runs,
                        repository=repository,
                        application_time=application_time,
                        country_code=country_code,
                        progress_callback=progress_callback,
                    )
                    for spec in runnable_specs
                ]
                for future in futures:
                    node_run = future.result()
                    node_runs[node_run.node_key] = node_run
                    outputs[node_run.node_key] = node_run.output_ref
                    if node_run.cache_status == "hit":
                        cache_hits += 1
                    elif node_run.cache_status == "miss":
                        cache_misses += 1

        ordered_node_runs = [node_runs[spec.node_key] for spec in self.node_specs]
        return ProfileRunResultSnapshot(
            uid=uid,
            requested_modules=list(requested_modules),
            module_outputs=outputs,
            node_runs=ordered_node_runs,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
        )

    def _execute_node(
        self,
        *,
        spec,
        uid: str,
        profile_run: ProfileRun,
        outputs: dict[str, dict[str, Any] | None],
        node_runs: dict[str, ProfileNodeRun],
        repository: Any | None,
        application_time: str | None,
        country_code: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> ProfileNodeRun:
        node_run = ProfileNodeRun(
            node_run_id=make_profile_node_run_id(),
            profile_run_id=profile_run.run_id,
            uid=uid,
            node_key=spec.node_key,
            skill_name=spec.skill_name,
            stage=spec.stage,
            depends_on=list(spec.depends_on),
            upstream_node_run_ids=[node_runs[dep].node_run_id for dep in spec.depends_on if dep in node_runs],
            status="running",
            attempt=1,
            started_at=utcnow(),
            input_ref={
                "uid": uid,
                "application_time": application_time,
                "country_code": country_code,
                "dependency_statuses": {
                    dep: node_runs[dep].status for dep in spec.depends_on if dep in node_runs
                },
            },
        )
        if progress_callback is not None:
            progress_callback(build_profile_node_started_event(node_run).to_payload())
        started = perf_counter()
        try:
            cached = None
            if self.cache_get is not None:
                cached = self.cache_get(uid, spec.node_key, application_time, country_code)
            if cached is not None:
                output = dict(cached)
                node_run.cache_status = "hit"
            else:
                skill = self.skill_map[spec.skill_name]
                kwargs: dict[str, Any] = {
                    "repository": repository,
                    "application_time": application_time,
                    "country_code": country_code,
                }
                for dep in spec.depends_on:
                    dep_spec = NODE_KEY_TO_SPEC[dep]
                    kwargs[f"{dep_spec.skill_name}_result"] = outputs.get(dep, {}) or {}
                output = skill.analyze(uid=uid, **kwargs)
                node_run.cache_status = "miss"
                if self.cache_set is not None:
                    self.cache_set(uid, spec.node_key, application_time, country_code, output)

            status, result_status = classify_module_payload(output)
            if status == "completed" and any(
                node_runs[dep].status in {"failed", "degraded", "skipped"}
                for dep in spec.depends_on
                if dep in node_runs
            ):
                status = "degraded"
            node_run.status = status
            node_run.output_ref = output
            node_run.result_status = result_status
        except Exception as exc:  # noqa: BLE001
            node_run.status = "failed"
            node_run.output_ref = None
            node_run.result_status = "failed"
            node_run.error = {"message": str(exc)}
        node_run.finished_at = utcnow()
        node_run.duration_ms = int((perf_counter() - started) * 1000)
        if progress_callback is not None:
            progress_callback(build_profile_node_terminal_event(node_run).to_payload())
        return node_run

    @staticmethod
    def _resolve_run_status(
        snapshots: list[ProfileRunResultSnapshot],
        requested_modules: list[str],
    ) -> str:
        requested = set(requested_modules)
        root_statuses = [
            node_run.status
            for snapshot in snapshots
            for node_run in snapshot.node_runs
            if node_run.node_key in requested
        ]
        if root_statuses and all(status == "failed" for status in root_statuses):
            return "failed"
        if any(status in {"degraded", "skipped", "failed"} for status in root_statuses):
            return "completed_with_degradation"
        return "completed"
