# data_acquisition_agent V1 + V2 白盒审计报告

- 审计基线（baseline commit）：`764a647 chore: sanitize demo0 credentials before git tracking`
- 审计范围终点：`HEAD`（branch `main`）
- 审计范围：`data_acquisition_agent/`、`app/main.py`、`app/core/config.py`、`requirements.txt`、`.env.example`
- 审计输出：仅本报告（`docs/reviews/data-acquisition-v1v2-audit.md`），不修改任何运行时代码
- 不在范围：本次前端变更（`app/static/`、`app/ui/build_frontend.py` 等不审计）
- 关键依据：`CLAUDE.md` 关键约束（SQL/凭据安全、artifact 安全）、`docs/specs/data_acquisition_agent.md`（V1 Design Doc）、`docs/specs/data_acquisition_agent_v2.md`（V2 Design Doc）

---

## 1. 变更概览

V1 在 baseline 之后引入了顶层独立的 `data_acquisition_agent/` 子项目，作为画像系统上游的「自然语言取数需求 → SQL/Python artifact」LLM Agent。V1 显式不连库、不执行 SQL、不落数据，仅生成可供分析师人工审核的字符串。V2 在同一子项目内扩展了「受控执行层」：分析师把审完的 SQL 通过新的 `POST /api/data-acquisition/execute` 端点提交，V2 走守门 → 短生命周期 StarRocks 连接 → COUNT 预检 → 执行 → bucket 切片 → 原子落 per-uid 文件，让画像 SkillRegistry 通过 `LocalUserRepository` 直接读到结果。

总计：`data_acquisition_agent/` 下新增 33 个文件、约 2424 行（其中运行时模块 11 个 / 1019 行，测试 15 个 / 1392 行）；外围：`app/main.py +24/-5`、`app/core/config.py +4`、`requirements.txt +2`（pyyaml、pymysql）、`.env.example +10`。

## 2. 文件清单

| 文件路径 | 行数 | 一句话职责 |
|---|---|---|
| [data_acquisition_agent/__init__.py](data_acquisition_agent/__init__.py) | 0 | package 标记 |
| [data_acquisition_agent/api.py](data_acquisition_agent/api.py) | 83 | FastAPI router；挂载 `/generate`、`/execute`、`/manifests`、`/healthz`，集中错误码→HTTP 状态映射 |
| [data_acquisition_agent/orchestrator.py](data_acquisition_agent/orchestrator.py) | 147 | V1 端到端编排：manifest → prompt 组装 → LLM → 输出策略守门 → Pydantic 响应组装 |
| [data_acquisition_agent/manifest.py](data_acquisition_agent/manifest.py) | 65 | YAML manifest 加载与校验，含 `analyst_private_prefix`、五个国家文件 |
| [data_acquisition_agent/prompt_assembler.py](data_acquisition_agent/prompt_assembler.py) | 84 | 把 5 份 md 经 redactor 后拼成 prompt + token 估算 + 800k 阈值守门 |
| [data_acquisition_agent/redactor.py](data_acquisition_agent/redactor.py) | 33 | L1 凭据脱敏（11 个正则 family） |
| [data_acquisition_agent/output_scanner.py](data_acquisition_agent/output_scanner.py) | 82 | L2 凭据扫描 + Python 危险代码黑名单 + SQL DDL 策略校验 |
| [data_acquisition_agent/schemas.py](data_acquisition_agent/schemas.py) | 161 | Pydantic 契约：GenerateRequest/Response、ExecuteRequest/Response、ErrorType 枚举（13 类） |
| [data_acquisition_agent/connection.py](data_acquisition_agent/connection.py) | 56 | V2 短生命周期 StarRocks（pymysql）连接；env-only 凭据；`_RedactedConnection.__repr__` 屏蔽 |
| [data_acquisition_agent/executor.py](data_acquisition_agent/executor.py) | 155 | V2 执行编排：守门 → 连接 → COUNT 预检 → 主查询 → 委托 output_writer |
| [data_acquisition_agent/output_writer.py](data_acquisition_agent/output_writer.py) | 153 | V2 bucket schema 校验 → 内存切片 → `.tmp_<rid>` + `os.replace` 原子落盘 |
| [data_acquisition_agent/configs/mexico.yaml](data_acquisition_agent/configs/mexico.yaml) | 9 | 墨西哥 manifest（唯一已填实路径），`analyst_private_prefix: dm_model.yyp_tmp_` |
| `configs/{indonesia,pakistan,thailand,philippines}.yaml` | 1 each | 占位符（架构留位） |
| `tests/test_redactor.py` 等 15 个测试文件 | 1392 | V1+V2 单元 / 集成 / smoke 测试 |

