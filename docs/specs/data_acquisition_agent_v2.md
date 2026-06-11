# data_acquisition_agent V2 Design Doc

状态：Design Doc 已确认（2026-04-29），待 Step 3 架构设计。

---

## 2026-06-05 Local MySQL Sandbox Addendum

- 新增本地 Docker MySQL 8 沙盒验证模式，目标是打通 `generate -> execute -> write by_uid -> profile read` 的工程闭环，不追求生产 StarRocks / Hive SQL 还原。
- `DA_LOCAL_DEV=1` 不仅要影响 `load_manifest("mexico") -> mexico.local.yaml`，还必须影响知识库 `INDEX` 路由与 BM25 索引命名空间，确保 `/generate` 真正加载 `data_acquisition_agent/configs/local_dev/*.md`。
- 本地 `local_dev` schema 从历史 3 表升级为 4 表：
  - `app_install_list`
  - `behavior_events`
  - `credit_report_raw`
  - `app_label_dictionary`
- 本地 credit 不再走 `credit_report.report_json` 简化模型；本轮正式采用 `credit_report_raw` 原始字段，以便更稳定通过 `output_writer` 的 credit 强信号校验。
- 本地 `behavior` / `credit` execute 输出继续采用 raw `csv`，不在本轮引入 prepared JSON 兼容改造。

---

## Context

为什么做 V2：

V1（72 tests，2026-04-29 完成）把"自然语言取数需求 → SQL/Python artifact"落地为 FastAPI 服务，但**显式不连库、不执行、不落数据**。分析师拿到 V1 artifact 后仍要：手工审 SQL → 跳到 StarRocks client 执行 → 手工切片成 per-uid 文件 → 落到 `data/` → 喂给画像 SkillRegistry。这条体力链路是 V2 要解决的痛点。

V1 的另一条独立 follow-up（real LLM JSON 稳定性 0/3）已记录在 TASK.md，**不与 V2 混做**——V2 接受"V1 输出可能要分析师手改"作为常态，因此 V2 不绑定 V1 GenerateResponse 作为执行输入。

V2 是**受控执行层**：只接受人工审完的 approved_sql，连 StarRocks 的**只读账号**执行 query_only，把结果切片到 LocalUserRepository 期望的 per-uid 文件目录。DDL 不在 V2 执行——CLAUDE.md "data_acquisition_agent artifact 安全" Zero Tolerance 条款明令"不得自动执行 SQL"，DDL 仍由分析师在 StarRocks client 手跑。

预期成果：分析师调一次 `POST /api/data-acquisition/execute` 就能完成"执行 + 切片 + 落地"，画像 SkillRegistry 直接从 LocalUserRepository 读到数据。

---

## ⚠️ Tension Points（必须显式解决的张力）

### T-1：CLAUDE.md "不得自动执行 SQL" ↔ V2 执行查询
**解**：V2 仅执行 `query_only`（SELECT 类）+ DB 账号 RBAC 层只授 SELECT + 应用层三层守门(credential scan / python blacklist / sql_policy + multi-statement)。`build_table_script` 一律 422 拒绝。CLAUDE.md "受控执行" 的精神 = 只读窗口，DDL 写操作天然在边界外。

### T-2：V2 持有 DB 凭据 ↔ "凭据不得进 prompt / 代码 / 日志 / 响应"
**解**：DB 凭据只通过 `os.environ` 在执行那一刻读取，仅存在局部变量 / 短生命周期连接对象中；**不进 `app/core/config.py` Settings 字段、不进 model_dump、不进 repr、不进 module-level 全局**。Settings 仅持有非敏感 V2 配置（max_rows / timeout / connection_profile 名）。错误响应固定短文本，logger 严格白/黑名单。

### T-3：V2 落 per-uid 文件 ↔ LocalUserRepository prepared schema 耦合
**解**：V2 成为 prepared schema 的生产者；写入的 JSON 包 `{schema_version: "da_agent_v2", source_meta: {...}, uid, rows}` 外壳，让 LocalUserRepository 走 prepared json 路径。`schema_version` 字段做版本管理，未来 schema 演进可灰度。

### T-4：路径泄漏 ↔ 调用方需要知道写到哪
**解**：成功响应只返回 `output_bucket` + `filenames`（仅文件名，不含目录）+ `written_file_count` + `total_uids` + `rows_per_uid`。**不返回绝对路径、不返回文件内容、不返回 DataFrame 行**。调用方根据 bucket 自己组合目标目录。

