from __future__ import annotations

from pathlib import Path


def test_admin_layer_does_not_import_forbidden_runtime_modules() -> None:
    admin_dir = Path(__file__).resolve().parents[3] / "app" / "risk_knowledge" / "admin"
    forbidden_imports = (
        "app.third_party.swxy_rag",
        "retrieval_core",
        "elasticsearch",
        "app.data_agent",
        "app.ui",
        "frontend",
    )

    for path in admin_dir.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        for forbidden in forbidden_imports:
            assert forbidden not in content, f"{path.name} must not import {forbidden}"