## 3. 技术路线

### V1 链路（manifest → redact → assemble → LLM → scan）
```
POST /api/data-acquisition/generate
  → DataAcquisitionOrchestrator.generate()
    → load_manifest(country)         # manifest.py：YAML 校验 + 路径存在
    → assemble_prompt()               # prompt_assembler.py：5 份 md → redact()（L1）→ system+knowledge+user 三段拼接 → estimate_tokens 800k 守门
    → ModelClient.generate_structured # app.core.model_client（复用 V1 唯一 LLM 通道）
    → _enforce_nl_sql_kind_consistency # NL 无建表意图却返回 build_table_script → 422
    → _enforce_output_policies        # L2：scan_credentials → scan_python_dangerous → check_sql_policy
    → _build_response                 # Pydantic 校验 + 缺字段补默认
  → GenerateResponse / ErrorResponse
```

### V2 链路（request → gate → precheck → execute → bucket → write）
```
POST /api/data-acquisition/execute
  → ExecuteRequest Pydantic 校验（含 app bucket → csv 强制）
  → run_execute_pipeline(request, request_id):
    1) load_manifest(target_country)               # 复用 V1 manifest 取 analyst_private_prefix
    2) enforce_pre_execution_gates                 # 守门：sql_kind≠build_table_script + V1 三层 scanner + 多语句 (";" split) 拦截
    3) open_starrocks_connection (env-only)        # 短生命周期 ctx mgr；失败 → DbUnreachableError
    4) precheck_row_count(包裹 SELECT COUNT(*) ... ) # 超 DA_MAX_RESULT_ROWS → result_too_large 413
    5) execute_query                                # 拿 DataFrame；空集 → result_validation_failed
    6) validate_bucket_schema                       # app bucket 强制 7 字段 + csv
    7) build_per_uid_payloads                       # groupby(uid) → list[(uid, bytes)]，behavior/credit json 包 schema_version="da_agent_v2" 外壳
    8) resolve_bucket_dir → mkdir
    9) write_per_uid_atomic                         # .tmp_<rid> → 全部写完 → 逐文件 os.replace → rmtree
   10) 组装 ExecuteResponse（filenames 仅文件名）
```

## 4. 安全审计

CLAUDE.md「关键约束（Zero Tolerance）」中与本子项目直接相关的安全约束（原文 5 条，逐条对照）：

> 1. SQL / 凭据安全：未经脱敏的凭据（host / port / user / password / database 明文，以及 token / key / secret）不得进入 prompt、生成代码、日志、API 响应或文档。所有知识库 md 注入 LLM 之前必须经过脱敏管线；LLM 输出必须经过凭据扫描。
> 2. data_acquisition_agent artifact 安全：V1 生成的 SQL / Python 仅为待审核 artifact，系统不得自动执行 SQL，不得运行生成的 Python，不得连接数据库，不得落数据。
> 3. `build_table_script` 类 SQL 必须限定分析师私有 schema / prefix，且必须人工审核后才能投入使用。
> 4. LLM 调用只通过 `ModelClient`（`app/core/model_client.py`），不直接 import google-genai。
> 5. 数据文件（`data/`）不允许加入 git 追踪。

### 4.1 L1 凭据脱敏（覆盖约束 1 入口侧）