### T-5：V1 LLM 输出不稳定 ↔ V2 需要可信输入
**解**：V2 不接受完整 V1 GenerateResponse 作为执行依据。分析师在审核环节自行修正 SQL，把审核后的 SQL 通过 `approved_sql` 字段提交给 V2。V2 不回查 V1，不依赖 V1 持久化。`source_request_id` 字段可空，仅作为审计关联用，不承担信任传递。

---

## 1. Background / Problem

### 1.1 V1 现状（2026-04-29 完成）

- 72 tests + 1 skipped；183 全量回归 0 failed
- 端点：`POST /api/data-acquisition/generate` 通过 `app/main.py include_router` 挂载
- 输入：自然语言需求 + 目标国家 + （可选）目标动作
- 输出：`{request_id, reasoning_summary, sql, sql_kind, python, audit_report, metadata}`
- 显式不做：连库、执行、落地、与画像 SkillRegistry 衔接
- 安全：L1 redactor 11 family + L2 output_scanner（cred / python blacklist / sql DDL 策略）+ analyst_private_prefix 校验

### 1.2 V1 已知 follow-up（与 V2 隔离）

- real LLM 3-retry 0/3 successful：JSON parse 失败 / Unterminated string / 缺 python 或 audit_report key
- 已记录在 TASK.md "待做" 段，**不与 V2 混做**
- V2 设计承认 V1 输出可能要手改，因此 V2 输入是"分析师审核后的 SQL"，不是 V1 GenerateResponse

### 1.3 痛点

V1 完成后，分析师仍需手工：
1. 审 SQL（V1 保留环节）
2. 跳到 StarRocks client 执行（V2 替代）
3. 切片成 per-uid 文件（V2 替代）
4. 落到 `data/` 对应目录（V2 替代）
5. 喂给画像 SkillRegistry（V2 不替代，由 LocalUserRepository 自动读）

V2 把第 2-4 步收编到一个受控端点。

---

## 2. Business Goal

### 2.1 面向用户

内部数据分析师 / 风控策略 / 增长 / 画像团队（与 V1 一致）。

### 2.2 V2 验收要点

- **G1** query_only end-to-end：mexico mock + StarRocks mock 全链路通，结果按 bucket 切片落到 LocalUserRepository 期望的目录
- **G2** build_table_script 一律 422 `ddl_not_supported_in_v2`，固定 message `"DDL is not executable by V2"`，不连库、不执行
- **G3** 凭据零泄漏：`DA_DB_PASSWORD` 等不进 Settings / model_dump / repr / log / response / error；T3 安全测试 assert 白名单 only
- **G4** schema 校验阻止脏数据进 LocalUserRepository（app bucket 7 字段强校验）
- **G5** all-or-nothing 落盘（接受单文件 `os.replace` 中途崩溃的 crash-consistency trade-off）
- **G6** 错误响应不回显 SQL / DB error / 表名 / 列名 / 路径 / DataFrame 内容

### 2.3 非目标

详见第 4 节 Out of Scope。

---

## 3. V2 Scope / Out of Scope

### 3.1 In Scope

| 项 | 内容 |
|---|---|
| 国家覆盖 | 代码层多国架构（沿用 V1 manifest），**仅 mexico 验证** |
| SQL 类型 | 仅 query_only |
| 交付形态 | FastAPI 路由，复用 `app/main.py` 实例（与 V1 同进程） |
| 输入 | JSON：approved_sql + sql_kind + target_country + approved_by + approval_note + source_request_id + output_bucket + output_format + uid_column + overwrite |
| 输出 | 结构化 JSON：`{request_id, output_bucket, output_format, filenames, written_file_count, total_uids, rows_per_uid, metadata}` |
| 凭据加载 | 执行时 `os.environ` 读取 `DA_DB_HOST / PORT / USER / PASSWORD / DATABASE`；**不入 Settings** |
| 非敏感配置 | `app/core/config.py` Settings 持有 `DA_MAX_RESULT_ROWS / DA_QUERY_TIMEOUT_SECONDS / DA_CONNECTION_PROFILE` |
| 守门 | sql_kind 守门 → V1 三层 scanner 复用 → multi-statement 拦截 |
| COUNT 预检 | 包裹单条 SELECT，超 `DA_MAX_RESULT_ROWS` → `result_too_large` |
| 落盘 | `<bucket_dir>/.tmp_<request_id>/` + `os.replace` |
| 错误码 | 6 类（含 V1 沿用的 credential_leak / dangerous_code / ddl_policy_violation） |
| Logger | 严格白/黑名单（§12.1） |
| 必做安全测试 | T1-T4（§12.2） |

