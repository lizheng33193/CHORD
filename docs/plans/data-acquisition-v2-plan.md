# data_acquisition_agent V2 Implementation Plan

> Design Doc: docs/specs/data_acquisition_agent_v2.md
> Step 3 baseline commit: d56d27c

## Context

V1（72 tests）已把"自然语言 → SQL/Python artifact"落地，但显式不连库、不执行、不落数据。V2 在 V1 基础上新增受控执行层：分析师审核后的 SQL → query_only 执行 → bucket 切片 → per-uid 文件落到 `data/<bucket>/by_uid/`，让画像 SkillRegistry 直接读到新数据。

Step 3 已落 7 个 Stub（connection.py / executor.py / output_writer.py + 4 测试 stub）+ schemas/api/config/requirements/.env.example 扩展。本 Plan 把 Stub 转为可工作实现。

## Scope

**In Scope（V2 Phase 1–6）**
- Phase 1：ExecuteRequest validators（app bucket → csv 强制等）
- Phase 2：connection.py — env→pymysql 短生命周期连接 + DbUnreachableError 封装
- Phase 3：executor.py — 守门 + COUNT 预检 + execute_query
- Phase 4：output_writer.py — schema 校验 + 内存切片 + .tmp + os.replace
- Phase 5：executor.run_execute_pipeline + api.py /execute 接编排 + HTTP 映射
- Phase 6：T1-T4 安全测试独立 Phase + e2e mock executor happy path

**Out of Scope（V2 不做，留 V3+）**
- DDL 执行（build_table_script 永远 422）
- partial write success / 跨多文件事务
- SQL 结果 streaming / 分批写
- 多分析师 / approval token 状态机
- 非 mexico 国家真实 StarRocks 验证
- healthz 扩展为 DB 探活
- StarRocks 真实 RBAC 自动化测试（部署 smoke checklist）
- V1 LLM JSON 稳定性修复（独立 follow-up）

## Worked Example（预期输入输出）

**正常请求 (200)**
```json
POST /api/data-acquisition/execute
{
  "approved_sql": "SELECT uid, app_name, app_package, first_install_time, last_update_time, gp_category, ai_category_level_2_CN FROM dm_model.yyp_tmp_mob1_mexico WHERE channel='MEX017' LIMIT 100",
  "sql_kind": "query_only",
  "target_country": "mexico",
  "approved_by": "analyst_alias",
  "approval_note": "v1 request_id 1234-... 审核后限 100 行",
  "source_request_id": "1234-5678-uuid",
  "output_bucket": "app",
  "output_format": "csv",
  "uid_column": "uid",
  "overwrite": true
}

→ 200 OK
{
  "request_id": "uuid",
  "output_bucket": "app",
  "output_format": "csv",
  "filenames": ["u1.csv", "u2.csv"],
  "written_file_count": 2,
  "total_uids": 2,
  "rows_per_uid": {"u1": 5, "u2": 3},
  "metadata": {
    "executed_at": "2026-04-29T10:00:00+00:00",
    "approved_by": "analyst_alias",
    "source_request_id": "1234-5678-uuid",
    "duration_ms": 1234,
    "row_count_total": 8
  }
}
```

**DDL 拒绝 (422)**
```json
{"approved_sql": "CREATE TABLE x AS SELECT 1", "sql_kind": "build_table_script", ...}
→ {"error_type": "ddl_not_supported_in_v2", "message": "DDL is not executable by V2", "request_id": "uuid"}
```

**结果过大 (413)**
```json
{"approved_sql": "SELECT * FROM huge_table", "sql_kind": "query_only", ...}
→ {"error_type": "result_too_large", "message": "result exceeds row limit", "request_id": "uuid"}
```

**连库失败 (502)**
```json
→ {"error_type": "db_unreachable", "message": "database connection failed", "request_id": "uuid"}
```

## 关键决策（已与用户确认）

1. **Plan 路径**：`docs/plans/data-acquisition-v2-plan.md`
2. **Mock 策略**：pytest 自带 monkeypatch + unittest.mock.MagicMock（与 V1 风格一致，不引入 pytest-mock）
3. **Phase 编号**：从 V2 Phase 1 重新起编（V2 是独立 plan 文档）
4. **T1-T4 编排**：独立 Phase 6，放在功能 Phase 1-5 之后
5. **Driver**：pymysql（Step 3 已写入 requirements.txt）
6. **Connection profile**：V2 单一全局，从 os.environ 读 DA_DB_*，不入 Settings
7. **写盘原子性**：单文件 os.replace；跨文件 crash-consistency trade-off 明确接受（Design Doc §8.4）

---

## V2 Phase 1 — schemas.py validators

### Task 1.1 — ExecuteRequest validator（app bucket 强制 csv + approved_sql 非空）

- **Files Modify**: `data_acquisition_agent/schemas.py`
- **Files Modify**: `data_acquisition_agent/tests/test_schemas.py`

**TDD 步骤**

- Step 1：在 test_schemas.py 追加测试：
  ```python
  from data_acquisition_agent.schemas import ExecuteRequest
  from pydantic import ValidationError

  def test_app_bucket_requires_csv_format():
      with pytest.raises(ValidationError):
          ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
              target_country="mexico", approved_by="t",
              output_bucket="app", output_format="json", uid_column="uid")

  def test_behavior_bucket_allows_json():
      ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
          target_country="mexico", approved_by="t",
          output_bucket="behavior", output_format="json", uid_column="uid")

  def test_credit_bucket_allows_csv():
      ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
          target_country="mexico", approved_by="t",
          output_bucket="credit", output_format="csv", uid_column="uid")

  def test_approved_sql_non_empty():
      with pytest.raises(ValidationError):
          ExecuteRequest(approved_sql="   ", sql_kind="query_only",
              target_country="mexico", approved_by="t",
              output_bucket="app", output_format="csv", uid_column="uid")

  def test_uid_column_default_is_uid():
      r = ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
          target_country="mexico", approved_by="t",
          output_bucket="app", output_format="csv")
      assert r.uid_column == "uid"
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_schemas.py -v` → 预期 4 个新 case FAIL（V1 5 case + V2 5 新 case，其中 default uid 已 PASS）
- Step 3：在 ExecuteRequest 内追加：
  ```python
  from pydantic import field_validator, model_validator

  @field_validator("approved_sql")
  @classmethod
  def _approved_sql_non_empty(cls, v: str) -> str:
      if not v or not v.strip():
          raise ValueError("approved_sql must be non-empty")
      return v

  @model_validator(mode="after")
  def _app_bucket_requires_csv(self):
      if self.output_bucket == "app" and self.output_format != "csv":
          raise ValueError("app bucket requires output_format=csv")
      return self
  ```
- Step 4：同命令 → 预期 V1 5 + V2 5 = 10 case PASS
- Step 5：`git add data_acquisition_agent/schemas.py data_acquisition_agent/tests/test_schemas.py && git commit -m "feat(da-agent): V2 ExecuteRequest validators"`

**不允许**：修改 V1 GenerateRequest / GenerateResponse / AuditReport；实现 sql_kind=build_table_script 拦截（属 Phase 3 守门层）
**完成标准**：10 case PASS

---

## V2 Phase 2 — connection.py

### Task 2.1 — open_starrocks_connection（env→pymysql 短生命周期）

- **Files Modify**: `data_acquisition_agent/connection.py`
- **Files Modify**: `data_acquisition_agent/tests/test_connection.py`

**TDD 步骤**

