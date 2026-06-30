from __future__ import annotations

from pathlib import Path


def test_evidence_layer_has_no_dashscope_imports() -> None:
    evidence_root = Path(__file__).resolve().parents[3] / "app" / "risk_knowledge" / "evidence"
    py_files = sorted(evidence_root.glob("*.py"))
    assert py_files
    for path in py_files:
        content = path.read_text(encoding="utf-8")
        assert "dashscope" not in content.lower(), f"unexpected dashscope reference in {path.name}"
