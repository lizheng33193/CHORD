"""Common helpers for repo-local skill CLI scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def bootstrap_repo_root() -> Path:
    """Add the repository root to sys.path and return it."""
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    return repo_root


def dump_json(data: Any, output_path: str | None) -> None:
    """Write JSON to a file or stdout."""
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(rendered + "\n", encoding="utf-8")
        return
    print(rendered)


def load_json(input_path: str) -> Any:
    """Load JSON from a file path."""
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def get_local_repository() -> Any:
    """Instantiate the repository backed by local sample data."""
    bootstrap_repo_root()
    from app.repositories.local_repository import LocalUserRepository

    return LocalUserRepository()


def unwrap_structured_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept either a full agent output or a structured_result object."""
    structured_result = payload.get("structured_result")
    if isinstance(structured_result, dict):
        return structured_result
    return payload


def unwrap_charts(payload: Any) -> list[dict[str, Any]]:
    """Accept a chart list, a full module output, or a full API payload."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    charts = payload.get("charts")
    if isinstance(charts, list):
        return [item for item in charts if isinstance(item, dict)]

    results = payload.get("results")
    if not isinstance(results, list):
        return []

    collected: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        for section in (
            "app_profile",
            "behavior_profile",
            "credit_profile",
            "comprehensive_profile",
        ):
            module_output = result.get(section)
            if not isinstance(module_output, dict):
                continue
            module_charts = module_output.get("charts")
            if isinstance(module_charts, list):
                collected.extend(item for item in module_charts if isinstance(item, dict))
    return collected