[redactor.py:9-21](data_acquisition_agent/redactor.py#L9-L21) 定义 11 family 正则，由 [prompt_assembler.py:33](data_acquisition_agent/prompt_assembler.py#L33) 在每份 md 注入前调用：

| # | family | 正则要点 | 覆盖 CLAUDE.md 哪一项 |
|---|---|---|---|
| 1 | host | `\bhost\s*=\s*'IPv4'` | host 明文 |
| 2 | port | `\bport\s*=\s*\d{2,6}\b` | port 明文 |
| 3 | user | `\buser\s*=\s*'e_*'` | user 明文 |
| 4 | password | `\bpassword\s*=\s*'[^']*'` | password 明文 |
| 5 | database | `\bdatabase\s*=\s*'dm_*'` | database 明文 |
| 6-10 | token / api_key / access_token / secret / key | `... '[^']+'` | token / key / secret |
| 11 | bearer | `Authorization: Bearer ...`（大小写不敏感） | bearer token |

5 项 CLAUDE.md 凭据 family 全部覆盖。注意要点：
- `prompt_assembler.assemble_prompt` 把 redact 命中数累加到 `total_hits` 并写进响应 metadata 的 `redaction_events`；功能上配合 §4.5 banner 提示分析师。
- 已知风险：L1 正则要求**单引号**包裹（`host='...'`）。如果知识库未来改成双引号或 `=`+空格风格（`host = "1.2.3.4"`），L1 会漏匹配。L2 [output_scanner.py:9-21](data_acquisition_agent/output_scanner.py#L9-L21) 已经放宽到 `['"]` 双层支持，作为补救。

### 4.2 L2 输出回扫（覆盖约束 1 出口侧）

[output_scanner.py:9-21](data_acquisition_agent/output_scanner.py#L9-L21) `CRED_PATTERNS` 与 L1 family 一一对应但放宽 quoting；
[output_scanner.py:32-41](data_acquisition_agent/output_scanner.py#L32-L41) `DANGEROUS` 含 `os.system / subprocess shell=True / eval / exec / __import__('os') / shutil.rmtree / os.remove / urllib.request.urlretrieve` 共 8 项黑名单；
[orchestrator.py:77-97](data_acquisition_agent/orchestrator.py#L77-L97) `_enforce_output_policies` 把 `sql + "\n" + python` 一起送 cred scanner（V1 出口），命中即 `OrchestratorError(CREDENTIAL_LEAK)`。
V2 在 [executor.py:39-44](data_acquisition_agent/executor.py#L39-L44) 又对 `approved_sql` 重跑一次 `scan_credentials` + `scan_python_dangerous`，符合 v2 §9.3「不信任请求方提供的 SQL」原则。

### 4.3 SQL 注入与 DDL/DML 守门（覆盖约束 3）

`output_scanner.check_sql_policy` 是策略中心：
- [output_scanner.py:46-49](data_acquisition_agent/output_scanner.py#L46-L49) `query_only` 模式：先剥注释（`_strip_sql_comments` 处理 `/* */` 与 `--`），DDL 关键字 `(CREATE|DROP|ALTER|TRUNCATE|INSERT|UPDATE|DELETE)` 命中即 reject。
- [output_scanner.py:50-62](data_acquisition_agent/output_scanner.py#L50-L62) `build_table_script` 模式：必须命中 DDL；逐 statement 必须匹配白名单 `_ALLOWED_BUILD_STMT`（仅 `CREATE TABLE [IF NOT EXISTS] <ident> AS [WITH|SELECT] ...` 和 `DROP TABLE [IF EXISTS] <ident>`）；禁用反引号/双引号包裹 identifier；`<ident>` 必须以 `manifest.analyst_private_prefix` 开头（如墨西哥的 `dm_model.yyp_tmp_`）。

V2 [executor.py:36-54](data_acquisition_agent/executor.py#L36-L54) 在守门链中：
- `sql_kind == "build_table_script"` 一律 reject 为 `DDL_NOT_SUPPORTED_IN_V2`（呼应 v2 §G2 决策与 CLAUDE.md「不得自动执行 SQL」）。
- 复用 V1 三层 scanner 把 `query_only` 的 DDL/DML 关键字硬拒。
- 额外用 `_strip_sql_comments` 剥注释后按 `;` split 计数，多个非空 token → `DDL_POLICY_VIOLATION`，专门防 `SELECT 1; DROP TABLE x` 形态。

注意点：上述守门是**应用层正则**，不是真正的 SQL parser。v2 §6.3 把「StarRocks DB 账号 RBAC 仅授 SELECT」作为最强边界（部署侧硬约束）写进文档，应用层正则定位为补充而非替代——这是合理的纵深防御立场。

### 4.4 连接安全（覆盖约束 1 + 约束 2）

[connection.py](data_acquisition_agent/connection.py) 关键设计：
- 凭据**只在 `open_starrocks_connection` 函数体内通过 `os.environ` 读取**（[connection.py:36-45](data_acquisition_agent/connection.py#L36-L45)），完全不入 Settings、不进 module-level 全局，与 v2 §6.1 / T-2 张力解一致。
- [app/core/config.py +4](app/core/config.py) 仅引入 `da_max_result_rows`/`da_query_timeout_seconds`/`da_connection_profile` 三个**非敏感**配置，未触碰 `DA_DB_*`。
- `_RedactedConnection.__repr__ → "<RedactedStarRocksConnection>"`（[connection.py:24](data_acquisition_agent/connection.py#L24)）防止 driver 对象被 logger / traceback 反射出 host/user。
- pymysql.connect 失败时 [connection.py:49-50](data_acquisition_agent/connection.py#L49-L50) 用 `from None` 切断异常 chain → 不会在上层 traceback 中暴露 driver 自带的 `Exception.message`（host / database / user 明文）。
- `open_starrocks_connection` 是 `@contextmanager`，`finally` 关闭原始连接，`creds` 局部变量随栈回收。

满足 v2 §9.1「凭据全程零泄漏」与 CLAUDE.md「凭据不得进入日志/响应」。

### 4.5 错误消息（覆盖约束 1 出口）

- V1 `OrchestratorError` 与 V2 `ExecutorError` / `OutputWriterError` / `DbUnreachableError` 都使用**预定义短常量字符串**：`"DDL is not executable by V2"`、`"database connection failed"`、`"query execution failed"`、`"result validation failed"`、`"result exceeds row limit"`、`"output write failed"` 等（见 [executor.py:38-72](data_acquisition_agent/executor.py#L38-L72)、[connection.py:15](data_acquisition_agent/connection.py#L15)、[output_writer.py:50-58](data_acquisition_agent/output_writer.py#L50-L58)）。
- 没有 f-string / .format / 参数化拼接 SQL/host 进 message。
- [api.py:48-77](data_acquisition_agent/api.py#L48-L77) 错误响应仅返回 `ErrorResponse{error_type, message, request_id}`，**不回显** SQL / DB error / 表名 / 列名 / 路径 / DataFrame。
- 子原因（`bucket_schema_mismatch` / `output_file_conflict` / `result_empty` / `missing_uid_column`）在代码里映射成同一个 `RESULT_VALIDATION_FAILED`，与 v2 §9.7 设计一致。

### 4.6 artifact 与执行边界安全（覆盖约束 2 + 约束 3）

- V1 端 `_enforce_output_policies` 在响应组装前一次性跑 cred + python 黑名单 + SQL 策略；命中 raise，artifact 不进 response。
- V1 仍**完全不连库不执行**——orchestrator 没有 import pymysql / connection.py，只 import LLM。
- V2 端 `executor.py` 仅执行 query_only；`build_table_script` 第一道闸就 reject。`build_table_script` 类 SQL 在 V1 也仍只是 artifact，必须人工拷到 StarRocks client 跑——这与 CLAUDE.md「`build_table_script` 类 SQL 必须限定分析师私有 schema / prefix，且必须人工审核后才能投入使用」一致：私有 prefix 由 [output_scanner.check_sql_policy](data_acquisition_agent/output_scanner.py#L60) 在 V1 出口强制；V2 拒绝其执行；DB RBAC 由部署 smoke checklist 兜底。
- V2 `os.replace` 原子流程（[output_writer.py:103-142](data_acquisition_agent/output_writer.py#L103-L142)）防止画像 SkillRegistry 读到半写文件；跨多文件 crash-consistency trade-off 已在 v2 §8.4 显式接受。
- V2 写盘目标限定为 `settings.{app,behavior,credit}_by_uid_dir`（[output_writer.py:145-153](data_acquisition_agent/output_writer.py#L145-L153)），由 `bucket` 枚举值 → 属性名映射，不接受请求方传入路径，根本上排除 path traversal。
- 唯一的弱点：`uid` 来自 DataFrame 列，最终用作 `f"{uid}.{ext}"` 文件名（[output_writer.py:124](data_acquisition_agent/output_writer.py#L124)）。如果数据库返回的 uid 含有 `..` 或路径分隔符，理论上可写到 `bucket_dir` 之外的目录。**改进建议**：在 `build_per_uid_payloads` 增加对 uid 的字符白名单（`^[A-Za-z0-9_-]+$`）或 `Path(...).name` 规约，命中即 `result_validation_failed`。

### 4.7 约束 4（ModelClient 唯一通道）合规性

[orchestrator.py:10](data_acquisition_agent/orchestrator.py#L10) `from app.core.model_client import ModelClient`，全文件唯一 LLM 调用 [orchestrator.py:60-61](data_acquisition_agent/orchestrator.py#L60-L61)；未直接 import google-genai。✅

### 4.8 约束 5（data/ 不入 git）

V2 写盘到 `data/` 子目录，但 `.gitignore` 已经在 baseline 之前由 `22ebb01 security: remove tracked data/secrets, update .gitignore` 处理；本次审计范围内没有把任何 `data/` 文件加入追踪。✅

## 5. 正确性判断

### V1 链路自检
- happy path：`mexico` 请求 → manifest 命中 → 5 份 md 路径存在 → redact 后 token 估算 < 800k → ModelClient mock 返回 5 keys JSON → 三层 scanner 通过 → Pydantic 组装 → 200。闭环。
- 已知 follow-up：v2 §1.2 记录 real LLM 3-retry 0/3 successful（JSON parse 失败 / 缺 key），v1 prompt_assembler 末尾 `# === json_format_rules ===` 段（[prompt_assembler.py:60-78](data_acquisition_agent/prompt_assembler.py#L60-L78)）和 `_build_response` 的缺字段兜底（[orchestrator.py:113-130](data_acquisition_agent/orchestrator.py#L113-L130)）已经做了第一轮加固，TASK.md 列为待跟进。

### V2 链路自检
- happy path：`approved_sql=SELECT ... LIMIT 100` + `output_bucket=app` + `output_format=csv` → 守门通过 → env 凭据→pymysql→COUNT 预检（≤ 100000）→ 真查询→DataFrame→app 7 字段校验→groupby(uid)→.tmp_<rid> 写入→`os.replace` 落 `data/app/by_uid/{uid}.csv`→`shutil.rmtree(.tmp)`→200。闭环。
- 异常分流：DB 连不通 → 502 db_unreachable；多语句 / DDL 关键字 → 422 ddl_policy_violation；行数过大 → 413 result_too_large；空集 / schema 不匹配 → 422 result_validation_failed；写盘失败 → 500 output_write_failed + .tmp 回滚。与 v2 §7.4 表对应。

## 6. 风险排查 + 改进建议

| 严重度 | 风险 | 位置 | 改进建议 |
|---|---|---|---|
| 中 | uid 直接拼文件名，未验证字符 | [output_writer.py:124](data_acquisition_agent/output_writer.py#L124) | 在 build_per_uid_payloads 加 `^[A-Za-z0-9_-]+$` 白名单或 `Path(uid).name` 规约 |
| 中 | L1 redactor 仅匹配单引号包裹的凭据 | [redactor.py:10-19](data_acquisition_agent/redactor.py#L10-L19) | 同步放宽到 `['"]`（与 L2 对齐），避免上游知识库格式变更导致 L1 失效 |
| 低 | `pymysql.connect` 默认 `connect_timeout=10`；`DA_QUERY_TIMEOUT_SECONDS` 未应用到 cursor.execute | [executor.py:60-67](data_acquisition_agent/executor.py#L60-L67) | 在 `pymysql.connect` 传 `read_timeout=settings.da_query_timeout_seconds, connect_timeout=...`，并在 cursor 上设 `cur.execute("SET query_timeout = ...")` |
| 低 | `_RedactedConnection.__getattr__` 把所有属性透传给 `_raw`，包括 `_raw.__repr__()` 仍可被强制调用（如 `repr(conn._raw)`） | [connection.py:22-26](data_acquisition_agent/connection.py#L22-L26) | 受 v2 §9.1 文档约束本就要求"不在异常 chain 中带 creds"，目前用 `raise ... from None` 已覆盖；如需进一步 hardening 可拒绝部分 dunder |
| 低 | `pyyaml>=6.0` 用 `yaml.safe_load`，✅ 安全；但 `yaml.safe_load` 配合用户上传内容时仍需注意 | [manifest.py:36](data_acquisition_agent/manifest.py#L36) | 当前 manifest 仅来自仓库受控文件，无风险；保持现状 |
| 低 | `ddl_not_supported_in_v2` 和 `result_too_large` 未列入 v1 ErrorType StatusMap 影响范围之外 | [api.py:25-30](data_acquisition_agent/api.py#L25-L30) | 已在 _STATUS_MAP 含全 13 类，OK；新增 ErrorType 时务必同步更新此 map |
| 低 | manifest 占位文件（4 国 1 行 yaml）调用时抛 `ManifestNotImplemented`，由 [orchestrator.py:51](data_acquisition_agent/orchestrator.py#L51) 映射为 `BAD_REQUEST` ✅ | — | 保持现状 |
| 低 | V1 `redaction_events` 记入 metadata 暴露给调用方 | [orchestrator.py:140](data_acquisition_agent/orchestrator.py#L140) | 是计数（非内容），合规；继续保留 |
| 中 | `app.main:55-65` 末尾 `from data_acquisition_agent.api import router` 是 module 加载期 import，且未做异常包装；如果该 package 在某些部署中未安装会让 main 直接挂 | [app/main.py](app/main.py) | 将 import 移至文件顶部 + 加注释；或包 try/except 给出明确 error |
| 信息 | `_RedactedConnection` 没有 `__enter__`/`__exit__`；调用方一律走外层 `@contextmanager` 处理生命周期 | [connection.py:22-26](data_acquisition_agent/connection.py#L22-L26) | 设计意图明确，无需改 |

## 7. 运行时链路图

### V1（generate）
```
HTTP POST /api/data-acquisition/generate
  └─► app.main → include_router(data_acquisition_router)
       └─► api.generate(request: GenerateRequest)         [api.py:43]
            └─► _get_orchestrator() → DataAcquisitionOrchestrator
                 └─► .generate(request)                    [orchestrator.py:47]
                      ├─► load_manifest(country)           [manifest.py:57]
                      │     └─► CountryManifest.from_yaml  [manifest.py:34]
                      ├─► assemble_prompt(req, manifest)   [prompt_assembler.py:21]
                      │     ├─► redact(md text)            [redactor.py:24]   ×5 文件
                      │     └─► estimate_tokens → 800k     [prompt_assembler.py:13]
                      ├─► ModelClient.generate_structured  [app/core/model_client.py]
                      ├─► _enforce_nl_sql_kind_consistency [orchestrator.py:102]
                      ├─► _enforce_output_policies         [orchestrator.py:77]
                      │     ├─► scan_credentials           [output_scanner.py:24]
                      │     ├─► scan_python_dangerous      [output_scanner.py:28]
                      │     └─► check_sql_policy           [output_scanner.py:44]
                      └─► _build_response (Pydantic)       [orchestrator.py:113]
       └─► 200 JSON (GenerateResponse) | 4xx ErrorResponse
```

### V2（execute）
```
HTTP POST /api/data-acquisition/execute
  └─► api.execute(request: ExecuteRequest)                 [api.py:60]
       └─► run_execute_pipeline(request, request_id)        [executor.py:100]
            ├─► load_manifest(target_country)               [manifest.py:57]
            ├─► enforce_pre_execution_gates                 [executor.py:28]
            │     ├─► sql_kind == build_table_script → 422
            │     ├─► scan_credentials(approved_sql)
            │     ├─► scan_python_dangerous(approved_sql)
            │     ├─► check_sql_policy(query_only, prefix)
            │     └─► multi-statement guard (";" split)
            ├─► open_starrocks_connection(rid)              [connection.py:33]
            │     ├─► env-only os.environ[...]
            │     └─► pymysql.connect(...) wrapped in _RedactedConnection
            ├─► precheck_row_count(SELECT COUNT(*) ...)     [executor.py:57]
            │     └─► n > DA_MAX_RESULT_ROWS → 413
            ├─► execute_query → pd.DataFrame                [executor.py:76]
            ├─► validate_bucket_schema(app→7字段+csv)       [output_writer.py:40]
            ├─► build_per_uid_payloads (groupby uid)        [output_writer.py:62]
            ├─► resolve_bucket_dir(bucket)                  [output_writer.py:145]
            └─► write_per_uid_atomic                        [output_writer.py:103]
                  ├─► .tmp_<rid> mkdir
                  ├─► 写入全部 (uid, payload)
                  ├─► overwrite=False 检查冲突
                  ├─► os.replace × N（逐文件原子）
                  └─► shutil.rmtree(tmp)
       └─► 200 ExecuteResponse | 4xx/5xx ErrorResponse
            （filenames 仅文件名；不返回路径/SQL/DB error/DataFrame）
```

## 8. Debug 手册

### 场景 A：V1 调用返回 `prompt_too_large`
- 入口：[orchestrator.py:55-57](data_acquisition_agent/orchestrator.py#L55-L57) → 由 [prompt_assembler.py:82-83](data_acquisition_agent/prompt_assembler.py#L82-L83) 抛 ValueError 触发。
- 排查：(1) 检查目标国 manifest 5 份 md 总字节 vs `TOKEN_LIMIT=800_000`；(2) 中文权重为 1.5 → 中文知识库放大；(3) 临时调高 TOKEN_LIMIT 仅做诊断，不做修复——根因通常是知识库一次塞太多。

### 场景 B：V1 调用返回 `credential_leak`
- 入口：[orchestrator.py:81-84](data_acquisition_agent/orchestrator.py#L81-L84) → `scan_credentials(sql + "\n" + python)` 命中。
- 排查：(1) 在测试桩中 print payload['sql'] / payload['python'] 看 LLM 是否真的把 host=/password= 直接写出；(2) 若是 LLM 偶发幻觉，加强 prompt 显式要求 placeholder；(3) 若是 L1 漏脱敏（知识库新格式），更新 [redactor.py PATTERNS](data_acquisition_agent/redactor.py#L9)。

### 场景 C：V2 调用返回 `db_unreachable`（502）
- 入口：[connection.py:35-50](data_acquisition_agent/connection.py#L35-L50) 抛 `DbUnreachableError` 后 [api.py:68-72](data_acquisition_agent/api.py#L68-L72) 映射 502。
- 排查：(1) `os.environ` 是否含 `DA_DB_HOST/PORT/USER/PASSWORD/DATABASE` 全部 5 个；(2) 内网代理 / 跳板机端口转发是否打开；(3) StarRocks FE MySQL 协议端口是否对端可达；(4) 帐号是否被锁——所有原始 driver message 已被 `from None` 切断，需在 DB 端日志看具体原因。

### 场景 D：V2 调用返回 `ddl_policy_violation` 但 SQL 看起来是 SELECT
- 入口：[executor.py:46-54](data_acquisition_agent/executor.py#L46-L54)。
- 排查：(1) SQL 中是否含 `;` 和后续非空内容（多语句）；(2) `_strip_sql_comments` 是否未剥掉 `INSERT` 注释——其实它会剥；(3) SQL 中是否有 `WITH ... DELETE ...` 等被 DDL_KW 命中的关键字（V1/V2 共用大写不敏感关键字正则）。

### 场景 E：V2 写盘失败 → `output_write_failed`（500）
- 入口：[output_writer.py:117-140](data_acquisition_agent/output_writer.py#L117-L140)。
- 排查：(1) `.tmp_<rid>` 已存在 → request_id 重复（极小概率）；(2) bucket_dir 无写权限或磁盘满；(3) os.replace 跨文件系统 → 通常 bucket_dir 与 .tmp_<rid> 在同 fs，确认 settings 解析的 path；(4) 中途崩溃留下 `.tmp_*` → 可手工清理，下次请求会自动重写所有 uid。

---

**审计结论**：V1 + V2 在凭据脱敏（双层）、SQL 守门（DDL 二分 + 多语句 + 私有 prefix）、连接安全（env-only + 短生命周期 + repr 屏蔽 + chain 切断）、错误消息（固定常量、无回显）、artifact 边界（V1 不执行 / V2 仅 query_only / DB RBAC 兜底）五条主线上全面落实了 CLAUDE.md 的 5 条 Zero Tolerance 安全约束。主要剩余风险集中在 §6 表中（uid → 文件名缺白名单、L1 quote 风格、pymysql timeout 未传透）三点，建议分析师审核后纳入下一轮 hardening 计划。