- Step 1：替换 test_connection.py（去掉 pytestmark.skip，写实测）：
  ```python
  import os, pytest
  from unittest.mock import MagicMock, patch
  from data_acquisition_agent.connection import (open_starrocks_connection,
      DbUnreachableError, _RedactedConnection)

  ENV = {"DA_DB_HOST": "10.0.0.1", "DA_DB_PORT": "9030",
         "DA_DB_USER": "ro_user", "DA_DB_PASSWORD": "fake_pw_xyz",
         "DA_DB_DATABASE": "dm_fake"}

  def test_open_reads_env_at_call_time(monkeypatch):
      """§6.1 凭据应在 open 时才从 os.environ 读，而非 import 时。"""
      for k, v in ENV.items(): monkeypatch.setenv(k, v)
      fake_conn = MagicMock()
      with patch("data_acquisition_agent.connection.pymysql.connect",
                 return_value=fake_conn) as m:
          with open_starrocks_connection(request_id="rid-1") as conn:
              assert conn is not None
          m.assert_called_once()
          kwargs = m.call_args.kwargs
          assert kwargs["host"] == "10.0.0.1"
          assert kwargs["port"] == 9030
          assert kwargs["user"] == "ro_user"
          assert kwargs["password"] == "fake_pw_xyz"
          assert kwargs["database"] == "dm_fake"
      fake_conn.close.assert_called_once()

  def test_open_missing_env_raises_db_unreachable(monkeypatch):
      monkeypatch.delenv("DA_DB_PASSWORD", raising=False)
      for k, v in ENV.items():
          if k != "DA_DB_PASSWORD": monkeypatch.setenv(k, v)
      with pytest.raises(DbUnreachableError):
          with open_starrocks_connection(request_id="rid-2"):
              pass

  def test_open_driver_exception_wrapped(monkeypatch):
      """§6.4 driver 异常 → DbUnreachableError，不带原 message。"""
      for k, v in ENV.items(): monkeypatch.setenv(k, v)
      with patch("data_acquisition_agent.connection.pymysql.connect",
                 side_effect=Exception("Access denied for user 'x'@'y'")):
          with pytest.raises(DbUnreachableError) as ei:
              with open_starrocks_connection(request_id="rid-3"):
                  pass
          # 不携带原始 message
          assert "Access denied" not in str(ei.value)
          assert "fake_pw_xyz" not in str(ei.value)

  def test_redacted_connection_repr_no_credentials(monkeypatch):
      for k, v in ENV.items(): monkeypatch.setenv(k, v)
      fake_conn = MagicMock()
      with patch("data_acquisition_agent.connection.pymysql.connect",
                 return_value=fake_conn):
          with open_starrocks_connection(request_id="rid-4") as conn:
              r = repr(conn)
              assert "10.0.0.1" not in r
              assert "fake_pw_xyz" not in r
              assert "ro_user" not in r
              assert "dm_fake" not in r

  def test_close_called_even_on_inner_exception(monkeypatch):
      for k, v in ENV.items(): monkeypatch.setenv(k, v)
      fake_conn = MagicMock()
      with patch("data_acquisition_agent.connection.pymysql.connect",
                 return_value=fake_conn):
          with pytest.raises(RuntimeError):
              with open_starrocks_connection(request_id="rid-5") as conn:
                  raise RuntimeError("inner")
      fake_conn.close.assert_called_once()
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_connection.py -v` → 预期 5 case FAIL
- Step 3：实现 connection.py：
  ```python
  import os
  import pymysql
  from contextlib import contextmanager

  class DbUnreachableError(Exception):
      def __init__(self, message: str = "database connection failed",
                   request_id: str = ""):
          super().__init__(message)
          self.message = message
          self.request_id = request_id

  class _RedactedConnection:
      def __init__(self, raw): self._raw = raw
      def __repr__(self) -> str: return "<RedactedStarRocksConnection>"
      def __getattr__(self, name): return getattr(self._raw, name)
      def close(self): self._raw.close()

  _REQUIRED_ENV = ("DA_DB_HOST", "DA_DB_PORT", "DA_DB_USER",
                   "DA_DB_PASSWORD", "DA_DB_DATABASE")

  @contextmanager
  def open_starrocks_connection(*, request_id: str):
      try:
          for k in _REQUIRED_ENV:
              if not os.environ.get(k):
                  raise DbUnreachableError(request_id=request_id)
          creds = {
              "host": os.environ["DA_DB_HOST"],
              "port": int(os.environ["DA_DB_PORT"]),
              "user": os.environ["DA_DB_USER"],
              "password": os.environ["DA_DB_PASSWORD"],
              "database": os.environ["DA_DB_DATABASE"],
          }
          raw = pymysql.connect(**creds)
      except DbUnreachableError:
          raise
      except Exception:
          raise DbUnreachableError(request_id=request_id) from None
      conn = _RedactedConnection(raw)
      try:
          yield conn
      finally:
          try: conn.close()
          except Exception: pass
  ```
- Step 4：同命令 → 预期 5 case PASS
- Step 5：`git add data_acquisition_agent/connection.py data_acquisition_agent/tests/test_connection.py && git commit -m "feat(da-agent): V2 starrocks connection layer"`

**不允许**：把 creds 存 module-level；让 driver 异常 chain 透传；用 sqlalchemy
**完成标准**：5 case PASS；`grep -r "fake_pw_xyz\|10\.0\.0\.1" data_acquisition_agent/connection.py` 无输出

---

## V2 Phase 3 — executor.py 守门 + COUNT + execute_query

### Task 3.1 — enforce_pre_execution_gates（Design Doc §7.1 三层守门 + multi-statement）

- **Files Modify**: `data_acquisition_agent/executor.py`
- **Files Modify**: `data_acquisition_agent/tests/test_executor.py`

**TDD 步骤**

- Step 1：替换 test_executor.py（去 pytestmark.skip）：
  ```python
  import pytest
  from data_acquisition_agent.executor import (enforce_pre_execution_gates,
      ExecutorError)
  from data_acquisition_agent.schemas import ErrorType

  PFX = "dm_model.yyp_tmp_"

  def test_gate_rejects_build_table_script():
      with pytest.raises(ExecutorError) as ei:
          enforce_pre_execution_gates(approved_sql="CREATE TABLE x AS SELECT 1",
              sql_kind="build_table_script", analyst_private_prefix=PFX,
              request_id="rid")
      assert ei.value.error_type == ErrorType.DDL_NOT_SUPPORTED_IN_V2
      assert ei.value.message == "DDL is not executable by V2"

  @pytest.mark.parametrize("sql", [
      "DROP TABLE x", "INSERT INTO x VALUES (1)",
      "UPDATE x SET a=1", "DELETE FROM x WHERE 1=1",
      "TRUNCATE TABLE x", "ALTER TABLE x ADD COLUMN c INT",
      "CREATE TABLE x AS SELECT 1",
  ])
  def test_gate_rejects_ddl_dml_in_query_only(sql):
      with pytest.raises(ExecutorError) as ei:
          enforce_pre_execution_gates(approved_sql=sql, sql_kind="query_only",
              analyst_private_prefix=PFX, request_id="rid")
      assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION

  def test_gate_rejects_multi_statement():
      with pytest.raises(ExecutorError) as ei:
          enforce_pre_execution_gates(
              approved_sql="SELECT 1; SELECT 2",
              sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
      assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION

  def test_gate_rejects_credential_leak():
      with pytest.raises(ExecutorError) as ei:
          enforce_pre_execution_gates(
              approved_sql="SELECT 1 -- password='leak_xyz'",
              sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
      assert ei.value.error_type == ErrorType.CREDENTIAL_LEAK

  def test_gate_rejects_dangerous_python():
      """§7.1 Step 2: scan_python_dangerous defensive guard。"""
      with pytest.raises(ExecutorError) as ei:
          enforce_pre_execution_gates(
              approved_sql="SELECT uid FROM t WHERE x=eval('1+1')",
              sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
      assert ei.value.error_type == ErrorType.DANGEROUS_CODE

  def test_gate_allows_clean_select():
      enforce_pre_execution_gates(approved_sql="SELECT uid FROM t WHERE x=1",
          sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")

  def test_gate_strips_comments_before_split():
      """; 在注释里不应触发 multi-statement。"""
      enforce_pre_execution_gates(
          approved_sql="SELECT uid FROM t -- foo; bar\n WHERE x=1",
          sql_kind="query_only", analyst_private_prefix=PFX, request_id="rid")
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_executor.py -v` → 预期 13 FAIL
- Step 3：实现 ExecutorError + enforce_pre_execution_gates：
  ```python
  from .output_scanner import (scan_credentials, scan_python_dangerous,
      check_sql_policy, _strip_sql_comments)
  from .schemas import ErrorType

  class ExecutorError(Exception):
      def __init__(self, error_type, message, request_id: str = ""):
          super().__init__(message)
          self.error_type = error_type
          self.message = message
          self.request_id = request_id

  def enforce_pre_execution_gates(*, approved_sql, sql_kind,
                                   analyst_private_prefix, request_id):
      if sql_kind == "build_table_script":
          raise ExecutorError(ErrorType.DDL_NOT_SUPPORTED_IN_V2,
              "DDL is not executable by V2", request_id=request_id)
      if scan_credentials(approved_sql):
          raise ExecutorError(ErrorType.CREDENTIAL_LEAK,
              "credential pattern in artifact", request_id=request_id)
      if scan_python_dangerous(approved_sql):
          raise ExecutorError(ErrorType.DANGEROUS_CODE,
              "dangerous code pattern in artifact", request_id=request_id)
      try:
          check_sql_policy(approved_sql, "query_only", analyst_private_prefix)
      except ValueError:
          raise ExecutorError(ErrorType.DDL_POLICY_VIOLATION,
              "artifact failed SQL policy", request_id=request_id)
      stripped = _strip_sql_comments(approved_sql)
      tokens = [s for s in (s.strip() for s in stripped.split(";")) if s]
      if len(tokens) > 1:
          raise ExecutorError(ErrorType.DDL_POLICY_VIOLATION,
              "artifact failed SQL policy", request_id=request_id)
  ```
  注：`_strip_sql_comments` 是 V1 output_scanner.py 已有的私有函数（V1 plan Phase 4.3 已实现），V2 复用，不改。