### 3.2 Out of Scope（V2 不做，留 V3+）

- ❌ DDL 执行（build_table_script 一律拒）
- ❌ partial write success
- ❌ 跨多文件事务 / rsync-style 双目录切换 / journal
- ❌ SQL 结果 streaming / 大结果集分批
- ❌ 多分析师 / 双人复核 / approval token 状态机
- ❌ 非 mexico 国家的真实 StarRocks 验证（架构留位）
- ❌ 子原因枚举对调用方暴露（仅进内部 log）
- ❌ StarRocks 真实 RBAC 自动化测试（部署要求 / smoke checklist）
- ❌ healthz 扩展为 DB 探活
- ❌ V1 LLM JSON 稳定性修复（独立 follow-up）
- ❌ V1 → V2 进程内串联（设计上分析师手工接力）

---

## 4. System Position

### 4.1 V1 / V2 关系

```
分析师调 V1 /generate
  → 拿到 V1 GenerateResponse（含 sql / audit_report / request_id）
  → 人工审核 + 手改 SQL（与 V1 LLM 输出稳定性问题解耦）
  → 把 approved_sql + 审计 metadata + bucket 信息 POST 到 V2 /execute
  → V2 守门 → COUNT 预检 → 执行 → 切片 → 落 per-uid 文件
  → 画像 SkillRegistry 通过 LocalUserRepository 自动读到新数据
```

V1 / V2 通过**分析师手工接力**衔接，**不在进程内串联**。V2 不回查 V1，V1 不持久化。

### 4.2 代码层定位

V2 在 `data_acquisition_agent/` 内扩展（沿用 V1 顶层独立 package 的 CLAUDE.md 受控例外条款），不新建顶层 package。通过 `app/main.py include_router` 暴露新端点（与 V1 同 router 共用 `/api/data-acquisition` 前缀）。

```
CHORD/
├── app/
│   ├── main.py                               # 沿用 V1 include_router
│   ├── core/config.py                        # ⚠️ 仅扩展非敏感 V2 配置；不读 DA_DB_*
│   ├── repositories/local_repository.py      # V2 落地目标
│   └── ...
├── data_acquisition_agent/
│   ├── api.py                                # 扩展 /execute 端点
│   ├── schemas.py                            # 扩展 ExecuteRequest / ExecuteResponse
│   ├── output_scanner.py                     # ✅ V1 现有，V2 复用守门
│   ├── connection.py                         # ⭐ V2 新增：env var 凭据 + 短生命周期连接
│   ├── executor.py                           # ⭐ V2 新增：守门 + COUNT + 执行 + 切片编排
│   ├── output_writer.py                      # ⭐ V2 新增：bucket 切片 + .tmp + os.replace
│   └── tests/                                # V2 测试与 V1 测试集独立
└── docs/specs/data_acquisition_agent_v2.md   # 本 Design Doc
```

### 4.3 与 CLAUDE.md 关键约束的对齐

- "LLM 调用只通过 ModelClient" → V2 不调 LLM，不涉及
- "运行时代码只在 app/ 下" → 沿用 V1 受控例外（已登记 `data_acquisition_agent/`）
- "新 Skill 必须继承 BaseSkill 并在 SkillRegistry 注册" → V2 不是 Skill，不适用
- "data_acquisition_agent artifact 安全 — 不得自动执行 SQL" → V2 仅执行 query_only + DB RBAC 只读 + 三层守门 = 受控执行；DDL 仍人工
- "凭据不得进 prompt / 代码 / 日志 / API 响应 / 文档" → §7、§10、§12.1 系统化守护

---

## 5. Input/Output Contract

### 5.1 Request（POST /api/data-acquisition/execute）

