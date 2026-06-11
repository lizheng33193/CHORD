# data_acquisition_agent V2 — 白盒审计报告

> 审计基线：`c8793e3` → HEAD `5ef1699`
> 关联 Design：[docs/specs/data_acquisition_agent_v2.md](../specs/data_acquisition_agent_v2.md)
> 关联 Plan：[docs/plans/data-acquisition-v2-plan.md](../plans/data-acquisition-v2-plan.md)
> 审计日期：2026-04-30

---

## 1. 概述

V1 完成"自然语言 → SQL/Python artifact"，但显式不连库。V2 是**受控执行层**：分析师拿到 V1 artifact 经人工审核后把 `approved_sql` 提交给 V2 → V2 三层守门 → COUNT(*) 预检 → query_only 执行 → bucket 切片 → per-uid 文件原子落到 LocalUserRepository 期望目录。**仅执行 query_only**；`build_table_script` 一律 422 拒绝（DDL 仍由分析师在 StarRocks client 手跑 — CLAUDE.md "不得自动执行 SQL" Zero Tolerance 条款）。

产出：71 V2 tests（V1 72 + V2 71 + 1 skipped 全量 153 通过，0 failed）；新增 3 个运行时模块（connection / executor / output_writer）+ 6 类新 ErrorType + 1 个 `/execute` 端点。

## 2. 技术路线

- **凭据零泄漏（最关键设计）**：DB 凭据**只**通过 `os.environ` 在执行那一刻读取，仅存在局部变量 + 短生命周期连接对象；**不入** `app.core.config.Settings` 字段、不入 `model_dump`、不入 `__repr__`、不入 module-level 全局、不入日志。Settings 仅持有非敏感配置（`DA_MAX_RESULT_ROWS` / `DA_QUERY_TIMEOUT_SECONDS` / `DA_CONNECTION_PROFILE`）。`_RedactedConnection` wrapper 覆写 `__repr__` 返回固定占位符 `<RedactedStarRocksConnection>`。
- **三层守门复用 V1 + multi-statement 拦截**：`enforce_pre_execution_gates` 在执行前依次跑 `scan_credentials` / `scan_python_dangerous` / `check_sql_policy(query_only)` / split-statement 检查（防 `SELECT 1; DROP TABLE x`）；`build_table_script` 在最前面直接拒，**永不连库**。
- **DB RBAC 双层防御**：应用层正则 + 部署侧 StarRocks 账号只授 SELECT — 应用层正则被绕过时 DB 仍拒。RBAC 自动化测试不验证（属部署 smoke checklist），但文档显式登记。
- **COUNT(*) 预检**：`SELECT COUNT(*) FROM (<approved_sql>) AS da_v2_count` 包裹，超 `DA_MAX_RESULT_ROWS`（默认 100000）→ 413 `result_too_large`，避免大结果集打爆内存。
- **原子落盘 + 显式接受 trade-off**：单文件 `os.replace` POSIX/Windows atomic；多文件中途崩溃可能"半新半旧"，Design Doc §8.4 明确接受，缓解策略是分析师重跑同一 request。`.tmp_<request_id>/` 隔离写入过程，失败 `shutil.rmtree(.tmp)` 回滚。
- **错误响应固定短文本**：6 类 V2 错误码 + 3 类 V1 沿用，所有 message 是预定义常量字符串（"DDL is not executable by V2" / "database connection failed" / "query execution failed" / "result validation failed" / "result exceeds row limit" / "output write failed"），不参数化、不 f-string、不 format。子原因（`bucket_schema_mismatch` / `output_file_conflict` / `result_empty` / `missing_uid_column`）仅进内部 log，不进 response。
- **per-uid JSON wrapper**：behavior/credit bucket json 落地用 `{schema_version: "da_agent_v2", source_meta, uid, rows}` 外壳，给未来 schema 演进灰度的余地。

## 3. 变更文件清单

来源：`git diff c8793e3..5ef1699 --stat`，2060 insertions / 51 deletions / 23 files。

