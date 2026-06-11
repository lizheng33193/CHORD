"""Pytest config: register --refresh-fixtures flag for golden test recording."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--refresh-fixtures",
        action="store_true",
        default=False,
        help="Re-record golden fixtures by calling real LLM. "
        "Use after intentional prompt changes; otherwise leave off so tests "
        "read from tests/fixtures/golden/.",
    )


@pytest.fixture
def refresh_fixtures(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--refresh-fixtures"))


@pytest.fixture(autouse=True)
def _redirect_orchestrator_outputs(tmp_path, monkeypatch):
    """Auto-redirect orchestrator session/memory dirs to tmp_path during tests."""
    try:
        from app.services.orchestrator_agent import memory_store, session_store
        from app.services.orchestrator_agent.tools import memory as memory_mod
    except ImportError:
        # Phase 1 RED 阶段模块不存在，跳过重定向（测试会以 ImportError 失败 → RED 预期）
        return
    monkeypatch.setattr(
        session_store, "_sessions_dir",
        lambda: tmp_path / "orchestrator_sessions",
    )
    monkeypatch.setattr(
        memory_mod, "_project_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        memory_store, "_project_root",
        lambda: tmp_path,
    )
