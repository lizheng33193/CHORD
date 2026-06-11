"""test_output_scanner — Step 4 TDD."""

import pytest
from data_acquisition_agent.output_scanner import scan_credentials


def test_scan_finds_ip_and_password():
    hits = scan_credentials("conn(host='198.51.100.10', password='FAKE_SECRET_REDACTED')")
    assert any("host" in h for h in hits)
    assert any("password" in h for h in hits)


def test_scan_clean_text():
    assert scan_credentials("SELECT 1") == []


def test_scan_finds_token_and_bearer():
    hits = scan_credentials("api_key='sk-FAKE'\nAuthorization: Bearer FAKE_AT")
    assert "api_key" in hits and "bearer" in hits


def test_scan_clean_does_not_match_report_eq_3306():
    assert scan_credentials("report=3306") == []


from data_acquisition_agent.output_scanner import scan_python_dangerous

DANGER = ["os.system('ls')", "subprocess.run(['x'], shell=True)", "eval('1+1')",
          "exec('x')", "__import__('os')", "shutil.rmtree('/')", "os.remove('/x')"]


@pytest.mark.parametrize("code", DANGER)
def test_blacklist_hits(code):
    assert scan_python_dangerous(code)


def test_clean_python():
    assert scan_python_dangerous("import pandas as pd\ndf = pd.read_csv('x.csv')") == []


from data_acquisition_agent.output_scanner import check_sql_policy


def test_query_only_rejects_ddl():
    with pytest.raises(ValueError):
        check_sql_policy("DROP TABLE x", "query_only", "dm_model.yyp_tmp_")


def test_query_only_allows_select():
    check_sql_policy("SELECT * FROM t", "query_only", "dm_model.yyp_tmp_")


def test_query_only_ignores_ddl_in_comments():
    check_sql_policy("-- DROP TABLE x\nSELECT 1", "query_only", "dm_model.yyp_tmp_")


@pytest.mark.parametrize("sql", [
    "CALL read_only_proc()",
    "EXEC read_only_proc()",
    "LOAD DATA INFILE '/tmp/users.csv' INTO TABLE users",
    "SELECT uid FROM users INTO OUTFILE '/tmp/users.csv'",
])
def test_query_only_rejects_non_select_statement_classes(sql):
    with pytest.raises(ValueError):
        check_sql_policy(sql, "query_only", "dm_model.yyp_tmp_")


@pytest.mark.parametrize("sql", [
    "SELECT uid FROM users LIMIT 10",
    "WITH cohort AS (SELECT uid FROM users) SELECT uid FROM cohort LIMIT 10",
    "SELECT uid FROM users WHERE note = 'drop candidate' LIMIT 10",
    "SELECT uid AS user_id FROM users LIMIT 10",
])
def test_query_only_allows_safe_select_and_cte_shapes(sql):
    check_sql_policy(sql, "query_only", "dm_model.yyp_tmp_")


def test_build_table_requires_prefix():
    with pytest.raises(ValueError):
        check_sql_policy("CREATE TABLE prod.x AS SELECT 1", "build_table_script", "dm_model.yyp_tmp_")


def test_build_table_with_prefix_ok():
    check_sql_policy("CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1", "build_table_script", "dm_model.yyp_tmp_")


def test_build_table_drop_if_exists_with_prefix_ok():
    check_sql_policy("DROP TABLE IF EXISTS dm_model.yyp_tmp_x", "build_table_script", "dm_model.yyp_tmp_")


# 新增：build_table_script 模式禁止其他 DML/DDL（即使表名带 prefix）
@pytest.mark.parametrize("sql", [
    "DELETE FROM dm_model.yyp_tmp_x WHERE id=1",
    "INSERT INTO dm_model.yyp_tmp_x VALUES (1)",
    "UPDATE dm_model.yyp_tmp_x SET a=1",
    "TRUNCATE TABLE dm_model.yyp_tmp_x",
    "ALTER TABLE dm_model.yyp_tmp_x ADD COLUMN c INT",
])
def test_build_table_rejects_non_create_drop_dml(sql):
    with pytest.raises(ValueError):
        check_sql_policy(sql, "build_table_script", "dm_model.yyp_tmp_")


# 新增：DDL target 含反引号 / 双引号包裹时保守 reject
@pytest.mark.parametrize("sql", [
    "CREATE TABLE `dm_model`.`yyp_tmp_x` AS SELECT 1",
    'CREATE TABLE "dm_model"."yyp_tmp_x" AS SELECT 1',
])
def test_build_table_rejects_quoted_identifier(sql):
    with pytest.raises(ValueError):
        check_sql_policy(sql, "build_table_script", "dm_model.yyp_tmp_")


# 新增：错误信息不得回显 SQL / target 原文（防 prompt 注入回显）
_SECRET_TARGET = "prod_secret_db.sensitive_table_name_xyz"
_SECRET_SQL_BODY = "SECRET_INNER_FRAGMENT_DO_NOT_LEAK"


def test_check_sql_policy_message_does_not_echo_sql():
    sql = f"INSERT INTO dm_model.yyp_tmp_x SELECT '{_SECRET_SQL_BODY}'"
    with pytest.raises(ValueError) as ei:
        check_sql_policy(sql, "build_table_script", "dm_model.yyp_tmp_")
    assert _SECRET_SQL_BODY not in str(ei.value)


def test_check_sql_policy_message_does_not_echo_target():
    sql = f"CREATE TABLE {_SECRET_TARGET} AS SELECT 1"
    with pytest.raises(ValueError) as ei:
        check_sql_policy(sql, "build_table_script", "dm_model.yyp_tmp_")
    assert _SECRET_TARGET not in str(ei.value)


def test_check_sql_policy_unknown_kind_message_fixed():
    with pytest.raises(ValueError) as ei:
        check_sql_policy("SELECT 1", "weird_attacker_supplied_kind", "dm_model.yyp_tmp_")
    assert "weird_attacker_supplied_kind" not in str(ei.value)
    assert str(ei.value) == "unknown sql_kind"
