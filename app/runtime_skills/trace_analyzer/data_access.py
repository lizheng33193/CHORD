"""Data access layer for the trace_analyzer pipeline.

Reads raw event CSV from {settings.data_dir}/behavior/by_uid/{uid}.csv.
See docs/specs/trace-analyzer-design.md §2.Q2 + §3.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.core.logger import get_logger
from app.runtime_skills.trace_analyzer.contracts import (
    TraceRawData,
    TraceRunContext,
)

logger = get_logger(__name__)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "uid",
    "servertimestamp",
    "timestamp_",
    "scenetype",
    "processtype",
    "eventname",
    "extend",
    "clientmodel",
    "clientosversion",
    "url",
    "refer",
    "ip",
)


class TraceDataAccess:
    """Read raw behavior events for a single uid (no aggregation)."""

    def fetch(self, uid: str, context: TraceRunContext) -> TraceRawData:
        path = Path(settings.data_dir) / "behavior" / "by_uid" / f"{uid}.csv"
        if not path.exists():
            return {
                "uid": uid,
                "events_df": pd.DataFrame(columns=list(REQUIRED_COLUMNS)),
                "data_status": "data_missing",
                "errors": [f"csv_not_found:{path}"],
            }
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
        except Exception as exc:
            logger.warning("trace data_access read_csv failed uid=%s err=%s", uid, exc)
            return {
                "uid": uid,
                "events_df": pd.DataFrame(columns=list(REQUIRED_COLUMNS)),
                "data_status": "error",
                "errors": [f"csv_parse_error:{exc.__class__.__name__}"],
            }
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            return {
                "uid": uid,
                "events_df": pd.DataFrame(columns=list(REQUIRED_COLUMNS)),
                "data_status": "error",
                "errors": [f"column_schema_mismatch:missing={missing}"],
            }
        return {
            "uid": uid,
            "events_df": df,
            "data_status": "ok",
            "errors": [],
        }
