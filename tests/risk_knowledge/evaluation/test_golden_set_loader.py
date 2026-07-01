from __future__ import annotations

from pathlib import Path

import pytest


def test_golden_set_loader_loads_jsonl_cases(sample_golden_path: Path) -> None:
    from app.risk_knowledge.evaluation.golden_set_loader import load_golden_cases

    cases = load_golden_cases(sample_golden_path)

    assert len(cases) == 10
    assert cases[0].case_id == "rk_eval_001"
    assert cases[2].intent == "profile_explanation"


def test_golden_set_loader_rejects_unknown_expected_behavior(tmp_path: Path) -> None:
    from app.risk_knowledge.evaluation.errors import GoldenSetSchemaError
    from app.risk_knowledge.evaluation.golden_set_loader import load_golden_cases

    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(
        '{"case_id":"bad","query":"x","kb_id":"risk_domain_knowledge","document_id":null,"version_id":null,"intent":"risk_knowledge_qa","expected_behavior":"wrong","expected_evidence":[],"expected_answer_points":[],"expected_citation_refs":[],"expected_refusal_reason":null,"tags":[],"difficulty":"easy"}\n',
        encoding="utf-8",
    )

    with pytest.raises(GoldenSetSchemaError):
        load_golden_cases(dataset)


def test_golden_set_loader_rejects_missing_required_field(tmp_path: Path) -> None:
    from app.risk_knowledge.evaluation.errors import GoldenSetSchemaError
    from app.risk_knowledge.evaluation.golden_set_loader import load_golden_cases

    dataset = tmp_path / "bad.jsonl"
    dataset.write_text('{"case_id":"bad","kb_id":"risk_domain_knowledge"}\n', encoding="utf-8")

    with pytest.raises(GoldenSetSchemaError):
        load_golden_cases(dataset)
