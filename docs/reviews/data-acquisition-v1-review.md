# data_acquisition_agent V1 — 白盒审计报告

> 审计基线：`e686404` → HEAD `c8793e3`
> 关联 Design：[docs/specs/data_acquisition_agent.md](../specs/data_acquisition_agent.md)
> 关联 Plan：[docs/plans/data-acquisition-v1-plan.md](../plans/data-acquisition-v1-plan.md)
> 审计日期：2026-04-30

---

## 1. 概述

V1 把 demo0 描述的"资深数据架构师"角色落地为一个 FastAPI Agent：分析师用自然语言描述取数需求 → Agent 输出"待审核的"SQL/Python artifact + 三阶段自检报告。**显式不连库、不执行、不落数据**，所有输出都是字符串。墨西哥 mob1 流失客群作为 V1 验证国家。设计核心是双层凭据脱敏（L1 加载 / L2 输出）、SQL DDL 二分策略（query_only vs build_table_script）、Python 危险代码黑名单。

产出：72 tests + 1 skipped，0 failed；FastAPI router 通过 `app/main.py include_router` 挂入主进程；7 类错误码 → HTTP 状态码完整映射。

## 2. 技术路线

- **顶层独立 package**（CLAUDE.md 受控例外）：`data_acquisition_agent/` 与 `app/runtime_skills/` 解耦，不进 SkillRegistry，仅复用 `app.core.model_client.ModelClient` / `app.core.logger` / `app.core.config`。
- **manifest 驱动多国架构**：每国一份 YAML（`mexico.yaml` 含 5 个 md 路径 + `analyst_private_prefix` + `sql_dialect`），placeholder country（`indonesia.yaml` 等）通过 `<PLACEHOLDER` 字符串触发 `ManifestNotImplemented` → 400 `bad_request`。
- **双层凭据防御（L1/L2 同源）**：L1 redactor 11 family（host/port/user/password/database/token/api_key/access_token/secret/key/bearer），加载 md 时立刻替换；L2 output_scanner 同 family（更宽松：单/双引号都扫），LLM 返回后回扫；命中即 422 `credential_leak`。两侧不抽 shared registry 是刻意决策，避免 V1 重构。
- **SQL DDL 二分**：`query_only`（默认，禁 DDL/DML）/ `build_table_script`（需 `analyst_private_prefix` 命中 + `audit_report.high_risk_ddl=true`），Pydantic model_validator 做联动校验，output_scanner.check_sql_policy 做 strip 注释 + statement split 后的 allowlist 匹配。
- **Token 估算**：CJK ×1.5 + 其它 /4 启发式，800K 阈值；超限 → 400 `prompt_too_large`，不进 LLM。
- **Orchestrator 错误分流**：`json_parse / json_repair_failed / schema_validation_failed` → 422；其他 model_error → 502 `upstream_llm_error`。

## 3. 变更文件清单

来源：`git diff e686404..c8793e3 --stat`，755 insertions / 94 deletions / 18 files。

| 类型 | 文件 | 行数 | 说明 |
|---|---|---|---|
| Modify | [app/main.py](../../app/main.py) | +3 | `include_router(data_acquisition_router)` |
| Modify | [requirements.txt](../../requirements.txt) | +1 | 新增 `pyyaml >=6.0,<7.0` |
| Modify | [data_acquisition_agent/configs/mexico.yaml](../../data_acquisition_agent/configs/mexico.yaml) | +6 / -6 | 6 个 placeholder → 真实知识库相对路径 + analyst_private_prefix |
| Modify | [data_acquisition_agent/schemas.py](../../data_acquisition_agent/schemas.py) | +20 | 2 个 model_validator：sql/python 至少一非空 + sql_kind ↔ high_risk_ddl 联动 |
| Modify | [data_acquisition_agent/manifest.py](../../data_acquisition_agent/manifest.py) | +48 | `CountryManifest.from_yaml` + `load_manifest` + `ManifestNotImplemented` + placeholder 字段检测 |
| Modify | [data_acquisition_agent/redactor.py](../../data_acquisition_agent/redactor.py) | +35 | L1 11 family 正则 |
| Modify | [data_acquisition_agent/output_scanner.py](../../data_acquisition_agent/output_scanner.py) | +79 | L2 凭据扫描 + Python 黑名单 8 条 + DDL 策略（含 quoted identifier 保守 reject） |
| Modify | [data_acquisition_agent/prompt_assembler.py](../../data_acquisition_agent/prompt_assembler.py) | +49 | CJK 加权 token 估算 + assemble_prompt + 800K 阈值护栏 |
| Modify | [data_acquisition_agent/orchestrator.py](../../data_acquisition_agent/orchestrator.py) | +110 | 骨架 + request_id + 输出策略分流 + schema fallback |
| Modify | [data_acquisition_agent/api.py](../../data_acquisition_agent/api.py) | +32 | router 接 orchestrator + 7 类 ErrorType → HTTP 映射 |
| Create/Modify | `data_acquisition_agent/tests/*.py` | +406 | 8 个测试文件，72 tests + 1 skipped |