| 类型 | 文件 | 行数 | 说明 |
|---|---|---|---|
| Modify | [.env.example](../../.env.example) | +10 | DA_DB_* 占位符 + V2 非敏感配置 |
| Modify | [PLANNING.md](../../PLANNING.md) | +63 | V2 模块结构、Step 3 Stub、Step 5 完成记录 |
| Modify | [TASK.md](../../TASK.md) | +43 | V2 Phase 1-6 任务跟踪 |
| Modify | [app/core/config.py](../../app/core/config.py) | +4 | 3 个非敏感字段（max_rows / timeout / connection_profile）|
| Modify | [requirements.txt](../../requirements.txt) | +1 | pymysql |
| Create | [data_acquisition_agent/connection.py](../../data_acquisition_agent/connection.py) | +56 | env→pymysql 短生命周期 + `DbUnreachableError` + `_RedactedConnection` |
| Create | [data_acquisition_agent/executor.py](../../data_acquisition_agent/executor.py) | +155 | 守门 + COUNT 预检 + execute_query + run_execute_pipeline |
| Create | [data_acquisition_agent/output_writer.py](../../data_acquisition_agent/output_writer.py) | +153 | bucket 切片 + schema 校验 + .tmp + os.replace + resolve_bucket_dir |
| Modify | [data_acquisition_agent/schemas.py](../../data_acquisition_agent/schemas.py) | +61 | ExecuteRequest / ExecuteResponse + 6 类新 ErrorType + validators |
| Modify | [data_acquisition_agent/api.py](../../data_acquisition_agent/api.py) | +34 | `/execute` 端点 + 6 类 V2 ErrorType → HTTP 映射 + db_unreachable 502 |
| Modify | [data_acquisition_agent/orchestrator.py](../../data_acquisition_agent/orchestrator.py) | +22 / -... | V1 ErrorResponse 安全短消息收尾 |
| Modify | [data_acquisition_agent/prompt_assembler.py](../../data_acquisition_agent/prompt_assembler.py) | +34 / -... | V1 prompt hardening 收尾 |
| Modify | [data_acquisition_agent/output_scanner.py](../../data_acquisition_agent/output_scanner.py) | +8 | V1 hardening |
| Create/Modify | `data_acquisition_agent/tests/*.py` | +691 | 6 个测试文件，71 V2 tests |
| Create | [docs/specs/data_acquisition_agent_v2.md](../specs/data_acquisition_agent_v2.md) | +697 | V2 Design Doc |

## 4. 正确性判断

- **TDD 严格**：6 Phase / 16 Task / 16 commit，每 Task TDD 5 步流程，最后 commit 含 `[complete]` 标签（5ef1699）。
- **6 类新 ErrorType 全覆盖**：`ddl_not_supported_in_v2 422` / `db_unreachable 502` / `query_failed 422` / `result_validation_failed 422` / `result_too_large 413` / `output_write_failed 500`，HTTP 映射在 `test_api_v2.py` 9 case parametrize 全验证。
- **3 类 V1 沿用错误**：`credential_leak` / `dangerous_code` / `ddl_policy_violation` 在 V2 守门重新跑，不信任 V1 输出（即便有 `source_request_id` 关联）。
- **request_id 透传**：`DbUnreachableError` 在 `connection.py` 抛但需要 api 层 rid，`api.py` 用 `e.request_id or rid` 兜底，测试覆盖。
- **Pipeline 编排**：`run_execute_pipeline` = `load_manifest → enforce_gates → open_connection → precheck → execute → validate_schema → build_payloads → resolve_bucket_dir → mkdir → write_atomic`，每一步失败映射到正确 ErrorType。
- **零回归**：V1 72 tests 全过；全量 153 passed + 1 skipped + 0 failed。

## 5. 安全扫描

### 5.1 凭据零泄漏（V2 安全核心）

- **测试 T3 显式断言**：合成假凭据 `FAKE_PW_DO_NOT_LEAK_42` 在 driver exception message 中故意带泄漏 → response.text / response.message / caplog.records 均不出现。
- **`_RedactedConnection.__repr__`**：测试断言 `repr(conn)` 不含 host / password / user / database 任一明文。
- **driver exception 封装**：所有 driver `Exception` 经 `except Exception: raise DbUnreachableError(...) from None`，**不带 chain**，不向上层透传原 message。
- **logger 白名单**：仅 `request_id / error_type / exception_class_name / stage / duration_ms / row_count_total / output_bucket / output_format`；黑名单（永不进 log）：`Exception.message` / SQL 文本 / DB host / database / username / password / port / 表名 / 列名 / `uid_column` 实际值 / DataFrame 内容 / 文件内容 / 绝对路径 / `approved_by` / `approval_note`。
- **`approved_by` / `approval_note`** 设计为审计 metadata，进**审计** logger（独立分离），不进运行时 logger。

### 5.2 SQL 安全

- `build_table_script` 永远 422 + 测试断言 `pymysql.connect` **不被调用**（T1 用 `side_effect=fail_connect`）— 守门在前，连库在后。
- `query_only` 含 7 类 DDL/DML 关键字（CREATE/DROP/ALTER/TRUNCATE/INSERT/UPDATE/DELETE）→ ddl_policy_violation 422（T2 parametrize 7 case）。
- multi-statement 拦截：strip 注释后 `;` split，token > 1 → 422，防 `SELECT 1; DROP TABLE x`；注释里的 `;` 不触发（`test_gate_strips_comments_before_split`）。
- COUNT(*) 包裹 `SELECT COUNT(*) FROM (<sql>) AS da_v2_count`，DB 异常 → query_failed，不暴露子原因。

