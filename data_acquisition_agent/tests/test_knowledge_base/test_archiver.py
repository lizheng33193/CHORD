"""Plan 07 Phase 3 — archiver 单测（fail-safe + 前缀校验）。

⚠️ 默认走生产 yaml：调用 `load_manifest('mexico')` 不设 `DA_LOCAL_DEV` env
   返回生产配置，prefix = `dm_model.yyp_tmp_`。本测**动态取 manifest.analyst_private_prefix**，
   不硬预设字面量，不依赖"mexico.local.yaml 存在与否"。
"""

from __future__ import annotations

from pathlib import Path

import data_acquisition_agent.knowledge_base.archiver as archiver


def test_default_args_fail_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(archiver, "LEARNED_ROOT", tmp_path / "learned")
    result = archiver.archive_example(
        nl_query="活跃用户",
        generated_sql="SELECT 1",
        country="mexico",
    )
    assert result is None, "fail-safe broken: archived without explicit user_acked=True"


def test_archive_creates_file_when_all_gates_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(archiver, "LEARNED_ROOT", tmp_path / "learned")
    result = archiver.archive_example(
        nl_query="活跃用户 top 10",
        generated_sql="SELECT user_id FROM dwd_users LIMIT 10",
        country="mexico",
        sql_judge_l1_pass=True,
        sql_judge_l2_pass=True,
        user_acked=True,
    )
    assert result is not None, "expected archive when all 3 gates True"
    assert Path(result).exists()
    content = Path(result).read_text(encoding="utf-8")
    assert "活跃用户" in content
    assert "user_acked: true" in content


def test_archive_skips_oversized(tmp_path, monkeypatch):
    monkeypatch.setattr(archiver, "LEARNED_ROOT", tmp_path / "learned")
    huge_sql = "SELECT 1 " + "AND 1 " * 5000
    result = archiver.archive_example(
        nl_query="x",
        generated_sql=huge_sql,
        country="mexico",
        sql_judge_l1_pass=True,
        sql_judge_l2_pass=True,
        user_acked=True,
    )
    assert result is None


def test_archive_blocks_ddl_outside_private_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(archiver, "LEARNED_ROOT", tmp_path / "learned")
    bad_sql = "CREATE TABLE prod_dwd.target_users AS SELECT * FROM x"
    result = archiver.archive_example(
        nl_query="构建标签宽表",
        generated_sql=bad_sql,
        country="mexico",
        sql_judge_l1_pass=True,
        sql_judge_l2_pass=True,
        user_acked=True,
    )
    assert result is None, "DDL outside analyst_private_prefix must be rejected"


def test_archive_allows_ddl_in_private_prefix(tmp_path, monkeypatch):
    monkeypatch.delenv("DA_LOCAL_DEV", raising=False)
    monkeypatch.setattr(archiver, "LEARNED_ROOT", tmp_path / "learned")
    from data_acquisition_agent.manifest import load_manifest

    prefix = load_manifest("mexico").analyst_private_prefix
    assert prefix, "manifest.analyst_private_prefix must not be empty"
    good_sql = f"CREATE TABLE {prefix}tag_table AS SELECT * FROM x"
    result = archiver.archive_example(
        nl_query="构建标签宽表",
        generated_sql=good_sql,
        country="mexico",
        sql_judge_l1_pass=True,
        sql_judge_l2_pass=True,
        user_acked=True,
    )
    assert result is not None