```json
{
  "approved_sql": "SELECT uid, app_name, app_package, first_install_time, last_update_time, gp_category, ai_category_level_2_CN FROM ... WHERE channel='MEX017' LIMIT 100",
  "sql_kind": "query_only",
  "target_country": "mexico",
  "approved_by": "analyst_alias",
  "approval_note": "v1 request_id 1234-... 审核后限 100 行",
  "source_request_id": "1234-5678-...",
  "output_bucket": "app",
  "output_format": "csv",
  "uid_column": "uid",
  "overwrite": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| approved_sql | str | ✅ | 分析师审核后的 SQL |
| sql_kind | `"query_only" \| "build_table_script"` | ✅ | `build_table_script` 立刻 422 |
| target_country | TargetCountry enum | ✅ | 沿用 V1 枚举；用于加载 manifest 取 analyst_private_prefix |
| approved_by | str | ✅ | 审计 metadata，非安全凭证 |
| approval_note | str | 可选 | 审计 metadata；建议填 V1 request_id |
| source_request_id | str | 可选 | 关联 V1 request_id；V2 不回查 |
| output_bucket | `"app" \| "behavior" \| "credit"` | ✅（query_only） | 一次只写一个 |
| output_format | `"csv" \| "json"` | ✅（query_only） | app 强制 csv |
| uid_column | str | ✅（query_only） | 默认 `"uid"` |
| overwrite | bool | 可选，默认 true | false 时已存在 → result_validation_failed |

### 5.2 Response（200 OK）

```json
{
  "request_id": "uuid",
  "output_bucket": "app",
  "output_format": "csv",
  "filenames": ["uid1.csv", "uid2.csv", "..."],
  "written_file_count": 100,
  "total_uids": 100,
  "rows_per_uid": {"uid1": 5, "uid2": 3},
  "metadata": {
    "executed_at": "2026-04-29T...",
    "approved_by": "analyst_alias",
    "source_request_id": "1234-5678-...",
    "duration_ms": 1234,
    "row_count_total": 837
  }
}
```

**禁项**：
- 不返回绝对路径
- 不返回文件内容
- 不返回 DataFrame 行
- 不返回 SQL 文本回声
- 不返回 DB error message

### 5.3 错误响应表

复用 V1 `ErrorResponse` 形状 `{error_type, message, request_id}`。

V2 新增 6 类错误（与 V1 7 类共存，复用 ErrorType enum 扩展）：

| error_type | HTTP | 固定 message | 触发条件 |
|---|---|---|---|
| `ddl_not_supported_in_v2` | 422 | `"DDL is not executable by V2"` | sql_kind == "build_table_script" |
| `db_unreachable` | 502 | `"database connection failed"` | 连接 / 代理 / 凭据错 / 连接超时 |
| `query_failed` | 422 | `"query execution failed"` | SQL 执行失败 / 权限不足 / 表不存在 / 查询超时 / COUNT 预检失败 |
| `result_validation_failed` | 422 | `"result validation failed"` | uid_column 缺失 / app schema 不匹配 / result_empty / output_file_conflict |
| `result_too_large` | 413 | `"result exceeds row limit"` | COUNT > DA_MAX_RESULT_ROWS |
| `output_write_failed` | 500 | `"output write failed"` | 落盘失败（已触发 .tmp 回滚） |

V1 沿用错误（V2 守门复用 V1 scanner 时透传）：
- `credential_leak` 422
- `dangerous_code` 422
- `ddl_policy_violation` 422（query_only 含 DDL/DML 关键字）

---

## 6. Connection Layer

### 6.1 凭据加载策略

**核心原则**：凭据只在执行那一刻进程内可见。

```
Settings（app/core/config.py）
  ✅ 持有：DA_MAX_RESULT_ROWS（默认 100000）
            DA_QUERY_TIMEOUT_SECONDS（默认 60）
            DA_CONNECTION_PROFILE（profile 名，纯字符串）
  ❌ 不持有：DA_DB_HOST / PORT / USER / PASSWORD / DATABASE

Connection Layer（data_acquisition_agent/connection.py）
  执行触发时：
    creds = {
      "host": os.environ["DA_DB_HOST"],
      "port": int(os.environ["DA_DB_PORT"]),
      "user": os.environ["DA_DB_USER"],
      "password": os.environ["DA_DB_PASSWORD"],
      "database": os.environ["DA_DB_DATABASE"],
    }
    conn = open_connection(**creds)
    try:
        yield conn   # 短生命周期 context manager
    finally:
        conn.close()
        # creds 局部变量随函数返回出栈