- Step 4：同命令 → 预期 13 case PASS（1 ddl_not_supported + 7 parametrize + multi-stmt + cred + dangerous_python + clean + comment-split）
- Step 5：`git add data_acquisition_agent/executor.py data_acquisition_agent/tests/test_executor.py && git commit -m "feat(da-agent): V2 pre-execution gates"`

**不允许**：实现 connect/COUNT/execute（属 3.2/3.3）；改 V1 output_scanner.py
**完成标准**：13 case PASS

### Task 3.2 — precheck_row_count（COUNT(*) 包裹预检）

- **Files Modify**: `data_acquisition_agent/executor.py`, `data_acquisition_agent/tests/test_executor.py`

**TDD 步骤**

- Step 1：追加测试：
  ```python
  from unittest.mock import MagicMock
  from data_acquisition_agent.executor import precheck_row_count

  def _mock_conn_returning(value):
      conn = MagicMock()
      cur = MagicMock()
      cur.fetchone.return_value = (value,) if value is not None else None
      conn.cursor.return_value.__enter__.return_value = cur
      return conn, cur

  def test_precheck_returns_count():
      conn, cur = _mock_conn_returning(42)
      n = precheck_row_count(conn=conn, approved_sql="SELECT 1",
          max_rows=100, timeout_s=60, request_id="rid")
      assert n == 42

  def test_precheck_raises_when_over_limit():
      conn, cur = _mock_conn_returning(101)
      with pytest.raises(ExecutorError) as ei:
          precheck_row_count(conn=conn, approved_sql="SELECT 1",
              max_rows=100, timeout_s=60, request_id="rid")
      assert ei.value.error_type == ErrorType.RESULT_TOO_LARGE

  def test_precheck_db_failure_to_query_failed():
      conn = MagicMock()
      conn.cursor.side_effect = Exception("syntax error near foo")
      with pytest.raises(ExecutorError) as ei:
          precheck_row_count(conn=conn, approved_sql="SELECT 1",
              max_rows=100, timeout_s=60, request_id="rid")
      assert ei.value.error_type == ErrorType.QUERY_FAILED
      assert ei.value.message == "query execution failed"
      assert "syntax" not in ei.value.message

  def test_precheck_wraps_sql_in_count():
      conn, cur = _mock_conn_returning(5)
      precheck_row_count(conn=conn, approved_sql="SELECT uid FROM t LIMIT 10",
          max_rows=100, timeout_s=60, request_id="rid")
      executed = cur.execute.call_args.args[0]
      assert "SELECT COUNT(*)" in executed.upper()
      assert "FROM (" in executed.upper()
      assert "AS DA_V2_COUNT" in executed.upper()
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_executor.py -v` → 预期 4 个新 case FAIL
- Step 3：实现：
  ```python
  def precheck_row_count(*, conn, approved_sql, max_rows, timeout_s, request_id):
      sql_stripped = approved_sql.rstrip().rstrip(";").rstrip()
      count_sql = f"SELECT COUNT(*) FROM ({sql_stripped}) AS da_v2_count"
      try:
          with conn.cursor() as cur:
              cur.execute(count_sql)
              row = cur.fetchone()
              n = int(row[0]) if row else 0
      except ExecutorError:
          raise
      except Exception:
          raise ExecutorError(ErrorType.QUERY_FAILED,
              "query execution failed", request_id=request_id) from None
      if n > max_rows:
          raise ExecutorError(ErrorType.RESULT_TOO_LARGE,
              "result exceeds row limit", request_id=request_id)
      return n
  ```
  注：pymysql 的 cursor 不直接支持 timeout 参数；timeout_s 在主查询场景由部署侧配 connect_timeout 兜底。运行时 query timeout 留 V3。
- Step 4：同命令 → 预期 4 case PASS
- Step 5：`git add data_acquisition_agent/executor.py data_acquisition_agent/tests/test_executor.py && git commit -m "feat(da-agent): V2 count precheck"`

**完成标准**：4 case PASS

### Task 3.3 — execute_query（主查询 + 空集校验）

- **Files Modify**: `data_acquisition_agent/executor.py`, `data_acquisition_agent/tests/test_executor.py`

**TDD 步骤**

- Step 1：追加测试：
  ```python
  import pandas as pd
  from data_acquisition_agent.executor import execute_query

  def _mock_conn_returning_rows(rows, columns):
      conn = MagicMock()
      cur = MagicMock()
      cur.description = [(c,) for c in columns]
      cur.fetchall.return_value = rows
      conn.cursor.return_value.__enter__.return_value = cur
      return conn

  def test_execute_returns_dataframe():
      conn = _mock_conn_returning_rows([("u1", "WhatsApp"), ("u2", "FB")],
          ["uid", "app_name"])
      df = execute_query(conn=conn, approved_sql="SELECT uid, app_name FROM t",
          timeout_s=60, request_id="rid")
      assert list(df.columns) == ["uid", "app_name"]
      assert len(df) == 2

  def test_execute_empty_result_raises_validation():
      conn = _mock_conn_returning_rows([], ["uid", "app_name"])
      with pytest.raises(ExecutorError) as ei:
          execute_query(conn=conn, approved_sql="SELECT uid FROM t",
              timeout_s=60, request_id="rid")
      assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

  def test_execute_db_failure_to_query_failed():
      conn = MagicMock()
      conn.cursor.side_effect = Exception("table 'x' doesn't exist")
      with pytest.raises(ExecutorError) as ei:
          execute_query(conn=conn, approved_sql="SELECT 1",
              timeout_s=60, request_id="rid")
      assert ei.value.error_type == ErrorType.QUERY_FAILED
      assert "doesn" not in ei.value.message
  ```
- Step 2：跑 → 3 FAIL
- Step 3：实现：
  ```python
  import pandas as pd

  def execute_query(*, conn, approved_sql, timeout_s, request_id):
      try:
          with conn.cursor() as cur:
              cur.execute(approved_sql)
              rows = cur.fetchall()
              cols = [d[0] for d in (cur.description or [])]
      except ExecutorError:
          raise
      except Exception:
          raise ExecutorError(ErrorType.QUERY_FAILED,
              "query execution failed", request_id=request_id) from None
      if not rows:
          raise ExecutorError(ErrorType.RESULT_VALIDATION_FAILED,
              "result validation failed", request_id=request_id)
      return pd.DataFrame(list(rows), columns=cols)
  ```
