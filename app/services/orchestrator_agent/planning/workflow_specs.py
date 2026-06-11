"""Declarative workflow specs for known orchestrator intents."""

from __future__ import annotations

from typing import Any


KNOWN_WORKFLOW_SPECS: dict[str, dict[str, Any]] = {
    "answer_from_workspace": {
        "required_slots": [],
        "allowed_tools": [],
        "review_policy": "workspace_review",
    },
    "profile_uid": {
        "required_slots": ["uid"],
        "allowed_tools": ["run_profile", "repair_profile_data"],
        "review_policy": "profile_review",
    },
    "profile_batch": {
        "required_slots": ["uids"],
        "allowed_tools": ["parse_uid_file", "run_profile", "repair_profile_data"],
        "review_policy": "profile_review",
    },
    "query_data_then_profile": {
        "required_slots": ["country", "time_window"],
        "allowed_tools": ["query_data", "run_profile", "repair_profile_data"],
        "review_policy": "cohort_profile_review",
    },
    "run_trace": {
        "required_slots": ["uid"],
        "allowed_tools": ["run_trace"],
        "review_policy": "trace_review",
    },
}
