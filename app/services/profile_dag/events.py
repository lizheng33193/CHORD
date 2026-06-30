"""Profile DAG event builders."""

from __future__ import annotations

from app.services.profile_dag.contracts import ProfileNodeEvent, ProfileNodeRun, ProfileRun


def build_profile_run_started_event(run: ProfileRun) -> ProfileNodeEvent:
    return ProfileNodeEvent(
        type="profile_run_started",
        profile_run_id=run.run_id,
        requested_modules=list(run.requested_modules),
        run_status=run.status,
    )


def build_profile_run_terminal_event(run: ProfileRun) -> ProfileNodeEvent:
    return ProfileNodeEvent(
        type="profile_run_failed" if run.status == "failed" else "profile_run_completed",
        profile_run_id=run.run_id,
        requested_modules=list(run.requested_modules),
        run_status=run.status,
        error=run.error,
    )


def build_profile_node_started_event(run: ProfileNodeRun) -> ProfileNodeEvent:
    return ProfileNodeEvent(
        type="profile_node_started",
        profile_run_id=run.profile_run_id,
        node_run_id=run.node_run_id,
        uid=run.uid,
        node_key=run.node_key,
        skill_name=run.skill_name,
        stage=run.stage,
        status=run.status,
        cache_status=run.cache_status,
        upstream_node_run_ids=list(run.upstream_node_run_ids),
    )


def build_profile_node_terminal_event(run: ProfileNodeRun) -> ProfileNodeEvent:
    if run.status == "failed":
        event_type = "profile_node_failed"
    elif run.status == "skipped":
        event_type = "profile_node_skipped"
    else:
        event_type = "profile_node_completed"
    return ProfileNodeEvent(
        type=event_type,
        profile_run_id=run.profile_run_id,
        node_run_id=run.node_run_id,
        uid=run.uid,
        node_key=run.node_key,
        skill_name=run.skill_name,
        stage=run.stage,
        status=run.status,
        duration_ms=run.duration_ms,
        cache_status=run.cache_status,
        upstream_node_run_ids=list(run.upstream_node_run_ids),
        error=run.error,
        output=run.output_ref,
    )
