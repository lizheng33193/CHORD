from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_IMPORT_PATTERNS = (
    re.compile(r"^\s*from\s+.*agent_loop\s+import\s+", re.MULTILINE),
    re.compile(r"^\s*import\s+.*agent_loop\b", re.MULTILINE),
)
SCAN_DIRS = (
    REPO_ROOT / "app/services/orchestrator_agent/flows",
    REPO_ROOT / "app/services/orchestrator_agent/execution",
    REPO_ROOT / "app/services/orchestrator_agent/runtime",
    REPO_ROOT / "app/services/orchestrator_agent/finalization",
    REPO_ROOT / "app/services/orchestrator_agent/planning",
)


def test_no_runtime_module_imports_agent_loop() -> None:
    hits: list[str] = []

    for scan_dir in SCAN_DIRS:
        for path in scan_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_IMPORT_PATTERNS:
                for match in pattern.finditer(text):
                    lineno = text[: match.start()].count("\n") + 1
                    relpath = path.relative_to(REPO_ROOT)
                    hits.append(f"{relpath}:{lineno}: {match.group(0).strip()}")

    assert not hits, "Unexpected agent_loop imports:\n" + "\n".join(hits)
