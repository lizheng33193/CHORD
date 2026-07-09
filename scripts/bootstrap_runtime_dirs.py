from __future__ import annotations

from pathlib import Path


RUNTIME_DIRS = [
    "outputs",
    "outputs/memory",
    "outputs/memory/vector",
    "outputs/risk_knowledge",
    "outputs/evals",
    "outputs/orchestrator_sessions",
    "storage",
    "storage/risk_knowledge",
    "storage/risk_knowledge/uploads",
]


def main() -> None:
    for item in RUNTIME_DIRS:
        path = Path(item)
        path.mkdir(parents=True, exist_ok=True)
        print(f"ready: {path}")


if __name__ == "__main__":
    main()