- Step 4：跑 → 3 PASS
- Step 5：`git add data_acquisition_agent/executor.py data_acquisition_agent/tests/test_executor.py && git commit -m "feat(da-agent): V2 execute_query"`

**完成标准**：3 case PASS（Phase 3 累计 20 case）

---

## V2 Phase 4 — output_writer.py

### Task 4.1 — validate_bucket_schema（app 7 字段 + uid_column）

- **Files Modify**: `data_acquisition_agent/output_writer.py`
- **Files Modify**: `data_acquisition_agent/tests/test_output_writer.py`

**TDD 步骤**

- Step 1：替换 test_output_writer.py：
  ```python
  import pandas as pd, pytest
  from data_acquisition_agent.output_writer import (validate_bucket_schema,
      OutputWriterError, APP_BUCKET_REQUIRED_COLUMNS)
  from data_acquisition_agent.schemas import ErrorType

  def _app_df():
      return pd.DataFrame([{c: "x" for c in APP_BUCKET_REQUIRED_COLUMNS}])

  def test_app_bucket_passes_with_seven_columns():
      validate_bucket_schema(_app_df(), output_bucket="app",
          output_format="csv", uid_column="uid", request_id="rid")

  def test_app_bucket_rejects_missing_column():
      df = _app_df().drop(columns=["app_name"])
      with pytest.raises(OutputWriterError) as ei:
          validate_bucket_schema(df, output_bucket="app",
              output_format="csv", uid_column="uid", request_id="rid")
      assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

  def test_app_bucket_rejects_json_format():
      with pytest.raises(OutputWriterError) as ei:
          validate_bucket_schema(_app_df(), output_bucket="app",
              output_format="json", uid_column="uid", request_id="rid")
      assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

  def test_uid_column_must_exist():
      df = pd.DataFrame([{"id": "x"}])
      with pytest.raises(OutputWriterError) as ei:
          validate_bucket_schema(df, output_bucket="behavior",
              output_format="json", uid_column="uid", request_id="rid")
      assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

  def test_behavior_bucket_minimal_passes():
      df = pd.DataFrame([{"uid": "u1", "extra": 1}])
      validate_bucket_schema(df, output_bucket="behavior",
          output_format="json", uid_column="uid", request_id="rid")
  ```
- Step 2：跑 → 5 FAIL
- Step 3：实现：
  ```python
  from .schemas import ErrorType

  def validate_bucket_schema(df, *, output_bucket, output_format,
                             uid_column, request_id):
      if uid_column not in df.columns:
          raise OutputWriterError(ErrorType.RESULT_VALIDATION_FAILED,
              "result validation failed", request_id=request_id)
      if output_bucket == "app":
          if output_format != "csv":
              raise OutputWriterError(ErrorType.RESULT_VALIDATION_FAILED,
                  "result validation failed", request_id=request_id)
          missing = set(APP_BUCKET_REQUIRED_COLUMNS) - set(df.columns)
          if missing:
              raise OutputWriterError(ErrorType.RESULT_VALIDATION_FAILED,
                  "result validation failed", request_id=request_id)
  ```
- Step 4：跑 → 5 PASS
- Step 5：`git add data_acquisition_agent/output_writer.py data_acquisition_agent/tests/test_output_writer.py && git commit -m "feat(da-agent): V2 bucket schema validation"`

**完成标准**：5 case PASS

### Task 4.2 — build_per_uid_payloads（内存切片 + json 外壳）

- **Files Modify**: `data_acquisition_agent/output_writer.py`, `data_acquisition_agent/tests/test_output_writer.py`

**TDD 步骤**

- Step 1：追加测试：
  ```python
  import json
  from data_acquisition_agent.output_writer import build_per_uid_payloads

  def test_app_csv_payloads_grouped_by_uid():
      df = pd.DataFrame([
          {"uid":"u1","app_name":"WA","app_package":"p","first_install_time":"t",
           "last_update_time":"t","gp_category":"g","ai_category_level_2_CN":"c"},
          {"uid":"u1","app_name":"FB","app_package":"p","first_install_time":"t",
           "last_update_time":"t","gp_category":"g","ai_category_level_2_CN":"c"},
          {"uid":"u2","app_name":"TG","app_package":"p","first_install_time":"t",
           "last_update_time":"t","gp_category":"g","ai_category_level_2_CN":"c"},
      ])
      items = build_per_uid_payloads(df, output_bucket="app", output_format="csv",
          uid_column="uid", approved_by="t", source_request_id=None,
          executed_at="2026-04-29T00:00:00", request_id="rid")
      assert len(items) == 2
      uids = [u for u, _ in items]
      assert sorted(uids) == ["u1", "u2"]
      u1_payload = next(p for u, p in items if u == "u1")
      assert b"WA" in u1_payload and b"FB" in u1_payload
      assert u1_payload.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM

  def test_behavior_json_wraps_schema_version():
      df = pd.DataFrame([{"uid": "u1", "x": 1}, {"uid": "u1", "x": 2}])
      items = build_per_uid_payloads(df, output_bucket="behavior",
          output_format="json", uid_column="uid", approved_by="alice",
          source_request_id="src-1", executed_at="2026-04-29T00:00:00",
          request_id="rid")
      assert len(items) == 1
      uid, payload = items[0]
      obj = json.loads(payload.decode("utf-8"))
      assert obj["schema_version"] == "da_agent_v2"
      assert obj["uid"] == "u1"
      assert obj["source_meta"]["approved_by"] == "alice"
      assert obj["source_meta"]["source_request_id"] == "src-1"
      assert obj["source_meta"]["row_count"] == 2
      assert len(obj["rows"]) == 2

  def test_behavior_csv_payload_no_wrapper():
      df = pd.DataFrame([{"uid": "u1", "x": 1}])
      items = build_per_uid_payloads(df, output_bucket="behavior",
          output_format="csv", uid_column="uid", approved_by="t",
          source_request_id=None, executed_at="t", request_id="rid")
      uid, payload = items[0]
      assert b"schema_version" not in payload
      assert b"x" in payload
  ```
- Step 2：跑 → 3 FAIL
- Step 3：实现：
  ```python
  import io, json

  def build_per_uid_payloads(df, *, output_bucket, output_format, uid_column,
                              approved_by, source_request_id, executed_at,
                              request_id):
      items: list[tuple[str, bytes]] = []
      for uid, group in df.groupby(uid_column, sort=True):
          uid_str = str(uid)
          if output_format == "csv":
              buf = io.StringIO()
              group.to_csv(buf, index=False)
              items.append((uid_str, buf.getvalue().encode("utf-8-sig")))
          else:  # json
              wrapper = {
                  "schema_version": "da_agent_v2",
                  "source_meta": {
                      "executed_at": executed_at,
                      "approved_by": approved_by,
                      "source_request_id": source_request_id,
                      "row_count": len(group),
                  },
                  "uid": uid_str,
                  "rows": group.to_dict(orient="records"),
              }
              items.append((uid_str,
                  json.dumps(wrapper, ensure_ascii=False).encode("utf-8")))
      return items
  ```
- Step 4：跑 → 3 PASS
- Step 5：`git add data_acquisition_agent/output_writer.py data_acquisition_agent/tests/test_output_writer.py && git commit -m "feat(da-agent): V2 per-uid payload builder"`

**完成标准**：3 case PASS

### Task 4.3 — write_per_uid_atomic（.tmp + os.replace + 回滚）

- **Files Modify**: `data_acquisition_agent/output_writer.py`, `data_acquisition_agent/tests/test_output_writer.py`

**TDD 步骤**

