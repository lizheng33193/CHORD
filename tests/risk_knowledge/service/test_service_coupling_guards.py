from __future__ import annotations

from pathlib import Path


_FORBIDDEN_TERMS = (
    "app.third_party.swxy_rag",
    "file_parse_core",
    "retrieval_core",
    "elasticsearch",
    "dataagent",
    "sql rag",
    "document upload",
    "admin api",
)


def test_risk_knowledge_service_layer_has_no_forbidden_runtime_coupling() -> None:
    service_root = Path(__file__).resolve().parents[3] / "app" / "risk_knowledge" / "service"
    py_files = sorted(service_root.glob("*.py"))
    assert py_files
    for path in py_files:
        content = path.read_text(encoding="utf-8").lower()
        for term in _FORBIDDEN_TERMS:
            assert term not in content, f"unexpected coupling term {term!r} in {path.name}"


def test_risk_knowledge_flow_has_no_tool_registry_or_data_agent_coupling() -> None:
    flow_path = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "services"
        / "orchestrator_agent"
        / "flows"
        / "risk_knowledge_answer.py"
    )
    content = flow_path.read_text(encoding="utf-8").lower()
    assert "get_tool_registry" not in content
    assert "dataagent" not in content
    assert "query_data" not in content