```

**禁项**：
- 不把 creds 存到 module-level 全局
- 不把 creds 作为 Settings 字段或 dotenv 自动 binding
- 不在 connection 对象上保留 `__repr__` 暴露的明文（必要时覆写 `__repr__` 返回固定占位符）
- 不在异常 chain 中带 creds（封装 driver exception 为 V2 自己的 `DbUnreachableError`）

### 6.2 内网代理 / 连接形态

V2 通过现有内网代理连 StarRocks（不直连公网）。代理形态（SSH tunnel / 跳板机端口转发）由部署侧决定，V2 应用层只看到一个本地端口。

**占位**：具体 driver 选型（pymysql / sqlalchemy / starrocks-python-client）+ 代理形态在 Step 3 架构设计阶段确认。

### 6.3 DB 账号 RBAC（部署侧硬约束）

部署 StarRocks 账号必须满足：
- ✅ 授 SELECT
- ❌ 不授 CREATE / DROP / ALTER / TRUNCATE / INSERT / UPDATE / DELETE
- ❌ 不授 GRANT / 用户管理类权限

这是 V2 安全的**最强边界**——即便 V2 应用层守门被绕过，DB 仍拒绝写。**应用层正则 < DB RBAC**。

**自动化测试不验证真实 RBAC**（属部署 smoke checklist），但 V2 文档与部署手册必须显式登记此要求。

### 6.4 连接失败映射

| Driver 异常类型示例 | V2 映射 |
|---|---|
| connection refused / timeout | `db_unreachable` 502 |
| auth failed / access denied | `db_unreachable` 502（不暴露"密码错"——攻击者不应能区分凭据有效性） |
| socket / network error | `db_unreachable` 502 |

logger 仅记 `exception_class_name`，不记 driver `Exception.message`（可能含 host / database / user 明文）。

---

## 7. Execution Layer

### 7.1 执行前守门(顺序，任一失败立刻拒)

```
Step 1: sql_kind 守门
  if sql_kind == "build_table_script":
      raise OrchestratorError(ddl_not_supported_in_v2, "DDL is not executable by V2", rid)

Step 2: V1 三层 scanner 复用
  scan_credentials(approved_sql)        → credential_leak 422
  scan_python_dangerous(...)            → dangerous_code 422（V2 不接 python，但保留为 defensive）
  check_sql_policy(approved_sql,
                   "query_only",
                   manifest.analyst_private_prefix)
                                        → ddl_policy_violation 422

Step 3: 多语句拦截
  - 复用 output_scanner._strip_sql_comments 剥注释后
  - 按 ";" split，过滤空 token，非空 token > 1 → ddl_policy_violation 422
  - 防止 "SELECT 1; DROP TABLE x" 形态
```

### 7.2 COUNT(*) 预检

**前提**：仅对已通过 §7.1 守门的单条 SELECT 执行。

```
sql_stripped = approved_sql.rstrip().rstrip(";").rstrip()
count_sql = f"SELECT COUNT(*) FROM ({sql_stripped}) AS da_v2_count"

执行 count_sql：
  - timeout 同 DA_QUERY_TIMEOUT_SECONDS
  - 任何失败（语法 / 权限 / 超时 / DB error）→ query_failed 422
  - 不暴露子原因
  - logger 仅记 exception_class_name + stage="count_precheck"

if count > DA_MAX_RESULT_ROWS:
    raise result_too_large 413
```

### 7.3 真正执行

```
执行 approved_sql：
  - timeout = DA_QUERY_TIMEOUT_SECONDS（默认 60）
  - 失败 → query_failed 422
  - logger 仅记 exception_class_name + stage="query_execute" + duration_ms

返回 pandas DataFrame（或等价行集）
```

### 7.4 失败分流

| 阶段 | 失败 | 错误类型 |
|---|---|---|
| 连接 | 任意 driver 异常 | `db_unreachable` |
| §7.1 守门 | 命中规则 | 各自 V1 ErrorType 或 `ddl_not_supported_in_v2` |
| §7.2 COUNT | 任意失败 | `query_failed` |
| §7.2 COUNT 行数超阈值 | — | `result_too_large` |
| §7.3 主查询 | 任意失败 | `query_failed` |
| §7.3 结果集为空 | 行数 = 0 | `result_validation_failed` |
| §8 切片 | uid_column 缺失 / app schema 不匹配 / overwrite 冲突 | `result_validation_failed` |
| §8 落盘 | 写 / rename 失败 | `output_write_failed`（先 rmtree .tmp） |

---

## 8. Output Layer

### 8.1 Bucket 切片规则

#### app bucket
- `output_format` 强制 `csv`（请求 json 时 → `result_validation_failed`）
- 必填 7 字段 schema 校验（与 LocalUserRepository._resolve_app_uid_file 对齐）：
  `uid, app_name, app_package, first_install_time, last_update_time, gp_category, ai_category_level_2_CN`
- 缺字段 → `result_validation_failed`（子原因 `bucket_schema_mismatch` 仅进 log）
- 多行 = 该 uid 多个 app
- 编码 utf-8-sig（与 LocalUserRepository CSV 读取一致）

#### behavior / credit bucket
- 推荐 `output_format: json`（prepared 路径，被 LocalUserRepository 优先识别）
- 兼容 `output_format: csv`（raw 路径，LocalUserRepository fallback）
- json 强制包外壳：

```json
{
  "schema_version": "da_agent_v2",
  "source_meta": {
    "executed_at": "<iso>",
    "approved_by": "<from request>",
    "source_request_id": "<from request, 可空>",
    "row_count": "<int>"
  },
  "uid": "<uid>",
  "rows": ["<dataframe rows for this uid>"]
}
```

- json 编码 utf-8
- csv 编码 utf-8-sig

### 8.2 Per-uid 文件命名

- `{uid}.csv` 或 `{uid}.json`（与 LocalUserRepository 期望对齐）
- 路径：`settings.<bucket>_by_uid_dir / {uid}.<ext>`
- response 仅返回 `filenames=[uid1.csv, ...]`（仅文件名，不含目录）

### 8.3 Atomic Rename 流程

```
Step 1: 内存 build
  - groupby(uid_column) → list[(uid, payload)]
  - 全部 schema 校验 + json 包装在内存里完成
  - build 阶段任一失败 → result_validation_failed（未触磁盘）