- Step 1：追加测试：
  ```python
  from pathlib import Path
  from data_acquisition_agent.output_writer import write_per_uid_atomic

  def test_write_creates_files_in_bucket(tmp_path):
      bucket = tmp_path / "app_by_uid"; bucket.mkdir()
      items = [("u1", b"hello"), ("u2", b"world")]
      filenames = write_per_uid_atomic(items, bucket_dir=bucket,
          output_format="csv", overwrite=True, request_id="rid")
      assert sorted(filenames) == ["u1.csv", "u2.csv"]
      assert (bucket / "u1.csv").read_bytes() == b"hello"
      assert (bucket / "u2.csv").read_bytes() == b"world"
      assert not list(bucket.glob(".tmp_*"))

  def test_write_overwrite_false_conflict_raises(tmp_path):
      bucket = tmp_path / "app_by_uid"; bucket.mkdir()
      (bucket / "u1.csv").write_bytes(b"old")
      with pytest.raises(OutputWriterError) as ei:
          write_per_uid_atomic([("u1", b"new")], bucket_dir=bucket,
              output_format="csv", overwrite=False, request_id="rid")
      assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED
      assert (bucket / "u1.csv").read_bytes() == b"old"
      assert not list(bucket.glob(".tmp_*"))

  def test_write_overwrite_true_replaces(tmp_path):
      bucket = tmp_path / "app_by_uid"; bucket.mkdir()
      (bucket / "u1.csv").write_bytes(b"old")
      write_per_uid_atomic([("u1", b"new")], bucket_dir=bucket,
          output_format="csv", overwrite=True, request_id="rid")
      assert (bucket / "u1.csv").read_bytes() == b"new"

  def test_write_rolls_back_tmp_on_failure(tmp_path, monkeypatch):
      bucket = tmp_path / "app_by_uid"; bucket.mkdir()
      from data_acquisition_agent import output_writer as ow
      orig_replace = ow.os.replace
      calls = {"n": 0}
      def boom(src, dst):
          calls["n"] += 1
          if calls["n"] == 2: raise OSError("disk full")
          orig_replace(src, dst)
      monkeypatch.setattr(ow.os, "replace", boom)
      with pytest.raises(OutputWriterError) as ei:
          write_per_uid_atomic([("u1", b"a"), ("u2", b"b")],
              bucket_dir=bucket, output_format="csv", overwrite=True,
              request_id="rid")
      assert ei.value.error_type == ErrorType.OUTPUT_WRITE_FAILED
      assert not list(bucket.glob(".tmp_*"))

  def test_write_returns_filenames_only_no_path(tmp_path):
      bucket = tmp_path / "behavior_by_uid"; bucket.mkdir()
      filenames = write_per_uid_atomic([("u1", b"x")], bucket_dir=bucket,
          output_format="json", overwrite=True, request_id="rid")
      for fn in filenames:
          assert "/" not in fn and "\\" not in fn
  ```
- Step 2：跑 → 5 FAIL
- Step 3：实现：
  ```python
  import os, shutil
  from pathlib import Path

  def write_per_uid_atomic(items, *, bucket_dir, output_format, overwrite,
                            request_id):
      tmp_dir = bucket_dir / f".tmp_{request_id}"
      try:
          tmp_dir.mkdir(parents=False, exist_ok=False)
      except FileExistsError:
          raise OutputWriterError(ErrorType.OUTPUT_WRITE_FAILED,
              "output write failed", request_id=request_id)
      filenames: list[str] = []
      try:
          for uid, payload in items:
              fn = f"{uid}.{output_format}"
              (tmp_dir / fn).write_bytes(payload)
              filenames.append(fn)
          if not overwrite:
              for fn in filenames:
                  if (bucket_dir / fn).exists():
                      raise OutputWriterError(ErrorType.RESULT_VALIDATION_FAILED,
                          "result validation failed", request_id=request_id)
          for fn in filenames:
              os.replace(tmp_dir / fn, bucket_dir / fn)
      except OutputWriterError:
          shutil.rmtree(tmp_dir, ignore_errors=True)
          raise
      except Exception:
          shutil.rmtree(tmp_dir, ignore_errors=True)
          raise OutputWriterError(ErrorType.OUTPUT_WRITE_FAILED,
              "output write failed", request_id=request_id) from None
      shutil.rmtree(tmp_dir, ignore_errors=True)
      return filenames
  ```
- Step 4：跑 → 5 PASS
- Step 5：`git add data_acquisition_agent/output_writer.py data_acquisition_agent/tests/test_output_writer.py && git commit -m "feat(da-agent): V2 atomic per-uid writer"`

**完成标准**：5 case PASS

### Task 4.4 — resolve_bucket_dir（settings 路径解析）

- **Files Modify**: `data_acquisition_agent/output_writer.py`, `data_acquisition_agent/tests/test_output_writer.py`

**TDD 步骤**

- Step 1：追加 1 测试：
  ```python
  import os

  def test_resolve_bucket_dir_from_settings():
      from app.core.config import settings
      from data_acquisition_agent.output_writer import resolve_bucket_dir
      assert str(resolve_bucket_dir("app")).endswith(
          settings.app_by_uid_dir.replace("/", os.sep))
      assert str(resolve_bucket_dir("behavior")).endswith(
          settings.behavior_by_uid_dir.replace("/", os.sep))
      assert str(resolve_bucket_dir("credit")).endswith(
          settings.credit_by_uid_dir.replace("/", os.sep))
  ```
- Step 2：跑 → FAIL
- Step 3：实现：
  ```python
  from app.core.config import settings

  _BUCKET_TO_ATTR = {
      "app": "app_by_uid_dir",
      "behavior": "behavior_by_uid_dir",
      "credit": "credit_by_uid_dir",
  }

  def resolve_bucket_dir(output_bucket: str) -> Path:
      return settings.resolve_path(getattr(settings, _BUCKET_TO_ATTR[output_bucket]))
  ```
- Step 4：跑 → PASS
- Step 5：`git add data_acquisition_agent/output_writer.py data_acquisition_agent/tests/test_output_writer.py && git commit -m "feat(da-agent): V2 resolve bucket dir"`

**完成标准**：1 case PASS（Phase 4 累计 14 case）

---

## V2 Phase 5 — run_execute_pipeline + api.py /execute

### Task 5.1 — run_execute_pipeline 编排

- **Files Modify**: `data_acquisition_agent/executor.py`, `data_acquisition_agent/tests/test_executor.py`

**TDD 步骤**

- Step 1：追加测试（mock connection + manifest）：
  ```python
  from data_acquisition_agent.executor import run_execute_pipeline
  from data_acquisition_agent.schemas import ExecuteRequest

  def _exec_req(**kw):
      defaults = dict(
          approved_sql=("SELECT uid, app_name, app_package, first_install_time, "
                        "last_update_time, gp_category, ai_category_level_2_CN "
                        "FROM dm_model.yyp_tmp_x"),
          sql_kind="query_only", target_country="mexico", approved_by="t",
          output_bucket="app", output_format="csv", uid_column="uid")
      defaults.update(kw)
      return ExecuteRequest(**defaults)

  def _mock_conn_pipeline(rows_count: int):
      conn = MagicMock()
      cur = MagicMock()
      cur.fetchone.return_value = (rows_count,)
      cur.description = [(c,) for c in
          ["uid","app_name","app_package","first_install_time",
           "last_update_time","gp_category","ai_category_level_2_CN"]]
      cur.fetchall.return_value = [
          ("u1","WA","p","t","t","g","c"),
          ("u2","FB","p","t","t","g","c")]
      conn.cursor.return_value.__enter__.return_value = cur
      return conn

  def test_pipeline_happy_path(monkeypatch, tmp_path):
      from data_acquisition_agent import executor as ex
      from data_acquisition_agent import output_writer as ow
      bucket = tmp_path / "app"; bucket.mkdir()
      monkeypatch.setattr(ow, "resolve_bucket_dir", lambda b: bucket)
      class CM:
          def __enter__(self_): return _mock_conn_pipeline(2)
          def __exit__(self_, *a): return False
      monkeypatch.setattr(ex, "open_starrocks_connection", lambda **kw: CM())

      result = run_execute_pipeline(_exec_req(), request_id="rid-happy")
      assert result["output_bucket"] == "app"
      assert result["written_file_count"] == 2
      assert sorted(result["filenames"]) == ["u1.csv", "u2.csv"]
      assert result["total_uids"] == 2
      assert result["metadata"]["row_count_total"] == 2

  def test_pipeline_build_table_script_rejected_no_connect(monkeypatch):
      from data_acquisition_agent import executor as ex
      called = {"connect": 0}
      class _NeverEnter:
          def __enter__(self_): called["connect"] += 1; return MagicMock()
          def __exit__(self_, *a): return False
      monkeypatch.setattr(ex, "open_starrocks_connection",
          lambda **kw: _NeverEnter())
      req = _exec_req(sql_kind="build_table_script",
          approved_sql="CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1")
      with pytest.raises(ExecutorError) as ei:
          run_execute_pipeline(req, request_id="rid-no")
      assert ei.value.error_type == ErrorType.DDL_NOT_SUPPORTED_IN_V2
      assert called["connect"] == 0  # T1：守门在前，不连库
  ```
