from __future__ import annotations

from app.risk_knowledge.context import ContextBuildRequest, RiskQaContextBuilder


def test_risk_qa_context_allows_only_risk_domain_knowledge() -> None:
    result = RiskQaContextBuilder().build(
        ContextBuildRequest(
            task_type="risk_knowledge_answer",
            query="什么是多头借贷风险？",
            selected_evidence_ids=["ev_risk_1"],
        )
    )

    assert result.allowed_context_sources == ["risk_domain_knowledge"]
    assert "data_knowledge" in result.blocked_context_sources
    assert "sql_examples" in result.blocked_context_sources
    assert "sql_error_cases" in result.blocked_context_sources
    assert "catalog_grounding" in result.blocked_context_sources
    assert "memory_as_authority" in result.blocked_context_sources
    assert result.context_hash


def test_data_agent_context_blocks_risk_domain_field_grounding() -> None:
    result = RiskQaContextBuilder().build(
        ContextBuildRequest(
            task_type="data_agent",
            query="生成 SQL 查询首贷从未逾期用户",
            selected_evidence_ids=[],
        )
    )

    assert result.allowed_context_sources == ["data_knowledge"]
    assert "risk_domain_knowledge_as_field_grounding" in result.blocked_context_sources
