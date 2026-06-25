from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


def write_yaml(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def make_minimal_assets_dir(tmp_path: Path) -> Path:
    assets_dir = tmp_path / "extracted_assets"
    assets_dir.mkdir()
    write_yaml(
        assets_dir / "catalog_tables.yaml",
        """
        - asset_id: table.mx.dwd_w_apply
          asset_type: catalog_table
          country: mx
          domain: loan
          table_name: hive.dwd.dwd_w_apply
          description: 申请与放款核心明细表
          grain: apply_uuid
          primary_entities: [user, apply, withdraw]
          join_keys: [user_uuid, withdraw_uuid]
          time_fields: [apply_create_at, asset_grant_at, asset_finish_at]
          partition_fields: [dt]
          source_files: [scheme.md]
          confidence: high
          runtime_allowed: sanitized_only
          notes:
            - dt is a partition field.
        """,
    )
    write_yaml(
        assets_dir / "catalog_fields.yaml",
        """
        - asset_id: field.mx.dwd_w_apply.user_uuid
          asset_type: catalog_field
          country: mx
          domain: loan
          table_name: hive.dwd.dwd_w_apply
          field_name: user_uuid
          field_type: bigint
          semantic: user_identifier
          description: 用户 ID
          usage: [cohort_join]
          is_join_key: true
          is_partition_field: false
          is_business_time: false
          source_files: [scheme.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )
    write_yaml(
        assets_dir / "glossary_terms.yaml",
        """
        - asset_id: glossary.common.mob1
          asset_type: glossary_term
          country: common
          domain: lifecycle
          term: mob1
          aliases: [mob1客群, mob1提取]
          definition: 首贷 完全结清 结清满7天且7天内无复借
          related_rules: [rule.common.full_settlement]
          source_files: [多国业务逻辑.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )
    write_yaml(
        assets_dir / "business_rules.yaml",
        """
        - asset_id: rule.common.full_settlement
          asset_type: business_rule
          country: common
          domain: lifecycle
          name: full_settlement
          description: 完全结清判定
          rule_summary:
            - count periods > 0
            - all periods settled
            - settlement over 7 days before churn observation
          forbidden_omissions:
            - missing_all_periods_settled_check
          source_files: [多国业务逻辑.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )
    write_yaml(
        assets_dir / "cohort_definitions.yaml",
        """
        - asset_id: cohort.mx.mob1_settled_7d_churn
          asset_type: cohort_definition
          country: mx
          domain: lifecycle
          name: mob1_settled_7d_churn
          definition: 首贷完全结清后7天内无复借
          required_conditions: [first_loan, full_settlement, settlement_over_7d, no_reborrow_within_7d]
          required_tables: [hive.dwd.dwd_w_apply]
          required_fields: [user_uuid, withdraw_uuid, apply_create_at, asset_finish_at]
          forbidden_patterns: [missing_reborrow_anti_join]
          source_files: [多国业务逻辑.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )
    write_yaml(
        assets_dir / "sql_example_patterns.yaml",
        """
        - asset_id: sql_pattern.mx.behavior_writeback_target_cohort
          asset_type: sql_example_pattern
          country: mx
          domain: behavior
          scenario: behavior_writeback_for_target_cohort
          pattern_summary:
            - build target_users CTE first
            - join behavior events by uid to cohort
          required_output_fields: [uid, timestamp_, eventname]
          forbidden_copy: [fixed_historical_date, historical_source_filter, temporary_table_name, unresolved_uid_placeholder]
          source_files: [few.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )
    write_yaml(
        assets_dir / "sql_error_cases.yaml",
        """
        - asset_id: error_case.common.fixed_historical_date_copy
          asset_type: sql_error_case
          country: common
          domain: sql_generation
          scenario: historical_template_drift
          bad_pattern_category: fixed_historical_date_copy
          risk: 模型复制历史 SQL 中的固定日期
          expected_fix: 使用动态时间窗口
          warning_categories: [PLAN_DATE_DRIFT]
          source_files: [few.md, all_examples .md]
          confidence: high
          runtime_allowed: eval_only
        """,
    )
    write_yaml(
        assets_dir / "canonical_field_policies.yaml",
        """
        - asset_id: canonical.mx.apply_business_time
          asset_type: canonical_field_policy
          country: mx
          domain: loan
          business_semantic: apply_business_time
          table_name: hive.dwd.dwd_w_apply
          preferred_fields: [apply_create_at]
          alternative_fields: [dt]
          avoid_as_business_time: [dt]
          rationale: apply_create_at is the application business timestamp.
          review_status: needs_human_review
          source_files: [scheme.md]
          confidence: medium
          runtime_allowed: sanitized_only
        """,
    )
    write_yaml(
        assets_dir / "asset_source_map.yaml",
        """
        - source_file: 多国业务逻辑.md
          source_group: business_logic
          extraction_status: extracted
          extracted_asset_types: [glossary_term, business_rule, cohort_definition]
          risk_level: medium
          runtime_policy: no_raw_runtime
        - source_file: few.md
          source_group: sql_pattern_doc
          extraction_status: partial
          extracted_asset_types: [sql_example_pattern, sql_error_case]
          risk_level: high
          runtime_policy: sanitized_only
          planned_phase: M2B-1
        - source_file: dwt_user_market_tag_d（泰国用户域）.md
          source_group: thai_domain_doc
          extraction_status: deferred
          extracted_asset_types: []
          risk_level: medium
          runtime_policy: sanitized_only
          deferred_reason: Not required by first-batch golden set priority cases.
          planned_phase: M2B later extraction
        """,
    )
    return assets_dir


def test_validator_accepts_committed_extracted_assets(tmp_path: Path) -> None:
    from scripts.validate_m2b_extracted_assets import validate_assets_dir

    repo_root = Path(__file__).resolve().parents[1]
    coverage_md = tmp_path / "coverage.md"
    coverage_yaml = tmp_path / "coverage.yaml"

    result = validate_assets_dir(
        repo_root / "data_knowledge_eval/m2b/extracted_assets",
        repo_root / "data_knowledge_eval/m2b/golden_set.yaml",
        coverage_output=coverage_md,
        coverage_yaml=coverage_yaml,
    )

    assert result["asset_count"] > 0
    assert result["covered_case_count"] >= 8
    assert coverage_md.exists()
    assert coverage_yaml.exists()


def test_duplicate_asset_id_fails(tmp_path: Path) -> None:
    from scripts.validate_m2b_extracted_assets import validate_assets_dir

    assets_dir = make_minimal_assets_dir(tmp_path)
    write_yaml(
        assets_dir / "catalog_fields.yaml",
        """
        - asset_id: table.mx.dwd_w_apply
          asset_type: catalog_field
          country: mx
          domain: loan
          table_name: hive.dwd.dwd_w_apply
          field_name: user_uuid
          field_type: bigint
          semantic: user_identifier
          description: 用户 ID
          usage: [cohort_join]
          is_join_key: true
          is_partition_field: false
          is_business_time: false
          source_files: [scheme.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )

    with pytest.raises(ValueError, match="duplicate asset_id"):
        validate_assets_dir(assets_dir, Path("data_knowledge_eval/m2b/golden_set.yaml"))


def test_invalid_runtime_allowed_fails(tmp_path: Path) -> None:
    from scripts.validate_m2b_extracted_assets import validate_assets_dir

    assets_dir = make_minimal_assets_dir(tmp_path)
    write_yaml(
        assets_dir / "catalog_fields.yaml",
        """
        - asset_id: field.mx.dwd_w_apply.user_uuid
          asset_type: catalog_field
          country: mx
          domain: loan
          table_name: hive.dwd.dwd_w_apply
          field_name: user_uuid
          field_type: bigint
          semantic: user_identifier
          description: 用户 ID
          usage: [cohort_join]
          is_join_key: true
          is_partition_field: false
          is_business_time: false
          source_files: [scheme.md]
          confidence: high
          runtime_allowed: unsafe_runtime
        """,
    )

    with pytest.raises(ValueError, match="invalid runtime_allowed"):
        validate_assets_dir(assets_dir, Path("data_knowledge_eval/m2b/golden_set.yaml"))


def test_sensitive_literal_in_assets_fails(tmp_path: Path) -> None:
    from scripts.validate_m2b_extracted_assets import validate_assets_dir

    assets_dir = make_minimal_assets_dir(tmp_path)
    write_yaml(
        assets_dir / "glossary_terms.yaml",
        """
        - asset_id: glossary.common.mob1
          asset_type: glossary_term
          country: common
          domain: lifecycle
          term: mob1
          aliases: [mob1客群]
          definition: password='secret'
          related_rules: [rule.common.full_settlement]
          source_files: [多国业务逻辑.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )

    with pytest.raises(ValueError, match="sensitive pattern"):
        validate_assets_dir(assets_dir, Path("data_knowledge_eval/m2b/golden_set.yaml"))


def test_dirty_sql_pattern_fails(tmp_path: Path) -> None:
    from scripts.validate_m2b_extracted_assets import validate_assets_dir

    assets_dir = make_minimal_assets_dir(tmp_path)
    write_yaml(
        assets_dir / "sql_example_patterns.yaml",
        """
        - asset_id: sql_pattern.mx.behavior_writeback_target_cohort
          asset_type: sql_example_pattern
          country: mx
          domain: behavior
          scenario: behavior_writeback_for_target_cohort
          pattern_summary:
            - join dm_model.yx_tmp_baduser and use dt='20260201'
          required_output_fields: [uid, timestamp_, eventname]
          forbidden_copy: [fixed_historical_date]
          source_files: [few.md]
          confidence: high
          runtime_allowed: sanitized_only
        """,
    )

    with pytest.raises(ValueError, match="dirty sql pattern"):
        validate_assets_dir(assets_dir, Path("data_knowledge_eval/m2b/golden_set.yaml"))


def test_coverage_report_can_be_generated_for_minimal_assets(tmp_path: Path) -> None:
    from scripts.validate_m2b_extracted_assets import validate_assets_dir

    assets_dir = make_minimal_assets_dir(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    coverage_md = tmp_path / "coverage.md"
    coverage_yaml = tmp_path / "coverage.yaml"

    result = validate_assets_dir(
        assets_dir,
        repo_root / "data_knowledge_eval/m2b/golden_set.yaml",
        coverage_output=coverage_md,
        coverage_yaml=coverage_yaml,
    )

    assert result["asset_count"] >= 8
    assert coverage_md.read_text(encoding="utf-8")
    assert coverage_yaml.read_text(encoding="utf-8")