### 5.3 输出安全

- Response 不含：绝对路径 / 文件内容 / DataFrame 行 / SQL 回声 / DB error message。
- `filenames` 仅文件名（无目录），测试断言不含 `/` 或 `\`。
- 6 类 error message 固定常量，T4 parametrize 断言不含 `SELECT` / `dm_model` / `app_name` 等敏感 hint。

### 5.4 OWASP

- **A03 注入**：query_only RBAC 限制（部署侧）+ 应用层正则双重；DDL/DML 永不被 V2 执行。
- **A04 设计**：双层凭据隔离（env → 短生命周期）+ 短文本错误响应。
- **A05 配置**：DB 凭据不入 Settings → 不会被 model_dump 序列化到任何 API 响应。
- **A09 日志失败**：白名单 logger + caplog 测试 anti-leak。
- **A07 认证**：V2 自身不做 auth（依赖部署层），但响应不区分 "auth failed" vs "host unreachable"（避免攻击者枚举凭据有效性）— 都映射 502。

## 6. 性能考量

- **COUNT(*) 包裹的优化器代价**：StarRocks 优化器在子查询包 COUNT 时可能不走索引下推，性能略劣于直接 COUNT；V2 接受，V3 可加 EXPLAIN 预检。
- **同步阻塞 I/O**：pymysql + pandas DataFrame 一次性 fetchall；`DA_MAX_RESULT_ROWS` 默认 100000 行兜底。streaming / 分批写留 V3。
- **多文件 `os.replace`**：N 次 atomic rename，O(N) 次 syscall；中途崩溃 trade-off 已显式接受。
- **request_id 是 uuid4**：`.tmp_<rid>/` 碰撞概率忽略；mkdir(exist_ok=False) 防御。
- **timeout**：pymysql cursor 不直接支持 query timeout；当前依赖 `connect_timeout` 兜底，运行时 query timeout 留 V3。

## 7. 测试覆盖

| 文件 | 用例数 | 维度 |
|---|---|---|
| `test_schemas.py`（V2 增量） | 5 | app bucket 强制 csv / behavior allow json / credit allow csv / approved_sql 非空 / uid_column 默认 |
| `test_connection.py` | 5 | env 在 open 时读 / missing env → DbUnreachable / driver exception 不带原 message / `__repr__` 不暴露 / inner exception close |
| `test_executor.py` | 22 | gates 13（含 multi-statement / cred / dangerous_python / clean / comment-split） + count 4 + execute 3 + pipeline 2 |
| `test_output_writer.py` | 14 | schema 5 + payloads 3 + atomic 5（含回滚） + resolve 1 |
| `test_api_v2.py` | 9 | happy + 5 ErrorType parametrize + db_unreachable + no-leak + invalid_country |
| `test_e2e_mock_executor.py` | 16 | T1 1（DDL 不连库）+ T2 7（query_only DDL/DML 拒） + T3 1（凭据不 leak） + T4 6（固定 message） + happy 1 |
| **V2 合计** | **71** | — |
| **V1 + V2 + skipped** | **153 + 1** | 0 failed |

T1-T4 是 Design Doc §11.2 强制必做安全测试，全部通过。

## 8. 风险排查

| # | 风险 | 应对 |
|---|---|---|
| 1 | pymysql 在 StarRocks FE 上 SET SESSION 失败 | 不做 SET SESSION timeout；query timeout 留 V3 |
| 2 | COUNT(*) 包裹改变优化器行为（性能） | 接受；V3 可加 EXPLAIN |
| 3 | `_strip_sql_comments` 是 V1 私有函数（_前缀），跨模块依赖 | V1 不动；V1 重构需协调 V2 |
| 4 | `resolve_bucket_dir` 返回绝对路径 → 误回 response | response 只回 filenames；test_api_v2 + T4 显式断言无 `/data/` |
| 5 | 多文件 os.replace 中途崩溃 → bucket_dir 半新半旧 | Design Doc §8.4 文档化接受；分析师重跑刷最新；V3 双目录切换 |
| 6 | 并发同 request 写同 bucket → `.tmp_<rid>` 同名 | uuid4 碰撞忽略 + mkdir(exist_ok=False) 防御 |
| 7 | overwrite=false mid-batch 冲突，已写 .tmp 文件需回滚 | 先 mkdir → 全部写 tmp → 检查 conflict → replace；冲突时 rmtree(.tmp)，bucket 保持原样 |
| 8 | T3 caplog 不抓 stdout/print | 项目用 logging（无 print）；caplog 已覆盖 |
| 9 | Windows 路径分隔符差异 → resolve test flaky | 用 `os.sep` 替换断言 |
| 10 | StarRocks `AS da_v2_count` 别名要求 | 已用；smoke checklist 二次确认 |
| 11 | 部署侧 RBAC 配错（账号给了 INSERT） | 应用层正则补一层；smoke checklist 验证 `CREATE TABLE` 被 DB 拒 |

无 P0 阻塞；P1 风险全部有缓解或显式接受。

## 9. 运行时链路

```
POST /api/data-acquisition/execute (FastAPI)
  → ExecuteRequest Pydantic 校验
       ├── approved_sql 非空 / 强制 csv for app bucket
       └── target_country enum / sql_kind / bucket / format / uid_column
  → run_execute_pipeline(request, request_id)
       │
       ├── load_manifest(country) — placeholder → ManifestNotImplemented → 400
       │
       ├── enforce_pre_execution_gates(approved_sql, sql_kind, prefix, rid)
       │     ├── sql_kind == "build_table_script" → 422 ddl_not_supported_in_v2 (T1: 不连库)
       │     ├── scan_credentials → 422 credential_leak
       │     ├── scan_python_dangerous → 422 dangerous_code
       │     ├── check_sql_policy(query_only, prefix) → 422 ddl_policy_violation
       │     └── strip 注释后 split ";" → token > 1 → 422 ddl_policy_violation
       │
       ├── open_starrocks_connection(rid)  ← 凭据从 os.environ 即时读
       │     ├── missing env → DbUnreachableError → 502 db_unreachable
       │     ├── pymysql.connect(...) → 异常封装 DbUnreachableError → 502
       │     └── _RedactedConnection wrap raw → __repr__ 固定占位符
       │
       ├── precheck_row_count(conn, sql, max, timeout, rid)
       │     ├── SELECT COUNT(*) FROM (<sql>) AS da_v2_count
       │     ├── DB 异常 → 422 query_failed（不暴露子原因）
       │     └── n > max_rows → 413 result_too_large
       │
       ├── execute_query(conn, sql, timeout, rid)
       │     ├── DB 异常 → 422 query_failed
       │     └── 空结果 → 422 result_validation_failed
       │
       ├── validate_bucket_schema(df, bucket, format, uid_col, rid)
       │     ├── uid_column not in df.columns → 422 result_validation_failed
       │     ├── app + format ≠ csv → 422
       │     └── app 7 字段缺 → 422
       │
       ├── build_per_uid_payloads(df, ...)
       │     ├── csv: groupby(uid) → utf-8-sig BOM bytes
       │     └── json: {schema_version, source_meta, uid, rows} → utf-8 bytes
       │
       ├── resolve_bucket_dir(bucket) → settings.app_by_uid_dir 等
       │
       └── write_per_uid_atomic(items, bucket_dir, format, overwrite, rid)
             ├── mkdir bucket_dir/.tmp_<rid> (exist_ok=False)
             ├── 全部写 tmp → 任一失败 rmtree + 500 output_write_failed
             ├── overwrite=false 时检查冲突 → 422 result_validation_failed
             ├── 逐文件 os.replace → 中途崩溃 trade-off (§8.4)
             └── rmtree .tmp
  → ExecuteResponse {request_id, output_bucket, filenames(只名), written_file_count, total_uids, rows_per_uid, metadata}