- Step 2：跑 → 2 FAIL
- Step 3：实现：
  ```python
  import time
  from datetime import datetime, timezone
  from app.core.config import settings
  from .connection import open_starrocks_connection
  from .manifest import load_manifest
  from .output_writer import (validate_bucket_schema, build_per_uid_payloads,
      write_per_uid_atomic, resolve_bucket_dir)

  def run_execute_pipeline(request, *, request_id):
      manifest = load_manifest(request.target_country.value)
      enforce_pre_execution_gates(approved_sql=request.approved_sql,
          sql_kind=request.sql_kind,
          analyst_private_prefix=manifest.analyst_private_prefix,
          request_id=request_id)
      t0 = time.monotonic()
      executed_at = datetime.now(timezone.utc).isoformat()
      with open_starrocks_connection(request_id=request_id) as conn:
          precheck_row_count(conn=conn, approved_sql=request.approved_sql,
              max_rows=settings.da_max_result_rows,
              timeout_s=settings.da_query_timeout_seconds,
              request_id=request_id)
          df = execute_query(conn=conn, approved_sql=request.approved_sql,
              timeout_s=settings.da_query_timeout_seconds,
              request_id=request_id)
      validate_bucket_schema(df, output_bucket=request.output_bucket,
          output_format=request.output_format, uid_column=request.uid_column,
          request_id=request_id)
      items = build_per_uid_payloads(df, output_bucket=request.output_bucket,
          output_format=request.output_format, uid_column=request.uid_column,
          approved_by=request.approved_by,
          source_request_id=request.source_request_id,
          executed_at=executed_at, request_id=request_id)
      bucket_dir = resolve_bucket_dir(request.output_bucket)
      bucket_dir.mkdir(parents=True, exist_ok=True)
      filenames = write_per_uid_atomic(items, bucket_dir=bucket_dir,
          output_format=request.output_format, overwrite=request.overwrite,
          request_id=request_id)
      duration_ms = int((time.monotonic() - t0) * 1000)
      rows_per_uid = {uid: int((df[request.uid_column] == uid).sum())
                       for uid, _ in items}
      return {
          "request_id": request_id,
          "output_bucket": request.output_bucket,
          "output_format": request.output_format,
          "filenames": filenames,
          "written_file_count": len(filenames),
          "total_uids": len(items),
          "rows_per_uid": rows_per_uid,
          "metadata": {
              "executed_at": executed_at,
              "approved_by": request.approved_by,
              "source_request_id": request.source_request_id,
              "duration_ms": duration_ms,
              "row_count_total": int(len(df)),
          },
      }
  ```
- Step 4：跑 → 2 PASS
- Step 5：`git add data_acquisition_agent/executor.py data_acquisition_agent/tests/test_executor.py && git commit -m "feat(da-agent): V2 execute pipeline"`

**完成标准**：2 case PASS（Phase 3+5 累计 22 case）

### Task 5.2 — api.py /execute 接编排 + 统一错误映射

- **Files Modify**: `data_acquisition_agent/api.py`
- **Files Create**: `data_acquisition_agent/tests/test_api_v2.py`

**TDD 步骤**

- Step 1：写测试：
  ```python
  import pytest
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from data_acquisition_agent.api import router
  from data_acquisition_agent import api as api_mod
  from data_acquisition_agent.executor import ExecutorError
  from data_acquisition_agent.connection import DbUnreachableError
  from data_acquisition_agent.schemas import ErrorType

  def _client(): app = FastAPI(); app.include_router(router); return TestClient(app)

  def _req(): return {"approved_sql":"SELECT 1","sql_kind":"query_only",
      "target_country":"mexico","approved_by":"t",
      "output_bucket":"app","output_format":"csv","uid_column":"uid"}

  def test_execute_happy_path_returns_200(monkeypatch):
      monkeypatch.setattr(api_mod, "_run_execute_pipeline",
          lambda req, request_id: {"request_id": request_id,
              "output_bucket":"app","output_format":"csv",
              "filenames":["u1.csv"], "written_file_count":1, "total_uids":1,
              "rows_per_uid":{"u1":1},
              "metadata":{"executed_at":"t","approved_by":"t",
                  "source_request_id":None,"duration_ms":1,"row_count_total":1}})
      r = _client().post("/api/data-acquisition/execute", json=_req())
      assert r.status_code == 200
      assert r.json()["written_file_count"] == 1

  @pytest.mark.parametrize("etype,expected_status,expected_msg", [
      (ErrorType.DDL_NOT_SUPPORTED_IN_V2, 422, "DDL is not executable by V2"),
      (ErrorType.QUERY_FAILED,            422, "query execution failed"),
      (ErrorType.RESULT_VALIDATION_FAILED,422, "result validation failed"),
      (ErrorType.RESULT_TOO_LARGE,        413, "result exceeds row limit"),
      (ErrorType.OUTPUT_WRITE_FAILED,     500, "output write failed"),
  ])
  def test_execute_v2_error_mapping(monkeypatch, etype, expected_status,
                                     expected_msg):
      def boom(req, request_id):
          raise ExecutorError(etype, expected_msg, request_id=request_id)
      monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
      r = _client().post("/api/data-acquisition/execute", json=_req())
      assert r.status_code == expected_status
      body = r.json()
      assert body["error_type"] == etype.value
      assert body["message"] == expected_msg
      assert body["request_id"]

  def test_execute_db_unreachable_mapped(monkeypatch):
      def boom(req, request_id):
          raise DbUnreachableError(request_id=request_id)
      monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
      r = _client().post("/api/data-acquisition/execute", json=_req())
      assert r.status_code == 502
      assert r.json()["error_type"] == "db_unreachable"
      assert r.json()["message"] == "database connection failed"

  def test_execute_response_no_absolute_path_or_sql_echo(monkeypatch):
      monkeypatch.setattr(api_mod, "_run_execute_pipeline",
          lambda req, request_id: {"request_id": request_id,
              "output_bucket":"app","output_format":"csv",
              "filenames":["u1.csv"], "written_file_count":1, "total_uids":1,
              "rows_per_uid":{"u1":1},
              "metadata":{"executed_at":"t","approved_by":"t",
                  "source_request_id":None,"duration_ms":1,"row_count_total":1}})
      r = _client().post("/api/data-acquisition/execute", json=_req())
      body_text = r.text
      assert "SELECT 1" not in body_text
      assert "/data/" not in body_text and "\\data\\" not in body_text

  def test_execute_invalid_country_422():
      r = _client().post("/api/data-acquisition/execute",
          json={**_req(), "target_country":"atlantis"})
      assert r.status_code == 422  # Pydantic enum 校验
  ```
