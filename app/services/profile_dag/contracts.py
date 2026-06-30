"""Internal contracts for the Profile DAG runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

ProfileNodeStatus = Literal["pending", "running", "completed", "failed", "skipped", "degraded"]
ProfileRunStatus = Literal[
    "pending",
    "running",
    "completed",
    "completed_with_degradation",
    "failed",
    "cancelled",
]
ProfileRunSource = Literal["api_analyze", "api_analyze_stream", "chat_run_profile", "internal", "test"]
ProfileEventType = Literal[
    "profile_run_started",
    "profile_node_started",
    "profile_node_completed",
    "profile_node_failed",
    "profile_node_skipped",
    "profile_run_completed",
    "profile_run_failed",
]
ProfileCacheStatus = Literal["hit", "miss", "not_applicable"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_profile_run_id() -> str:
    return f"pr_{uuid4().hex}"


def make_profile_node_run_id() -> str:
    return f"pnr_{uuid4().hex}"


@dataclass(slots=True, frozen=True)
class ProfileNodeSpec:
    node_key: str
    module: str
    skill_name: str
    result_key: str
    label: str
    stage: int
    depends_on: list[str]


@dataclass(slots=True)
class ProfileRun:
    run_id: str
    source: ProfileRunSource
    uids: list[str]
    requested_modules: list[str]
    country_code: str
    application_time: str | None
    strict_data_mode: bool
    status: ProfileRunStatus
    trace_id: str | None
    session_id: str | None
    turn_id: str | None
    request_id: str | None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: dict[str, Any] | None = None


@dataclass(slots=True)
class ProfileNodeRun:
    node_run_id: str
    profile_run_id: str
    uid: str
    node_key: str
    skill_name: str
    stage: int
    depends_on: list[str]
    upstream_node_run_ids: list[str]
    status: ProfileNodeStatus
    attempt: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int = 0
    input_ref: dict[str, Any] | None = None
    output_ref: dict[str, Any] | None = None
    result_status: str | None = None
    error: dict[str, Any] | None = None
    skip_reason: str | None = None
    cache_status: ProfileCacheStatus = "not_applicable"


@dataclass(slots=True)
class ProfileNodeEvent:
    type: ProfileEventType
    profile_run_id: str
    node_run_id: str | None = None
    uid: str | None = None
    node_key: str | None = None
    skill_name: str | None = None
    stage: int | None = None
    status: str | None = None
    duration_ms: int | None = None
    cache_status: ProfileCacheStatus | None = None
    upstream_node_run_ids: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    requested_modules: list[str] = field(default_factory=list)
    run_status: ProfileRunStatus | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "profile_run_id": self.profile_run_id,
            "node_run_id": self.node_run_id,
            "uid": self.uid,
            "node_key": self.node_key,
            "skill_name": self.skill_name,
            "stage": self.stage,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "cache_status": self.cache_status,
            "upstream_node_run_ids": list(self.upstream_node_run_ids),
            "error": self.error,
            "output": self.output,
            "requested_modules": list(self.requested_modules),
            "run_status": self.run_status,
        }


@dataclass(slots=True)
class ProfileRunResultSnapshot:
    uid: str
    requested_modules: list[str]
    module_outputs: dict[str, dict[str, Any] | None]
    node_runs: list[ProfileNodeRun]
    cache_hits: int = 0
    cache_misses: int = 0

