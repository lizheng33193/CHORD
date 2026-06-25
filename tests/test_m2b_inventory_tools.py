from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_inventory_scans_files_without_leaking_sensitive_values(tmp_path: Path) -> None:
    source_dir = tmp_path / "knowledge-base"
    source_dir.mkdir()
    (source_dir / "多国业务逻辑.md").write_text(
        "# mob1\n首贷 + 完全结清 + 7天未复借流失\n",
        encoding="utf-8",
    )
    (source_dir / "few.md").write_text(
        "conn = pymysql.connect(host='10.20.84.10', user='demo_user', password='super-secret')\n",
        encoding="utf-8",
    )
    (source_dir / ".DS_Store").write_text("ignore-me", encoding="utf-8")

    from scripts.knowledge_base_inventory import build_inventory, render_inventory_markdown

    entries = build_inventory(source_dir)

    assert [entry.source_file for entry in entries] == ["few.md", "多国业务逻辑.md"]

    few_entry = next(entry for entry in entries if entry.source_file == "few.md")
    assert few_entry.contains_sensitive_info is True
    assert few_entry.sensitive_categories == ["host", "password", "user", "ip", "connection_string"]
    assert few_entry.runtime_allowed == "sanitized_only"

    logic_entry = next(entry for entry in entries if entry.source_file == "多国业务逻辑.md")
    assert logic_entry.source_type == "business_logic"
    assert logic_entry.useful_asset_types == ["glossary_term", "business_rule", "cohort_definition"]
    assert logic_entry.runtime_allowed == "no_raw_runtime"

    rendered = render_inventory_markdown(entries, source_dir=source_dir)

    assert "super-secret" not in rendered
    assert "10.20.84.10" not in rendered
    assert ".DS_Store" not in rendered
    assert "ignored files" in rendered.lower()


def test_template_baseline_runner_is_deterministic_and_validates_duplicates(tmp_path: Path) -> None:
    golden_set = tmp_path / "golden_set.yaml"
    golden_set.write_text(
        """
cases:
  - case_id: mx-high-risk-cohort
    country: mx
    domain: risk
    run_type: cohort_query
    output_bucket: null
    request: 找最近 7 天高风险用户
    expected_tables: [hive.dwd.dwd_w_apply]
    expected_fields: [user_uuid, risk_level, apply_time, dt]
    expected_glossary_terms: [high_risk, recent_7d]
    expected_sql_examples: []
    forbidden_examples: [fixed_historical_date_copy]
    notes:
      - dt can be used for partition pruning but should not replace the business time field.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    from scripts.run_m2b_retrieval_baseline import build_template_results, load_golden_cases

    cases = load_golden_cases(golden_set)
    payload = build_template_results(cases, generated_at="template")

    assert payload["generated_at"] == "template"
    assert payload["run_mode"] == "template"
    assert payload["retriever"] == "not_connected"
    assert payload["cases"][0]["case_id"] == "mx-high-risk-cohort"
    assert payload["cases"][0]["judgment"] == "todo"
    assert payload["cases"][0]["retrieved_tables"] == []

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    assert "Real retriever adapter is intentionally out of M2B-0 scope." in rendered

    golden_set.write_text(
        """
cases:
  - case_id: duplicate-case
    country: mx
    domain: risk
    run_type: cohort_query
    output_bucket: null
    request: one
    expected_tables: []
    expected_fields: []
    expected_glossary_terms: []
    expected_sql_examples: []
    forbidden_examples: []
    notes: []
  - case_id: duplicate-case
    country: mx
    domain: risk
    run_type: cohort_query
    output_bucket: null
    request: two
    expected_tables: []
    expected_fields: []
    expected_glossary_terms: []
    expected_sql_examples: []
    forbidden_examples: []
    notes: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate case_id"):
        load_golden_cases(golden_set)
