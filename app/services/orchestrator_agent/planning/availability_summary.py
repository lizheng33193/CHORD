"""Formatting helpers for availability summaries."""

from __future__ import annotations

from app.services.orchestrator_agent.schemas import DataAvailability


def availability_summary(availability: DataAvailability) -> str:
    parts: list[str] = []
    for row in availability.per_uid:
        available = "/".join(row.available_buckets) if row.available_buckets else "none"
        missing = "/".join(row.missing_buckets) if row.missing_buckets else "none"
        parts.append(f"{row.uid}: available={available}; missing={missing}")
    return " | ".join(parts) if parts else "暂无可用性结果"
