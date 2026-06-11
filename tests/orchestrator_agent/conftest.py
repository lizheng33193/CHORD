"""Phase 1 / Errata E2 — settings 单例隔离 + memory _project_root monkeypatch fixture。

放在 `tests/orchestrator_agent/` 下作用域，仅覆盖该目录下的 memory tool / loop 测试，
不影响项目根 conftest 的 `_redirect_orchestrator_outputs`。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_memory_root(tmp_path, monkeypatch):
    """每个 orchestrator_agent 测试结束后还原 _project_root，避免跨 test 污染。

    顺序：
      1. monkeypatch tools.memory._project_root → tmp_path（隔离 four-class / legacy 路径）
      2. 清理可能被别的 test 污染的 settings 缓存（V1 settings 是模块级单例 → 没有 _cached_settings 字段，
         留 try/except 兜底，未来 V2 改 Annotated[Settings, Depends(...)] 时此处不需要改动）
    """
    from app.services.orchestrator_agent import memory_store
    from app.services.orchestrator_agent.tools import memory as memory_mod

    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.memory._project_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(memory_store, "_project_root", lambda: tmp_path)
    yield
    try:
        from app.core import config as cfg_mod

        if hasattr(cfg_mod, "_cached_settings"):
            cfg_mod._cached_settings = None
    except ImportError:
        pass