Step 2: 临时目录
  tmp_dir = bucket_dir / f".tmp_{request_id}"
  os.makedirs(tmp_dir, exist_ok=False)

Step 3: 写到临时目录
  for uid, payload in items:
      tmp_path = tmp_dir / f"{uid}.{ext}"
      write_atomic(tmp_path, payload)
  任一失败 → shutil.rmtree(tmp_dir) → output_write_failed 500

Step 4: 逐文件 os.replace 到 bucket_dir
  for uid, payload in items:
      target = bucket_dir / f"{uid}.{ext}"
      if not overwrite and target.exists():
          raise result_validation_failed  # 子原因 output_file_conflict（仅 log）
      os.replace(tmp_dir / f"{uid}.{ext}", target)

Step 5: 清理 .tmp
  shutil.rmtree(tmp_dir, ignore_errors=True)
```

### 8.4 Crash-Consistency Trade-off（明确接受）

`os.replace` 在同一 fs 内是 POSIX/Windows atomic（单文件层面）。但**逐文件 replace 中途进程崩溃时，bucket_dir 可能出现"部分新部分旧"的混合状态**。

**V2 明确接受此 trade-off**：
- 真正的跨多文件事务（rsync-style 双目录切换 / journal-based）→ Future Optional
- V2 文档化此边界，调用方需要知道：进程崩溃后画像 Skill 可能读到不一致快照
- 缓解：V2 进程崩溃后分析师可重跑同一 request → 二次写入将所有 uid 文件刷到最新

### 8.5 Overwrite 策略

| overwrite | target 已存在 | 行为 |
|---|---|---|
| true（默认） | — | 直接 `os.replace` 覆盖 |
| false | 否 | 写入 |
| false | 是 | `result_validation_failed`（子原因 `output_file_conflict` 仅 log） |

---

## 9. Safety

### 9.1 凭据全程零泄漏

- DB 凭据不入 Settings / model_dump / repr / log / response / error
- env → 短生命周期连接对象 → 用完即丢
- connection 对象覆写 `__repr__`（如 driver 提供）返回固定占位符
- driver 异常封装为 V2 自己的异常类型，不向上层透传 chain

### 9.2 错误响应固定短文本

- 6 类 V2 错误码 + 3 类 V1 沿用（credential_leak / dangerous_code / ddl_policy_violation）
- 所有 message 是预定义常量字符串，不参数化、不 f-string、不 format
- 与 V1 commit 5183809 同原则

### 9.3 V1 守门在 V2 重新跑

- V2 不信任请求方提供的 SQL（即便 source_request_id 关联 V1）
- §7.1 三层 scanner 强制重跑

### 9.4 DB RBAC 硬约束

- §6.3 部署侧要求；应用层正则是补充而非替代

### 9.5 atomic rename 防止画像 Skill 读到半写文件

- §8.3 .tmp 目录隔离写入过程
- 单文件层面 atomic
- 跨多文件 trade-off 见 §8.4

### 9.6 Response 不暴露敏感信息

- 不返回绝对路径、文件内容、DataFrame 行、SQL 回声、DB error
- §5.2 禁项

### 9.7 子原因不进 response

- `missing_uid_column / bucket_schema_mismatch / result_empty / output_file_conflict` 仅进内部 structured log
- 进 log 时也不含实际列名 / 表名 / 数据
- 如未来要暴露给调用方 → 必须是预定义枚举值，不带 payload（Future Optional）

---

## 10. API Surface

| 端点 | 状态 | V2 行为 |
|---|---|---|
| `POST /api/data-acquisition/execute` | ⭐ 新增 | V2 主端点 |
| `POST /api/data-acquisition/generate` | ✅ V1 现有 | 不动 |
| `GET  /api/data-acquisition/manifests` | ✅ V1 stub | 不动 |
| `GET  /api/data-acquisition/healthz` | ✅ V1 stub | 不动；DB 探活 → Future Optional |

挂载方式：沿用 V1 在 `app/main.py` 的 `include_router`；新端点加在同一 router 上，前缀 `/api/data-acquisition`。

---

## 11. Logging / Testing Strategy

### 11.1 安全 Logger 规范

#### 白名单（仅这些字段允许进 logger）

- `request_id`
- `error_type`
- `exception_class_name`（type(e).__name__）
- `stage`（connect / count_precheck / query_execute / build_payload / write_tmp / replace / cleanup）
- `duration_ms`
- `row_count_total`
- `output_bucket`
- `output_format`

#### 黑名单（绝不进 log / response / error）

- `Exception.message`（driver 抛的原始异常 message）
- SQL 文本（approved_sql / count 包裹后的 SQL）
- DB host / database / username / password / port
- 表名 / 列名（包括 `uid_column` 实际值）
- DataFrame 内容 / 行 / 单元格
- 文件内容
- 绝对本地路径
- approved_by / approval_note 实际值（这些是审计 metadata，要进**审计** log，不进运行时 log；分离 logger）

#### 日志事件清单（示例）

```
exec_started  (request_id, output_bucket, output_format)
stage_done    (request_id, stage, duration_ms)
exec_failed   (request_id, error_type, exception_class_name, stage)
exec_succeeded(request_id, output_bucket, written_file_count, row_count_total, duration_ms)
```

### 11.2 测试矩阵

#### 必做自动化（V2 In Scope）

| ID | 测试 | 目的 |
|---|---|---|
| **T1** | build_table_script 被拒 | sql_kind="build_table_script" → 422 + error_type=="ddl_not_supported_in_v2" + message=="DDL is not executable by V2"；不连库（mock connection 验证未调用） |
| **T2** | query_only 含 DDL/DML 被拒 | 参数化 6 类 DDL/DML 关键字（CREATE / DROP / ALTER / TRUNCATE / INSERT / UPDATE / DELETE）→ ddl_policy_violation 422 |
| **T3** | connection layer 不 log secret | mock env 注入合成假凭据 → 触发 db_unreachable → assert logger 输出仅含白名单字段 + assert 假凭据值不在任何 log record / response body / exception traceback 中 |
| **T4** | error response 不泄漏 payload | 参数化 6 类 V2 error → assert response.message 是固定常量、不含 SQL / 表名 / 列名 / 路径 / Exception message |

#### V2 单元测试

- `test_executor.py`：守门顺序 / multi-statement 拦截 / COUNT 预检包裹正确
- `test_connection.py`：env var 加载 + 短生命周期 + repr 不暴露密码
- `test_output_writer.py`：bucket 切片 / app schema 校验 / .tmp 创建 / os.replace / 失败回滚 / overwrite 策略 / output_file_conflict
- `test_schemas.py` 扩展：ExecuteRequest / ExecuteResponse Pydantic 边界
- `test_api.py` 扩展：6 类 ErrorType → HTTP 状态码映射

#### V2 集成测试

- `test_e2e_mock_executor.py`：mock StarRocks connection + mock DataFrame → mexico app bucket 端到端 happy path
- mexico real LLM smoke：optional，不在本轮必做

#### 部署 smoke checklist（不在本轮自动化）

- StarRocks 真实账号 RBAC 验证（账号确实只能 SELECT，DDL/DML 被 DB 层拒）
- 内网代理连接通

#### 与 V1 测试集独立

- V2 测试文件在 `data_acquisition_agent/tests/test_*_v2.py` 或子目录
- 跑 V1 测试集（72 + 1 skipped）保证 0 回归

---

## 12. Open Decisions / Future Optional

| 项 | 备注 |
|---|---|
| 独立 DDL 端点（方案 B 完整形态：双账号 + token + 双人复核） | 等真正多人协作 + 有审批系统时再做 |
| 多分析师 / approval token 状态机 | 同上 |
| 非 mexico 国家真实验证（印尼 / 巴铁 / 泰国 / 菲律宾） | 等 V1 manifest 真实路径填充后 |
| healthz 扩展为 DB 探活 | 加深部署可观测性 |
| SQL 结果 streaming / 分批写 | 大结果集场景 |
| 跨多文件事务 / rsync-style 双目录切换 | 真正解决 §8.4 crash-consistency trade-off |
| 子原因枚举对调用方暴露 | 必须预定义 enum，不带敏感 payload |
| V1 → V2 审计链强化 | V2 主动持有 source_request_id 索引；要求 V1 持久化（违反当前 V1 不动约束） |
| StarRocks query 性能 / cache 策略 | 性能优化阶段 |
| connection_profile 多 profile 支持 | 当前单一全局；未来可按用户 / 环境分 profile |

---

## 13. Critical Files

### V2 In Scope 涉及

- `data_acquisition_agent/api.py` — 扩展 `/execute` 端点（V1 现有）
- `data_acquisition_agent/schemas.py` — 扩展 ExecuteRequest / ExecuteResponse / 6 类新 ErrorType（V1 现有）
- `data_acquisition_agent/output_scanner.py` — V2 复用守门（V1 现有，**不修改**）
- `data_acquisition_agent/manifest.py` — V2 读取 analyst_private_prefix（V1 现有，**不修改**）
- `data_acquisition_agent/connection.py` — ⭐ 新增（候选名）
- `data_acquisition_agent/executor.py` — ⭐ 新增（候选名）
- `data_acquisition_agent/output_writer.py` — ⭐ 新增（候选名）
- `app/core/config.py` — 仅扩展非敏感 V2 配置（max_rows / timeout / connection_profile）；**不读 DA_DB_***
- `app/main.py` — 不变（V1 已 include_router）
- `app/repositories/local_repository.py` — V2 写入目标，**不修改**
- `data_acquisition_agent/tests/` — 新增 V2 测试（T1-T4 + 单元 + 集成）

### 部署 / 环境

- `.env` — 新增 `DA_DB_*` + `DA_MAX_RESULT_ROWS` + `DA_QUERY_TIMEOUT_SECONDS` + `DA_CONNECTION_PROFILE`
- `.env.example` — 仅新增占位符
- `requirements.txt` — 新增 StarRocks driver（具体选型 Step 3 确认）
- StarRocks 部署侧 — 新建只读账号 + RBAC 验证（smoke checklist）

---

## 14. Verification

### 14.1 本地端到端验证（Step 5 实现完成后）

1. 启动服务：`uvicorn app.main:app --reload`
2. 准备 mock StarRocks（pytest fixture 或 docker test container）
3. 调 `POST /api/data-acquisition/execute`：
   ```
   {
     "approved_sql": "SELECT uid, app_name, ... LIMIT 10",
     "sql_kind": "query_only",
     "target_country": "mexico",
     "approved_by": "test",
     "output_bucket": "app",
     "output_format": "csv",
     "uid_column": "uid"
   }
   ```
4. 断 response 200 + filenames 存在 + 不含绝对路径
5. 检查 `<app_by_uid_dir>/` 下确有 per-uid CSV
6. 调 `POST /api/analyze` 用刚写入的 uid → 验证画像 SkillRegistry 读到 V2 落地数据

### 14.2 安全验证

1. T1-T4 自动化测试全过
2. 跑 `python -m pytest data_acquisition_agent/tests/ -v` → V1 72 + V2 全部 pass
3. 跑 `python -m pytest tests/ -v` → 现有画像测试 0 回归

### 14.3 部署 smoke checklist

1. StarRocks 账号尝试 `CREATE TABLE` → 应被 DB 拒
2. 调 V2 `/execute` 含 `sql_kind="build_table_script"` → 422 ddl_not_supported_in_v2
3. 调 V2 `/execute` 含 `sql_kind="query_only", approved_sql="DROP TABLE x"` → 422 ddl_policy_violation
4. 调 V2 `/execute` 故意打错 DA_DB_PASSWORD → 502 db_unreachable + log 不含密码

---

## 15. 五点检查法自检

1. **Context 段说清为什么做？** ✅ §Context + §1 阐明 V1 完成后的体力链路痛点
2. **Tension Points 显式？** ✅ §Tension Points 列出 5 条张力 + 解
3. **Scope 边界清晰？** ✅ §3 In/Out + §12 Future Optional
4. **关键文件路径标注？** ✅ §13
5. **Verification 可执行？** ✅ §14 含本地 + 安全 + 部署 smoke

---

## 后续步骤（不在本 Design Doc Scope）

- Step 3：架构设计（确认 driver 选型、connection.py / executor.py / output_writer.py 接口签名、与 V1 schemas.py 复用边界）
- Step 4：实现 Plan（TDD 拆 phase / task，2-5 分钟一个 task，参考 V1 `docs/plans/data-acquisition-v1-plan.md` 风格）
- Step 5：TDD 实现
- Step 6-8：基线 commit / Review / 白盒审计