- Step 2：跑 → 8 FAIL
- Step 3：实现 api.py /execute（保留 V1 /generate 不动）：
  ```python
  import uuid
  from .schemas import ExecuteRequest, ExecuteResponse
  from .executor import run_execute_pipeline as _run_execute_pipeline
  from .executor import ExecutorError
  from .output_writer import OutputWriterError
  from .connection import DbUnreachableError

  @router.post("/execute", response_model=ExecuteResponse)
  def execute(request: ExecuteRequest):
      rid = str(uuid.uuid4())
      try:
          payload = _run_execute_pipeline(request, request_id=rid)
          return ExecuteResponse(**payload)
      except DbUnreachableError:
          err = ErrorResponse(error_type=ErrorType.DB_UNREACHABLE,
              message="database connection failed", request_id=rid)
          return JSONResponse(status_code=502,
              content=err.model_dump(mode="json"))
      except (ExecutorError, OutputWriterError) as e:
          err = ErrorResponse(error_type=e.error_type, message=e.message,
              request_id=e.request_id or rid)
          return JSONResponse(status_code=_STATUS_MAP[e.error_type],
              content=err.model_dump(mode="json"))
  ```
- Step 4：跑 → 9 PASS（happy + 5 parametrize + db_unreachable + no-leak + invalid-country = 9；其中 invalid-country 不需 mock，通过 Pydantic 直接 422）
- Step 5：`git add data_acquisition_agent/api.py data_acquisition_agent/tests/test_api_v2.py && git commit -m "feat(da-agent): V2 wire api /execute to pipeline"`

**完成标准**：9 case PASS

---

## V2 Phase 6 — T1-T4 安全测试 + e2e mock executor

### Task 6.1 — T1: build_table_script 不连库（独立断言点）

- **Files Modify**: `data_acquisition_agent/tests/test_e2e_mock_executor.py`

**TDD 步骤**

- Step 1：替换文件（去 pytestmark.skip）：
  ```python
  import pytest
  from unittest.mock import MagicMock, patch
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from data_acquisition_agent.api import router

  def _client(): app = FastAPI(); app.include_router(router); return TestClient(app)

  def _req_ddl(): return {"approved_sql":"CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1",
      "sql_kind":"build_table_script","target_country":"mexico","approved_by":"t",
      "output_bucket":"app","output_format":"csv","uid_column":"uid"}

  def test_t1_build_table_script_422_no_connect():
      called = {"n": 0}
      def fail_connect(*a, **kw): called["n"] += 1; raise AssertionError("must not connect")
      with patch("data_acquisition_agent.connection.pymysql.connect",
                 side_effect=fail_connect):
          r = _client().post("/api/data-acquisition/execute", json=_req_ddl())
      assert r.status_code == 422
      assert r.json()["error_type"] == "ddl_not_supported_in_v2"
      assert r.json()["message"] == "DDL is not executable by V2"
      assert called["n"] == 0
  ```
- Step 2/3/4：跑 → PASS
- Step 5：`git add data_acquisition_agent/tests/test_e2e_mock_executor.py && git commit -m "feat(da-agent): V2 T1 build_table_script no-connect"`

**完成标准**：T1 PASS

### Task 6.2 — T2: query_only 含 DDL/DML 被拒（参数化 7 类）

- **Files Modify**: `data_acquisition_agent/tests/test_e2e_mock_executor.py`

**TDD 步骤**

- Step 1：追加：
  ```python
  @pytest.mark.parametrize("sql", [
      "CREATE TABLE x AS SELECT 1", "DROP TABLE x", "ALTER TABLE x ADD c INT",
      "TRUNCATE TABLE x", "INSERT INTO x VALUES (1)",
      "UPDATE x SET a=1", "DELETE FROM x WHERE 1=1",
  ])
  def test_t2_query_only_rejects_ddl_dml(sql, monkeypatch):
      from data_acquisition_agent import executor as ex
      monkeypatch.setattr(ex, "open_starrocks_connection",
          lambda **kw: pytest.fail("must not connect"))
      r = _client().post("/api/data-acquisition/execute",
          json={**_req_ddl(), "sql_kind":"query_only", "approved_sql": sql})
      assert r.status_code == 422
      assert r.json()["error_type"] == "ddl_policy_violation"
  ```
- Step 2/3/4：跑 → 7 PASS
- Step 5：`git add data_acquisition_agent/tests/test_e2e_mock_executor.py && git commit -m "feat(da-agent): V2 T2 query_only DDL/DML reject"`

**完成标准**：7 case PASS

### Task 6.3 — T3: connection 不 log secret + response 不含合成密码

- **Files Modify**: `data_acquisition_agent/tests/test_e2e_mock_executor.py`

**TDD 步骤**

- Step 1：追加：
  ```python
  SECRET = "FAKE_PW_DO_NOT_LEAK_42"

  def test_t3_db_unreachable_no_secret_in_log_or_response(monkeypatch, caplog):
      monkeypatch.setenv("DA_DB_HOST", "10.0.0.1")
      monkeypatch.setenv("DA_DB_PORT", "9030")
      monkeypatch.setenv("DA_DB_USER", "ro_user")
      monkeypatch.setenv("DA_DB_PASSWORD", SECRET)
      monkeypatch.setenv("DA_DB_DATABASE", "dm_fake")
      with patch("data_acquisition_agent.connection.pymysql.connect",
                 side_effect=Exception(f"Access denied (password={SECRET})")):
          import logging
          with caplog.at_level(logging.DEBUG):
              r = _client().post("/api/data-acquisition/execute",
                  json={"approved_sql":"SELECT uid FROM dm_model.yyp_tmp_x",
                        "sql_kind":"query_only","target_country":"mexico",
                        "approved_by":"t","output_bucket":"app",
                        "output_format":"csv","uid_column":"uid"})
      assert r.status_code == 502
      assert SECRET not in r.text
      for record in caplog.records:
          assert SECRET not in record.getMessage()
          assert SECRET not in str(record.args or "")
      assert SECRET not in r.json().get("message", "")
  ```
- Step 2/3/4：跑 → PASS
- Step 5：`git add data_acquisition_agent/tests/test_e2e_mock_executor.py && git commit -m "feat(da-agent): V2 T3 connection no secret leak"`

**完成标准**：T3 PASS

### Task 6.4 — T4: 6 类 V2 error response 固定 message

- **Files Modify**: `data_acquisition_agent/tests/test_e2e_mock_executor.py`

**TDD 步骤**

- Step 1：追加：
  ```python
  from data_acquisition_agent import api as api_mod
  from data_acquisition_agent.executor import ExecutorError
  from data_acquisition_agent.connection import DbUnreachableError
  from data_acquisition_agent.schemas import ErrorType

  V2_ERRORS = [
      (ErrorType.DDL_NOT_SUPPORTED_IN_V2, "DDL is not executable by V2"),
      (ErrorType.QUERY_FAILED,            "query execution failed"),
      (ErrorType.RESULT_VALIDATION_FAILED,"result validation failed"),
      (ErrorType.RESULT_TOO_LARGE,        "result exceeds row limit"),
      (ErrorType.OUTPUT_WRITE_FAILED,     "output write failed"),
  ]

  @pytest.mark.parametrize("etype,fixed_msg", V2_ERRORS)
  def test_t4_response_has_fixed_message_no_payload(monkeypatch, etype, fixed_msg):
      LEAK_HINT = "uid app_name SELECT FROM dm_model.yyp_tmp_x"
      def boom(req, request_id):
          raise ExecutorError(etype, fixed_msg, request_id=request_id)
      monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
      r = _client().post("/api/data-acquisition/execute",
          json={"approved_sql": LEAK_HINT,"sql_kind":"query_only",
              "target_country":"mexico","approved_by":"t",
              "output_bucket":"app","output_format":"csv","uid_column":"uid"})
      body = r.json()
      assert body["message"] == fixed_msg
      assert "SELECT" not in body["message"]
      assert "dm_model" not in body["message"]
      assert "app_name" not in body["message"]

  def test_t4_db_unreachable_fixed_message(monkeypatch):
      def boom(req, request_id):
          raise DbUnreachableError(request_id=request_id)
      monkeypatch.setattr(api_mod, "_run_execute_pipeline", boom)
      r = _client().post("/api/data-acquisition/execute",
          json={"approved_sql":"SELECT 1","sql_kind":"query_only",
              "target_country":"mexico","approved_by":"t",
              "output_bucket":"app","output_format":"csv","uid_column":"uid"})
      assert r.json()["message"] == "database connection failed"
  ```