```

## 10. 遗留项

- **DDL 执行**：永远 422，不做（Zero Tolerance 条款）。需要建表的场景由分析师在 StarRocks client 手跑。
- **partial write success / 跨多文件事务**：Design Doc §8.4 trade-off 显式接受；V3 可加 rsync-style 双目录切换 / journal-based。
- **SQL 结果 streaming / 分批**：大结果集场景留 V3；当前 `DA_MAX_RESULT_ROWS=100000` 兜底。
- **多分析师 / approval token 状态机**：等真正多人协作 + 有审批系统时再做（V3+）。
- **非 mexico 国家真实验证**：架构留位（manifest YAML 占位），需要分析师补 4 国知识库路径。
- **healthz DB 探活**：当前 stub 501，未扩展 DB ping。
- **StarRocks 真实 RBAC 自动化测试**：属部署 smoke checklist，不在自动化范围；文档已登记部署侧硬要求。
- **运行时 query timeout**：pymysql cursor 不直接支持，当前依赖 connect_timeout 兜底；V3 可换 driver 或加 watchdog。
- **V1 / V2 进程内串联**：设计上分析师手工接力，不在进程内串联；V2 不回查 V1，V1 不持久化。
- **子原因枚举对调用方暴露**：当前仅进内部 log；如未来要暴露须用预定义 enum 不带 payload。