## 4. 正确性判断

- **TDD 严格**：每个 Task 5 步流程（写失败测试 → 跑确认 FAIL → 实现 → 跑确认 PASS → commit），17 个 commit 串成 [baseline]→[complete] 链路。
- **错误契约全覆盖**：Design Doc §5 七类 ErrorType（bad_request / prompt_too_large / schema_validation_failed / credential_leak / dangerous_code / ddl_policy_violation / upstream_llm_error）均有对应测试 case 与 HTTP 状态码 parametrize 校验（`test_api.py`）。
- **manifest 健壮性**：3 个 manifest 测试覆盖 mexico happy path / 未知国家 FileNotFoundError / placeholder country `ManifestNotImplemented`。
- **schema 联动**：5 个 schema 测试覆盖 sql/python 至少一非空 + 3 个 sql_kind ↔ high_risk_ddl 矩阵 + ErrorResponse round-trip。
- **L1/L2 同源 anti-drift**：双侧 11 family 各自 compile 正则，redactor 15 case + scanner 4 case 显式覆盖每个 family 的命中。
- **零回归**：72 + 1 skipped 全套通过；既有画像测试 0 影响（V1 是新顶层 package，`app/main.py` 只追加 2 行 include_router）。

## 5. 安全扫描

- **L1 加载层脱敏**：5 份 md 注入 prompt 前必经 redact()；测试覆盖 11 类 family + 4 个边界（SQL 业务字段 e_id 不误伤 / `report=3306` 不误判 port / `user_uuid` 不误判 user / 英文文档"password"词不误报）。
- **L2 输出扫描**：LLM 输出的 `python` 字段 + SQL 字段拼接后扫；命中 11 类 family 任一 → 422，不返 artifact。
- **Python 黑名单 8 条**：`os.system / subprocess(...shell=True) / eval / exec / __import__('os') / shutil.rmtree / os.remove / urllib.request.urlretrieve`。
- **SQL DDL 策略**：query_only 禁 DDL/DML 关键字（注释先 strip）；build_table_script allowlist 仅 `CREATE TABLE [IF NOT EXISTS] X AS SELECT` / `DROP TABLE [IF EXISTS] X`，X 必须命中 `analyst_private_prefix`，反引号或双引号 quoted identifier 一律保守 reject。
- **demo0 入 git 前置脱敏**：mini-task `764a647` 已落地（不是本审计区间，但是 V1 实现的安全前提）。
- **日志规则**：仅记 path / size / sha256 / hits / token_estimate / latency / error_type，绝不打知识库正文（即使脱敏后也不打）。
- **凭据响应面**：响应体不含 SQL prompt 回声、不含 LLM raw payload、不含原始 driver exception；ErrorResponse 字段固定 `{error_type, message, request_id}`，message 是 OrchestratorError 短文本（V1 后期由 commit `5183809` 统一改为固定安全短消息，不在本审计区间）。
- **OWASP 合规**：A03 注入（SQL 不执行；Python artifact 黑名单）/ A04 设计缺陷（双层防御 + DB RBAC 由部署侧承担）/ A09 日志（白名单字段）。

## 6. 性能考量

- **Prompt 体积**：墨西哥 5 份 md ~170KB，CJK 加权 token 估算约 ~70-100K（远低于 800K 阈值）。
- **Cache 友好**：system_prompt + 4 知识库为静态前缀，理想 prompt cache 命中区；LLM 端开启 cache 后摊销复用率高。但功能正确性不依赖 cache（cache miss 时仍能跑）。
- **Orchestrator 同步阻塞**：单请求一次 LLM 调用（可能 retry 一次），mexico 全链路约 ~10-30s（依模型）。无并发瓶颈，FastAPI 默认 worker 即可。
- **正则扫描**：L1 11 模式 + L2 11 模式 + Python 8 模式 + SQL 1 模式，单次扫描线性 O(n) on text length，开销 ms 级。

## 7. 测试覆盖