- Step 2/3/4：跑 → 6 PASS
- Step 5：`git add data_acquisition_agent/tests/test_e2e_mock_executor.py && git commit -m "feat(da-agent): V2 T4 fixed error messages"`

**完成标准**：6 case PASS

### Task 6.5 — e2e mock executor happy path（mexico app bucket）

- **Files Modify**: `data_acquisition_agent/tests/test_e2e_mock_executor.py`

**TDD 步骤**

- Step 1：追加 happy path：
  ```python
  def test_e2e_happy_path_app_bucket_mexico(monkeypatch, tmp_path):
      from data_acquisition_agent import executor as ex
      from data_acquisition_agent import output_writer as ow
      bucket = tmp_path / "app_by_uid"; bucket.mkdir()
      monkeypatch.setattr(ow, "resolve_bucket_dir", lambda b: bucket)

      def fake_open(**kw):
          conn = MagicMock()
          cur = MagicMock()
          cur.fetchone.return_value = (3,)
          cur.description = [(c,) for c in
              ["uid","app_name","app_package","first_install_time",
               "last_update_time","gp_category","ai_category_level_2_CN"]]
          cur.fetchall.return_value = [
              ("u1","WA","p","t","t","g","c"),
              ("u1","FB","p","t","t","g","c"),
              ("u2","TG","p","t","t","g","c")]
          conn.cursor.return_value.__enter__.return_value = cur
          class CM:
              def __enter__(self_): return conn
              def __exit__(self_, *a): return False
          return CM()
      monkeypatch.setattr(ex, "open_starrocks_connection", fake_open)

      r = _client().post("/api/data-acquisition/execute",
          json={"approved_sql":("SELECT uid, app_name, app_package, first_install_time, "
                                "last_update_time, gp_category, ai_category_level_2_CN "
                                "FROM dm_model.yyp_tmp_x"),
                "sql_kind":"query_only","target_country":"mexico",
                "approved_by":"alice","output_bucket":"app",
                "output_format":"csv","uid_column":"uid"})
      assert r.status_code == 200, r.text
      body = r.json()
      assert body["written_file_count"] == 2
      assert body["total_uids"] == 2
      assert sorted(body["filenames"]) == ["u1.csv", "u2.csv"]
      assert body["metadata"]["row_count_total"] == 3
      assert body["metadata"]["approved_by"] == "alice"
      assert (bucket / "u1.csv").exists()
      assert (bucket / "u2.csv").exists()
  ```
- Step 2/3/4：跑 → PASS
- Step 5：`git add data_acquisition_agent/tests/test_e2e_mock_executor.py && git commit -m "feat(da-agent): V2 e2e mock executor happy path [complete]"`

**完成标准**：1 case PASS；全套 `python -m pytest data_acquisition_agent/tests/ -v` 全绿（V1 72 + V2 71 = 143）

---

## Commit 策略

1. **执行前打基线**（Phase 1 之前）：
   ```bash
   git commit --allow-empty -m "[baseline] data_acquisition_agent_v2"
   ```
2. 每个 Task 完成立即 commit，commit message 见各 Task Step 5
3. **禁止** `git add -A`；每次只 add 该 Task 显式列出的文件
4. **最后一个 commit 必须含 `[complete]` 标签**：Task 6.5 已含

## 停止条件（遇到以下情况立即停下汇报，不要猜测或绕过）

- pymysql 安装失败（环境冲突）→ 停，问用户是否切换 driver
- output_scanner._strip_sql_comments 私有签名变化 → 停，不要私自改 V1
- COUNT 包裹后 SQL 在 StarRocks 上语义不等价（部署 smoke 才能发现）→ 停，记录 V3 follow-up
- 任何 Task 实测 case 数与 Plan 预估不符 → 停，对齐 Plan
- T3 假凭据出现在 caplog 任一 record → 停，根因排查 logger，不绕过
- V1 72 测试出现回归 → 停，不要修改 V1 代码逻辑

## 预估总测试用例数

| 测试文件 | 用例数 | 累计 |
|---|---|---|
| test_schemas.py（V2 新增）| 5 | 5 |
| test_connection.py | 5 | 10 |
| test_executor.py（gates 13 + count 4 + execute 3 + pipeline 2）| 22 | 32 |
| test_output_writer.py（schema 5 + payloads 3 + atomic 5 + resolve 1）| 14 | 46 |
| test_api_v2.py | 9 | 55 |
| test_e2e_mock_executor.py（T1 1 + T2 7 + T3 1 + T4 6 + happy 1）| 16 | 71 |
| **V2 合计** | **71** | — |
| V1 现有 | 72 | — |
| **总合计** | **143** | — |

## 已知风险及应对

| # | 风险 | 应对 |
|---|---|---|
| 1 | pymysql 在 StarRocks FE 上 driver 协议不完全兼容（罕见 SET SESSION 失败）| Phase 3 不做 SET SESSION timeout；timeout 暂用 connect_timeout，运行时 query timeout 留 V3 |
| 2 | COUNT(*) 包裹改变 StarRocks 优化器行为（性能差异）| V2 接受；V3 可加 EXPLAIN 预检 |
| 3 | _strip_sql_comments 是 V1 私有函数（_前缀），import 等于跨模块依赖 | V1 不动，V2 直接 import；如 V1 重构需协调 |
| 4 | resolve_bucket_dir 走 settings.resolve_path 后是绝对路径，调用方误把它当 filename | API 响应只回 filenames（不含 path），test_api_v2 / T4 已断言无 `/data/` |
| 5 | 多文件 os.replace 中途崩溃 → bucket_dir 半新半旧（Design Doc §8.4） | 文档化接受；Future Optional：rsync-style 双目录 |
| 6 | 并发同 request 写同 bucket → .tmp_<rid> 同名冲突 | request_id 是 uuid4，碰撞概率忽略；mkdir(exist_ok=False) 已防御 |
| 7 | overwrite=false 时 mid-batch 检测到冲突，已写到 .tmp 的文件需回滚 | 实现先 mkdir → 全部写 tmp → 检查 conflict → replace；冲突时 rmtree(.tmp)，bucket_dir 保持原样 |
| 8 | T3 caplog 不抓 stdout/print → 偷偷 print 密码无法检测 | 项目 logger 用 logging（`get_logger`），无 print；caplog 已覆盖 |
| 9 | request_id 透传：DbUnreachableError 在 connection.py 抛出，但 ExecuteResponse 需要 api 层 rid | api.py /execute 用 `e.request_id or rid` 兜底；test_api_v2 已覆盖 |
| 10 | StarRocks SQL 方言差异（`AS da_v2_count` 别名要求）| Phase 3.2 已用 `AS da_v2_count`；smoke checklist 二次确认 |
| 11 | Windows 路径分隔符差异导致 resolve_bucket_dir 测试 flaky | 用 `os.sep` 替换断言；test 已写成 `replace("/", os.sep)` |

## 五点检查法自检

1. **每个 Task 有精确文件路径？** ✅ 全部 Task 列 Files Modify/Create
2. **有 TBD/TODO/占位符？** ✅ Plan 主体无未决；timeout SET SESSION 显式 defer 到 V3（风险表 #1）
3. **代码步骤有最小可执行代码块？** ✅ 每 Task Step 1 含可粘贴测试，Step 3 含 patch 级实现
4. **有验证命令 + 预期输出？** ✅ 每 Task Step 2/4 有 pytest 命令 + FAIL/PASS 预期
5. **一个人不问问题能执行完？** ✅ Driver / Mock 策略 / Phase 编号 / T1-T4 编排 / Plan 路径全部已确认
