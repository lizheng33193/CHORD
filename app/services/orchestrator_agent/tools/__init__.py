"""Orchestrator Agent tools registry with lazy imports.

Keep tool loading lightweight so generic orchestrator imports do not pull in
optional Data Agent execution dependencies unless `query_data` is actually used.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any


_TOOL_EXPORTS = {
    "parse_uid_file": "app.services.orchestrator_agent.tools.parse_uid_file",
    "run_profile": "app.services.orchestrator_agent.tools.run_profile",
    "run_trace": "app.services.orchestrator_agent.tools.run_trace",
    "query_data": "app.services.orchestrator_agent.tools.query_data",
    "memory_write": "app.services.orchestrator_agent.tools.memory",
    "memory_read": "app.services.orchestrator_agent.tools.memory",
    "memory": "app.services.orchestrator_agent.tools.memory",
}

__all__ = [*list(_TOOL_EXPORTS.keys()), "get_tool_registry"]


class LazyTool:
    """Lazy callable wrapper that preserves attribute access."""

    def __init__(self, name: str):
        self.name = name

    def _load(self) -> Any:
        return getattr(sys.modules[__name__], self.name)

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._load(), attr)

    def __call__(self, *args, **kwargs):
        tool = self._load()
        return tool(*args, **kwargs)


def __getattr__(name: str) -> Any:
    module_path = _TOOL_EXPORTS.get(name)
    if not module_path:
        raise AttributeError(name)
    module = importlib.import_module(module_path)
    if name == "memory":
        globals()[name] = module
        return module
    value = getattr(module, name)
    globals()[name] = value
    return value


def get_tool_registry() -> dict[str, Any]:
    return {name: LazyTool(name) for name in _TOOL_EXPORTS if name != "memory"}