| 文件 | 用例数 | 维度 |
|---|---|---|
| `test_schemas.py` | 5 | sql/python 至少一非空 + 3 个 sql_kind 联动 + ErrorResponse round-trip |
| `test_manifest.py` | 3 | mexico happy / unknown country / placeholder country |
| `test_redactor.py` | 15 | 11 family parametrize + 4 false-positive 边界 |
| `test_output_scanner.py` | 25 | 凭据 4 + Python 8 + DDL 13（含 5 DML reject + 2 quoted reject） |
| `test_prompt_assembler.py` | 9 | CJK 加权 3 + assemble + redact + 阈值护栏 |
| `test_orchestrator.py` | 6 | happy + 3 类策略守门 + 2 schema fallback |
| `test_api.py` | 11 | invalid_country 422 / placeholder 400 / credential_leak 422 + 7 ErrorType 映射 + mount |
| `test_e2e_mock_llm.py` | 1 | mexico mock LLM happy path（含 MEX017 + knowledge files=5）|
| `test_smoke_real_llm_mexico.py` | 0（skip） | real LLM smoke，CI 默认跳过 |
| **合计** | **72 + 1 skipped** | — |

测试用 stub `ModelClient`（构造注入 orchestrator），不依赖全局 `settings`、不调 real LLM、不连任何外部资源。

## 8. 风险排查

| # | 风险 | 应对 |
|---|---|---|
| 1 | demo0 后续修改引入新明文 | redactor 测试常驻；可选 pre-commit 扫描（V2 follow-up） |
| 2 | LLM JSON 不稳定 | ModelClient 内置 1 次 retry；失败 → 422 不静默降级（已知 follow-up：commit `32d64e0` 已修复） |
| 3 | DDL prefix 绕过（注释挟带 / quoted identifier） | strip 注释 + 反引号 / 双引号一律 reject；V2 可考虑安全 quoted identifier 解析 |
| 4 | 日志泄漏正文 | logger 严格白名单（path/size/hits） |
| 5 | Token 估算误差 | CJK ×1.5 启发式偏低 ~30%，800K 阈值留充足边际 |
| 6 | ModelClient 不返 token usage | `metadata.tokens_used=None`（Optional），`token_estimate` 始终填 |
| 7 | include_router 影响 /api/analyze | `test_api.py` 同时断言两条路径都存在 |
| 8 | L1/L2 family 漂移 | 同源约定 + 双侧测试集 anti-drift |
| 9 | placeholder country 误调用 → LLM 用未脱敏 `<PLACEHOLDER...>` | manifest 加载层 `ManifestNotImplemented` 前置拦截 → 400；test_api 含 indonesia 400 case |
| 10 | ModelClient 单点故障 | V1 接受直接 502；V2 可加 FALLBACK_MODELS |

无 P0 阻塞。

## 9. 运行时链路

```
POST /api/data-acquisition/generate (FastAPI)
  → ExecuteRequest Pydantic 校验（target_country enum / nl 非空）
  → DataAcquisitionOrchestrator.generate(request)
       ├── load_manifest(country) — placeholder 检测 → ManifestNotImplemented → 400
       ├── assemble_prompt(request, manifest)
       │     ├── 5 份 md 加载 → L1 redact() → 拼装
       │     ├── token 估算 → 超 800K → ValueError → 400 prompt_too_large
       │     └── 返回 (prompt, tokens, files, redaction_hits)
       ├── ModelClient.generate_structured(prompt, response_schema)
       │     └── status≠ok → json_parse hint → 422 schema_validation_failed
       │                  → 其他 → 502 upstream_llm_error
       ├── _enforce_output_policies(payload, manifest, rid)
       │     ├── scan_credentials(sql + python) → 422 credential_leak
       │     ├── scan_python_dangerous(python) → 422 dangerous_code
       │     └── check_sql_policy(sql, kind, prefix) → 422 ddl_policy_violation
       └── _build_response(...) — Pydantic 构造异常 → 422 schema_validation_failed
  → GenerateResponse JSON
```

错误路径：所有 OrchestratorError 由 `api.py` 统一查 `_STATUS_MAP` 映射到 HTTP 状态码 + ErrorResponse 序列化。

## 10. 遗留项

- **real LLM JSON 稳定性**：V1 完成时 3/3 失败（json_parse / Unterminated string / 缺 key），独立 follow-up 已在 `32d64e0` 修复（不在本审计区间）。
- **prompt/security hardening**：V1 完成后追加 `5183809` 把 ErrorResponse / OrchestratorError 改为固定安全短消息，避免泄漏 SQL / Python / LLM payload（不在本审计区间）。
- **印尼 / 巴铁 / 泰国 / 菲律宾 manifest**：占位 yaml 留位，未来填路径即开。
- **manifests / healthz endpoint**：V1 stub 501，未实现具体逻辑（Future Optional）。
- **3-5 条 Golden Case 评测集**：V1 Plan 提到的 prompt 调优基线评测集未建立，建议 V2 完成后补。
- **log 中可能含 redaction_event 的字符级 hits 计数**：当前实现仅计 hits 总数，不记 pattern 类别 — 故意为之，避免 fingerprint 泄漏。
