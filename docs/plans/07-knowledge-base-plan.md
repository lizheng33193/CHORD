# Plan 07 — Knowledge Base 子系统（INDEX 路由 + BM25 + learned/）

> **STATUS**: ✅ READY-TO-EXECUTE — v3（**V1 范围收敛为 mx + th 双国**，其余 3 国仅留接口）
>
> **v3 修订点**（对照 v2，2026-05-06 第六轮 paranoid 审核 + 用户范围决策）：
> - **P5 致命**：v2 测试 / 脚本 parametrize `["mexico","thailand","indonesia","pakistan","philippines"]` —— 但 [`indonesia.yaml`](data_acquisition_agent/configs/indonesia.yaml) 实测内容只有 `# 留位，V1 不验证`，`load_manifest("indonesia")` 必抛 `ManifestNotImplemented`，所有 5 国 parametrize 必挂在 indonesia 这一栏。**v3 修复**：用户决策 V1 仅做 mx + th 双国，其余 3 国（indonesia / pakistan / philippines）暂不实现，仅在 `COUNTRY_DIR_MAP` 留 5 国映射作为未来扩展接口；测试 / 脚本 parametrize 全量缩到 `["mexico","thailand"]`。
> - **P10 致命**：印尼 / 菲律宾两国实际 few 文件名是 `few-shot.md`（不是 `few.md`，实测 `Get-ChildItem`），v2 Task 0.2 「预期输出」+ Spec §0.1 「`few.md`（本国化 few-shot；**不是** few-shot.md）」都给错了断言。本 v3 把这 3 国移出 V1 范围后，文案同步标注「印尼 / 菲律宾未来扩展时 few 文件名为 `few-shot.md`，需在 yaml `few_md` 中对应（菲律宾 yaml 已正确，印尼 yaml 待补）」。
> - **P6 高危**：v2 Task 1.1 只展开墨西哥 1 国 INDEX.md 模板、其余「替换路径前缀」省略式占位，违反五点检查法第 2-3 条。**v3 修复**：mx + th 两国 INDEX.md 各自完整展开（各 ~50 行），不再有任何省略。
> - **P8 中**：v2 router `token_budget=int(TOKEN_LIMIT * 0.03)` ≈ 24K（仅 md 段），加上 `SYSTEM_PROMPT_ENGINE` (~3K) + 4 段 md (按 always_inject 后裁剪，~5-8K) + `user_block` (~2K) + 余量，总 prompt ≥ 30K，但 `budget_monitor.budget_target=25_000`、`exceeded=prompt_tokens>25_000` **永真**。**v3 修复**：`budget_target` 从 25_000 抬到 30_000（与 Spec §5.3 「整体感知预算」实际口径对齐）；router md_only budget 维持 ~24K，保持 Spec §5.3 表格一致。
> - **P9 信息**：Plan §0.1 / Phase 4 Task 4.1 引用的 `def assemble_prompt @ L87` / `user_block = ( @ L105` / `raise @ L151` / `return @ L152` 与 ground truth 偏 +/-3-6 行（实测分别为 L83 / L99 / L154 / L155）。**v3 修复**：所有行号引用以「函数体内位置感知」（如「`for label, p in [...]:` 5-md 循环段」）代替绝对行号，避免 `prompt_assembler.py` 后续改动一行让 Plan 行号引用过期。
>
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05（v2） / 2026-05-06（v3 mx+th 双国收敛）
> **关联 Spec**: `docs/specs/07-knowledge-base-design.md`（v3 同步）
> **HEAD baseline**: 待执行前打 `[baseline] plan-07`（**独立执行，不依赖 Plan 05**）
> **预计 Phase 数**: 5（Phase 0 baseline → Phase 1 INDEX + BM25 → Phase 2 Router → Phase 3 Archiver → Phase 4 Assembler 接入 + 验收）

---

## 0. Baseline 共识

### 0.1 关联文档
- Spec: `docs/specs/07-knowledge-base-design.md`（v3，必读）
- `PLANNING.md` 已知约束 7 条（Token 预算 / SQL 安全 / 凭据脱敏 / Surgical Hard Boundary）
- `CLAUDE.md` 关键约束 + DA artifact 安全约束（fail-safe default + 人工 ack）

### 0.2 V1 范围与未来扩展接口（用户范围决策 2026-05-06）
- **V1 仅做 mx + th 双国**：[`mexico.yaml`](data_acquisition_agent/configs/mexico.yaml) / [`thailand.yaml`](data_acquisition_agent/configs/thailand.yaml) 已填好生产路径 + 私有前缀 `dm_model.yyp_tmp_`；知识库 md 目录 `墨西哥/` / `泰国/` 实测齐全（每国 5 个 md，含 `few.md` / `all_examples .md`（含空格）/ `gem prompt.md`（含空格）/ `多国业务逻辑.md` / `scheme.md`）。
- **其余 3 国（indonesia / pakistan / philippines）当前不在 V1 范围**：
  - [`indonesia.yaml`](data_acquisition_agent/configs/indonesia.yaml) 是空 placeholder（`# 留位，V1 不验证`），未来扩展时需补全所有 yaml 字段
  - [`pakistan.yaml`](data_acquisition_agent/configs/pakistan.yaml) / [`philippines.yaml`](data_acquisition_agent/configs/philippines.yaml) yaml 已填，但未列入 V1 测试矩阵
  - 本 Plan 给 3 国留 `COUNTRY_DIR_MAP` 映射 + bm25_indexer / router 的 manifest 加载 fail-soft 兜底（manifest 缺失 / 无效 → 返回空 indexer / 全量回退），**未来填好 yaml + INDEX.md 即可自动接入，无需改 Plan 07 代码**
- **印尼 / 菲律宾未来扩展注意点**：实测 few 文件名是 `few-shot.md` 不是 `few.md`，对应 yaml 的 `few_md` 字段需写 `.../few-shot.md`（菲律宾 yaml 已正确指向 `few-shot.md`，印尼 yaml 待补时同此规则）。
- 本 Plan **独立于 Plan 05** 执行：mx + th 双国知识库 md 在 `demo0/各国数据知识库汇总/{墨西哥,泰国}/` 已就绪（实测）。

### 0.3 Zero Tolerance 关键约束（执行前明确）

> ⚠️ **与 PLANNING.md "Surgical Hard Boundary" 关系（执行前必读）**：
> 该硬边界仍按 PLANNING.md 作为默认约束执行。本 Plan 07 属于一次**明确授权的例外变更**：只允许新增知识库子模块，并修改 `data_acquisition_agent/prompt_assembler.py` **单文件**，前提条件：
>  ① Phase 0 Task 0.5 baseline 164 tests 必须 100% 全绿；
>  ② Phase 4 Task 4.7 改造后 164 tests 仍 100% 全绿（不允许少 1 个）；
>  ③ Task 4.0 三条守护单测（redact / TOKEN_LIMIT / 4-tuple）必须在改造前后都保持全绿。
> 任一条件不成立，立即 `git reset --hard {baseline_commit}` 并停止本 Plan。

**9 个核心 .py 不动**：
- `data_acquisition_agent/{api.py, connection.py, executor.py, manifest.py, orchestrator.py, output_scanner.py, output_writer.py, redactor.py, schemas.py}` 共 9 个文件**完全不动**
- 仅允许修改 `data_acquisition_agent/prompt_assembler.py` 一个文件
- 新增 `data_acquisition_agent/knowledge_base/` + `data_acquisition_agent/learned/` + `data_acquisition_agent/tests/test_knowledge_base/` 子目录**不算侵入**

**凭据脱敏不绕过（Zero Tolerance 硬约束）**：
- Phase 4 改造后 `prompt_assembler.py` 必须保留每个 md 文件的 `red, hits = redact(raw)` 调用
- 必须新增单测 `test_redactor_still_called_per_file` 兜底，否则 [complete] 不通过

**TOKEN_LIMIT = 800_000 硬上限保留**：
- Phase 4 改造后必须保留 `if tokens > TOKEN_LIMIT: raise ValueError("prompt_too_large")`
- 必须新增单测 `test_token_limit_still_raises` 兜底

**learned/ 归档能力 — Plan 07 降级为“只实现基础 archiver，不接运行时 ACK hook”**：
- `archive_example()` 函数签名 `user_acked: bool = False`（默认 False，调用方必须显式传 True）
- `sql_judge_l1_pass / sql_judge_l2_pass` 同样默认 False
- Plan 07 不再把 archiver 挂到 `app/api/orchestrator_routes.py` 或 `agent_loop.py`；自动归档接入依赖 Plan 08 SQLJudge 真实结果，后续单独执行

**`build_table_script` SQL 必须落在 `analyst_private_prefix` 内**：
- archiver 入库前 SQL 含 `CREATE TABLE` 必须以 `manifest.analyst_private_prefix` 开头（如 `dm_model.yyp_tmp_`），否则拒绝归档；`INSERT INTO` 不在 Plan 07 V1 检查范围内，避免与 `archiver.py` 的 `_DDL_RE` 实现口径漂移

**不修改的目录**：
- 不修改 `app/services/orchestrator_agent/`
- 不修改 `app/api/` 的 ACK 路由
- 不修改 `.agents/skills/`
- 不修改 `app/agents/`（Legacy 死代码）

### 0.4 baseline commit
```bash
git commit --allow-empty -m "[baseline] plan-07 — before execution"
```

### 0.5 测试矩阵
- DataAcq 现有 164 tests 全绿（Phase 0 + Phase 4 各跑一次）
- knowledge_base 新增 unit test 全绿（BM25 + Router + Parser + Archiver + Budget）
- **V1 双国（mx + th）INDEX 路由 + BM25 召回验证**（其余 3 国走 fail-soft 回退分支单测兜底，不进 parametrize）
- Token 用量从 250K → ≤30K 实测（budget_target=30_000）
- redactor 调用 + TOKEN_LIMIT 硬上限单测兜底

---

## 1. 范围

### 1.1 ✅ 包含
- `data_acquisition_agent/demo0/各国数据知识库汇总/{墨西哥,泰国}/INDEX.md` **2 份 V1 路由表**（中文目录；3 国未来扩展时按相同模板补，不在 V1 范围）
- `data_acquisition_agent/configs/local_dev/INDEX.md` 1 份 local_dev 路由表
- `data_acquisition_agent/knowledge_base/__init__.py` 模块入口 + `COUNTRY_DIR_MAP`（5 国映射保留作为未来扩展接口）+ `V1_COUNTRIES`（仅 mx + th）
- `data_acquisition_agent/knowledge_base/router.py` 路由器（INDEX + BM25 + 全量回退）
- `data_acquisition_agent/knowledge_base/index_parser.py` INDEX.md 解析（中/英文逗号双解析）
- `data_acquisition_agent/knowledge_base/bm25_indexer.py` BM25 索引（manifest 驱动；非 V1 国 fail-soft）
- `data_acquisition_agent/knowledge_base/archiver.py` learned/ 归档基础能力（fail-safe + 私有前缀校验；Plan 07 不接运行时 ACK hook）
- `data_acquisition_agent/knowledge_base/budget_monitor.py` Token 用量监控
- `data_acquisition_agent/prompt_assembler.py` 改造接入 router（保留 redact + TOKEN_LIMIT）
- Token 用量监控（`outputs/da_token_log.jsonl`）

### 1.2 ❌ 不包含
- Vector embedding 召回（V3）
- Chunk 切分（V2）
- Rerank（V2）
- 修改 `data_acquisition_agent/{api.py, connection.py, executor.py, manifest.py, orchestrator.py, output_scanner.py, output_writer.py, redactor.py, schemas.py}` 共 9 个核心 .py
- 修改 `app/services/orchestrator_agent/` / `app/api/` / `app/agents/` / `.agents/skills/`
- 依赖 Plan 05 任何输出（本 Plan 独立执行）

---

## Phase 0 — Baseline 核对（只读 + 依赖准备）

### Task 0.1 核对 prompt_assembler 真实接口 + manifest 路径 + schemas 字段名 + redact 返回类型
```powershell
Get-Content data_acquisition_agent/prompt_assembler.py | Select-String "^def assemble_prompt|^TOKEN_LIMIT|redact|estimate_tokens|prompt_too_large|SYSTEM_PROMPT_ENGINE" | Select-Object -First 12
Get-Content data_acquisition_agent/redactor.py | Select-String "^def redact|return " | Select-Object -First 6
Get-Content data_acquisition_agent/manifest.py | Select-String "^class CountryManifest|REQUIRED_MD|REQUIRED_FIELDS|analyst_private_prefix|REPO_ROOT|DA_LOCAL_DEV" | Select-Object -First 12
Get-Content data_acquisition_agent/schemas.py | Select-String "class GenerateRequest|class TargetAction|class TargetCountry|natural_language_request|target_country|target_action|BUILD_TABLE|EXTRACT"
Get-Content data_acquisition_agent/configs/mexico.yaml
Write-Host "--- mexico.local.yaml override 检查（仅在 \$env:DA_LOCAL_DEV=1 时才生效；默认 / CI / 生产不走这个 override） ---"
if (Test-Path data_acquisition_agent/configs/mexico.local.yaml) { Get-Content data_acquisition_agent/configs/mexico.local.yaml | Select-String "analyst_private_prefix|business_logic_md|schema_md" }
```
**预期输出**：
- `def assemble_prompt(request, manifest):`（**不是** `(query, country)`）
- `TOKEN_LIMIT = 800_000`
- `raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")`（**byte-identical 文案，改一个字都算违反 Zero Tolerance**）
- `from .redactor import redact` + `red, hits = redact(raw)` + `total_hits += hits`（**hits 是 int 不是 list；累加用 `+= hits`，写 `len(hits)` 立即 TypeError**）
- `def redact(text: str) -> tuple[str, int]`
- `def estimate_tokens(text: str) -> int:`
- `CountryManifest` 含 `analyst_private_prefix: str` 字段，`REPO_ROOT = Path(__file__).resolve().parent.parent`，`from_yaml` 把 md path 拼成 `REPO_ROOT / data[k]` 绝对 Path
- `load_manifest(country)` 中含 `if os.environ.get("DA_LOCAL_DEV") == "1": ... return CountryManifest.from_yaml(local_p)`—这是 **opt-in**，默认 / CI / 生产 都走生产 yaml，不走 local override
- `GenerateRequest` 含三字段：`natural_language_request: str` + `target_country: TargetCountry` + `target_action: Optional[TargetAction]`
- `TargetCountry` 枚举成员：`MEXICO = "mexico"` / `INDONESIA = "indonesia"` / `PAKISTAN = "pakistan"` / `THAILAND = "thailand"` / `PHILIPPINES = "philippines"`（取 `.value` 得小写英文国名）
- `TargetAction` 枚举成员：`BUILD_TABLE = "build_table"` / `EXTRACT = "extract"` / `BUILD_TABLE_AND_EXTRACT = "build_table_and_extract"`（**这三个是 schemas 枚举语义，不要与 LLM 输出的 `sql_kind = "query_only" / "build_table_script"` 混淆：后者是在 user_block JSON 契约中约束的 SQL 类别**）
- `mexico.yaml` 含 5 个 md key + `analyst_private_prefix: dm_model.yyp_tmp_`，路径中目录名为中文 `墨西哥/`
- `mexico.local.yaml` **可能存在**，`analyst_private_prefix: user_profile.tmp_`（与生产 yaml 不同）。**但默认 `load_manifest("mexico")` 不走这个 override**—仅在本地打开 `$env:DA_LOCAL_DEV="1"` 时才走。Plan/CI/跑 baseline / Plan §3.3 archiver test 都不设该 env var，默认拿到生产 prefix `dm_model.yyp_tmp_`。

**STOP 条件**：
- 接口签名不是 `(request, manifest)` → 回 Spec §5 修正全部 5 段相关代码块
- `redact()` 调用消失或 `TOKEN_LIMIT` 被改动 → 回 Spec §5 修正
- `redact` 返回签名不是 `tuple[str, int]` → 回 Plan §4.0 / §4.1 修复所有 `len(hits)` 误写、mock 的 `(raw, [])` 误写为 `(raw, 0)`
- `GenerateRequest` 字段名不是 `natural_language_request` / `target_country` → 回 Plan §4.0 / §4.1 / §4.3 把所有 `request.query` / `request.country` 替换为真实字段名后再继续
- `load_manifest` 内不是 `if os.environ.get("DA_LOCAL_DEV") == "1"` 而是默认优先 local → 回 Plan §Task 0.3 / §Task 3.3 把 baseline 脚本 与 archiver 测试里关于 prefix 的部分重新调整
- `raise` 文案不是 `prompt_too_large: {tokens} > {TOKEN_LIMIT}` → 回 §4.1 改造后代码段恢复原文案

### Task 0.2 核对现有 V1 双国 md 文件实际名字（含空格 + 中文）+ 3 国留位状态
```powershell
Get-ChildItem 'data_acquisition_agent/demo0/各国数据知识库汇总/' | Select-Object Name
Write-Host "--- V1 mx + th 实际文件 ---"
Get-ChildItem 'data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/' -File | Select-Object Name
Get-ChildItem 'data_acquisition_agent/demo0/各国数据知识库汇总/泰国/' -File | Select-Object Name
Write-Host "--- 3 国留位（仅信息，V1 不进 parametrize）---"
Get-ChildItem 'data_acquisition_agent/demo0/各国数据知识库汇总/印尼/' -File -ErrorAction SilentlyContinue | Select-Object Name
Get-ChildItem 'data_acquisition_agent/demo0/各国数据知识库汇总/巴铁/' -File -ErrorAction SilentlyContinue | Select-Object Name
Get-ChildItem 'data_acquisition_agent/demo0/各国数据知识库汇总/菲律宾/' -File -ErrorAction SilentlyContinue | Select-Object Name
Write-Host "--- 跨国共享 system_prompt ---"
Test-Path data_acquisition_agent/demo0/system_prompt.md
Write-Host "--- local_dev md ---"
Get-ChildItem data_acquisition_agent/configs/local_dev/ -File | Select-Object Name
Write-Host "--- yaml manifest 加载体检（V1 仅 mx + th 必须能加载，indonesia 现仍是 placeholder）---"
python -c "from data_acquisition_agent.manifest import load_manifest; [print(c, '=', load_manifest(c).few_md.exists()) for c in ['mexico','thailand']]"
```
**预期输出**：
- 5 国子目录（中文）：`巴铁 / 菲律宾 / 墨西哥 / 泰国 / 印尼`
- **V1 mx + th 双国每国 5 个 md（一字不差）**：`多国业务逻辑.md` / `all_examples .md`（含空格）/ **`few.md`**（mx + th 实测都是 `few.md`）/ `gem prompt.md`（含空格）/ `scheme.md`
- 3 国信息（仅供未来扩展参考，V1 不进测试 / 脚本 parametrize）：
  - 印尼：`多国业务逻辑.md` / `all_examples .md` / **`few-shot.md`**（注意：不是 `few.md`！）/ `gem prompt.md` / `scheme.md`；yaml 仍是空 placeholder
  - 巴铁：`多国业务逻辑.md` / `all_examples .md` / `few.md` / `gem prompt.md` / `scheme.md`；yaml 已填
  - 菲律宾：`多国业务逻辑.md` / `all_examples .md` / **`few-shot.md`**（注意：不是 `few.md`！）/ `gem prompt.md` / `scheme.md`；yaml 已填且正确指向 `few-shot.md`
- 跨国共享：`data_acquisition_agent/demo0/system_prompt.md` 存在
- local_dev 4 个 md：`all_examples.md`（无空格）/ `business_logic.md` / `few.md` / `scheme.md`
- yaml 体检：`mexico = True` + `thailand = True` 两行（任一 False 必须停 Plan 排查路径）

**STOP 条件**：mx 或 th 文件名 / 目录名 / yaml 加载与上述任何一条不符，回 Spec §0.1 / §2.1 修正后才能进 Phase 1。3 国不齐不阻塞 V1。

### Task 0.3 token 基线统计（5 条样本 NL）

> ✅ **默认不需 rename mexico.local.yaml**：Task 0.1 已确认 `load_manifest` 是 **opt-in** 走 local override（仅当 `$env:DA_LOCAL_DEV == "1"` 时）。
> 本脚本不设该 env var，`load_manifest("mexico")` 默认拿到生产 `mexico.yaml`，prefix = `dm_model.yyp_tmp_`。
> 脚本内项除 env 守护以充分防御（防止外层 shell 意外遗留 DA_LOCAL_DEV=1 造成 baseline 失真）。

**Create**: `scripts/plan_07_baseline_tokens.py`
**完整代码**:
```python
"""Plan 07 Phase 0 Task 0.3 — baseline token statistics on 5 sample NL queries.

Run: python scripts/plan_07_baseline_tokens.py | Tee-Object -FilePath .reports/plan-07-baseline-tokens.txt

Guarantee: 本脚本主动清理 DA_LOCAL_DEV env var，避免外层 shell 意外设置
导致拿到 local override（user_profile.tmp_）而不是生产 prefix 。
"""
import os
from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.prompt_assembler import assemble_prompt
from data_acquisition_agent.schemas import GenerateRequest, TargetCountry

SAMPLES = [
    "查找最近 7 天活跃用户的 top 10",
    "统计本月有逾期记录的用户数量",
    "导出 30 天内首贷通过且 mob1 无逾期的用户清单",
    "对比上周和本周的 eKYC 拦截率",
    "构建一张近 90 天复借首贷客群的标签宽表",  # 含 build_table_script
]

def main():
    # 脚本内主动清除 DA_LOCAL_DEV，保证走生产 yaml。避免外层 shell 上下文污染。
    os.environ.pop("DA_LOCAL_DEV", None)

    manifest = load_manifest("mexico")
    # 守护：拿到的应是生产 prefix，避免未来某人改了 mexico.yaml 使基线不可重复
    if manifest.analyst_private_prefix != "dm_model.yyp_tmp_":
        raise SystemExit(
            f"Expected production prefix 'dm_model.yyp_tmp_', got '{manifest.analyst_private_prefix}'. "
            "请检查 mexico.yaml 生产配置。"
        )
    totals: list[int] = []
    for i, q in enumerate(SAMPLES, 1):
        req = GenerateRequest(
            natural_language_request=q,
            target_country=TargetCountry.MEXICO,
        )
        _, tokens, _files, _hits = assemble_prompt(req, manifest)
        print(f"[{i}] tokens={tokens}  query={q[:40]}...")
        totals.append(tokens)
    avg = sum(totals) // len(totals)
    print(f"--- BASELINE_AVG_TOKENS = {avg} (samples = {len(totals)}) ---")

if __name__ == "__main__":
    main()
```

**执行**：
```powershell
mkdir -Force .reports
python scripts/plan_07_baseline_tokens.py | Tee-Object -FilePath .reports/plan-07-baseline-tokens.txt
```
**预期**：5 条 prompt token 平均值 ≈ 250K（与 Spec §0.1 baseline 对齐），文件落到 `.reports/plan-07-baseline-tokens.txt`，`BASELINE_AVG_TOKENS` 行明确给出整数。
**STOP 条件**：脚本 SystemExit 表示 manifest prefix 不是生产值，需检查 mexico.yaml 是否被改动；若 token 平均值 < 100K，检查是否走了 4 小 md、路径是否加载不上。

### Task 0.4 补充依赖 — jieba + rank-bm25（实测两者都不在）
**Modify**: `requirements.txt`（在末尾追加）
```
jieba>=0.42.1
rank-bm25==0.2.2
```
**前置实测验证**：
```powershell
Select-String -Path requirements.txt -Pattern "jieba|rank-bm25"
```
**预期**：执行前为空（即 jieba 与 rank-bm25 都不在）；追加后再次执行应返回 2 行匹配。

**安装 + jieba 字典预热（避免离线 CI hang）**：
```powershell
pip install -r requirements.txt
# jieba 首次切词会同步加载 ~50MB 字典；离线 / 慢网下可能卡 60s+。
# 这里做一次 90s 超时的预热，命中即返回；超时则停 Plan 排查（绝不能让 Phase 1+ 测试在首次切词上 hang）。
$job = Start-Job -ScriptBlock { python -c "import jieba; jieba.initialize(); print('jieba_ok'); print(list(jieba.cut('查找活跃用户')))" }
Wait-Job $job -Timeout 90 | Out-Null
if ($job.State -eq "Completed") {
    Receive-Job $job
    Remove-Job $job
    python -c "from rank_bm25 import BM25Okapi; print('rank_bm25_ok')"
} else {
    Stop-Job $job; Remove-Job $job
    throw "jieba dict load >90s; STOP and pre-vendor jieba/dict.txt before continuing."
}
```
**预期**：依次输出 `jieba_ok` + 分词结果 + `rank_bm25_ok`（首次会下载字典 ~50MB；超过 90 秒立即 STOP，由用户决定预下载策略）。

### Task 0.5 验证 baseline 164 tests 仍绿（持久化基线数）
```powershell
mkdir -Force .reports
python -m pytest data_acquisition_agent/tests/ -v 2>&1 | Tee-Object -FilePath .reports/plan-07-baseline-tests.txt | Select-String "passed|failed|error" | Select-Object -Last 5
```
**预期**：`164 passed (1 skipped)` 或更高。完整 stdout 落到 `.reports/plan-07-baseline-tests.txt`（Phase 4 Task 4.7 通过对比该文件首尾两行 `passed` 数确认无回归——基线数固化在文件，不依赖 PowerShell 变量跨 session 存活）。
**STOP 条件**：失败任何一个 test 都不能进 Phase 1。

### Task 0.6 确认 learned/ 运行时接入本 Plan 不做
```powershell
Get-Content app/api/orchestrator_routes.py | Select-String "class _AckBody|def ack_endpoint|resolve_ack" | Select-Object -First 20
Get-Content app/services/orchestrator_agent/agent_loop.py | Select-String "awaiting_user_ack|wait_ack|ACK 通过|execute_out" | Select-Object -First 20
```
**预期**：
- `app/api/orchestrator_routes.py` 的 ACK body 只承载 `confirm / tool_call_id / decision`，不含 `nl_query / generated_sql / country`。
- `agent_loop.py` 的 ACK 通过分支能拿到 `tool_input["request"]`、`tool_input["country"]`、`qr.sql_text`，但 Plan 07 **不修改该文件**。

**结论记录**：Plan 07 Phase 3 只实现 `archive_example()` 基础能力与安全单测，不接入运行时 ACK hook；自动归档接入依赖 Plan 08 SQLJudge 真实结果，另起后续 Plan。

### Phase 0 commit（先 diff 后 commit）
```powershell
git status --short
git diff -- requirements.txt
# ⚠️ 在 commit 前先把 `.reports/` 加进 .gitignore（却不进 git history）
#    该目录装临时核对报告，不是产品产出。
if (-not (Select-String -Path .gitignore -Pattern "^\.reports/" -SimpleMatch -Quiet)) {
    Add-Content -Path .gitignore -Value "`n.reports/"
}
# ⚠️ 用户审核 diff 后再执行下面两行
git add .gitignore requirements.txt scripts/plan_07_baseline_tokens.py
git commit -m "chore(07): phase 0 baseline + jieba/rank-bm25 deps"
```

---

## Phase 1 — V1 双国 INDEX.md + BM25 索引（manifest 驱动）

### Task 1.1 编写 V1 双国 INDEX.md（中文目录 + 含空格文件名，**两国均完整展开**）

> **v3 范围决策**：V1 仅创建 mx + th 两份 INDEX.md。3 国（印尼 / 巴铁 / 菲律宾）未来扩展时按相同模板补即可（注意印尼 / 菲律宾 `few` 文件名为 `few-shot.md`，对应 yaml `few_md` 字段需写 `.../few-shot.md`）。Plan 07 v3 不创建这 3 份 INDEX.md，但 `COUNTRY_DIR_MAP` 仍保留 5 国映射 + bm25_indexer / router 的 manifest 加载 fail-soft 兜底。

**Create 2 个文件**（每个文件按 Spec §2.2 模板，含 6 个 entry：1 个跨国共享 system_prompt + 5 个国家私有 md）：

1. `data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/INDEX.md`
2. `data_acquisition_agent/demo0/各国数据知识库汇总/泰国/INDEX.md`

**完整代码（mx + th 两份各自全量给出，无任何省略式占位）**：

````markdown
# Mexico Data Acquisition Knowledge Base — INDEX

> 本文件为 LLM 路由用，列出本目录下每个 md 文件的元数据。
> 路由优先级：always_inject > INDEX 关键词命中 > BM25 兜底 > 全量回退（env var）

---

## system_prompt.md
- **path**: data_acquisition_agent/demo0/system_prompt.md
- **title**: 跨国共享 system prompt（任务流程 / JSON 输出契约 / analyst_private_prefix 规则）
- **keywords**: [system, prompt, role, task_orientation, json_format_rules, analyst_private_prefix]
- **usage_hint**: 必须始终注入，承载任务流程与输出契约
- **token_estimate**: 3000
- **always_inject**: true

## 多国业务逻辑.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/多国业务逻辑.md
- **title**: 业务黑话词典（mob1 / eKYC 拦截 / 复借首贷 / 客群定义 / 时间窗口）
- **keywords**: [活跃用户, 沉默用户, 风控, 阈值, 分层, mob1, eKYC, 复借, 首贷, 黑话, 业务规则]
- **usage_hint**: 当用户问题涉及"什么算 X"、"X 的定义"、"X 的判断标准"
- **token_estimate**: 5200
- **always_inject**: false

## scheme.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/scheme.md
- **title**: StarRocks 物理 schema（主表 / 维度表 / 事件表 / UID 字段名）
- **keywords**: [schema, table, column, dwd_, ods_, dws_, fact_, dim_, 字段, 表结构, uid, user_uuid, individual_uuid]
- **usage_hint**: 任何涉及"查询哪张表"、"字段是什么类型"、"表之间怎么 JOIN"的问题
- **token_estimate**: 8500
- **always_inject**: true

## few.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/few.md
- **title**: 目标国原生验证代码（高频 SQL 模板 + 目标国本地化 quirks）
- **keywords**: [example, few-shot, 模板, sql 示例, 时区, 渠道, 风控标识]
- **usage_hint**: 默认作为基础 few-shot；本地化字段替换时优先级最高
- **token_estimate**: 12000
- **always_inject**: true

## all_examples .md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/all_examples .md
- **title**: 跨国全局 SQL 示例库（100+ 个 NL→SQL 历史成功 case，跨国宏观骨架）
- **keywords**: [完整示例, 历史 case, 高级查询, CTE, 漏斗, 跨国]
- **usage_hint**: 复杂查询场景下补充示例；提取纯逻辑骨架，禁止直接带入参考国字段
- **token_estimate**: 45000
- **always_inject**: false

## gem prompt.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/gem prompt.md
- **title**: Gemini 提示词补丁（gem 模型行为微调）
- **keywords**: [gemini, prompt patch, 模型微调]
- **usage_hint**: 仅 gem 模型路由命中时注入
- **token_estimate**: 1500
- **always_inject**: false
````

````markdown
# Thailand Data Acquisition Knowledge Base — INDEX

> 本文件为 LLM 路由用，列出本目录下每个 md 文件的元数据。
> 路由优先级：always_inject > INDEX 关键词命中 > BM25 兜底 > 全量回退（env var）

---

## system_prompt.md
- **path**: data_acquisition_agent/demo0/system_prompt.md
- **title**: 跨国共享 system prompt（任务流程 / JSON 输出契约 / analyst_private_prefix 规则）
- **keywords**: [system, prompt, role, task_orientation, json_format_rules, analyst_private_prefix]
- **usage_hint**: 必须始终注入，承载任务流程与输出契约
- **token_estimate**: 3000
- **always_inject**: true

## 多国业务逻辑.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/多国业务逻辑.md
- **title**: 业务黑话词典（mob1 / eKYC 拦截 / 复借首贷 / 客群定义 / 时间窗口）
- **keywords**: [活跃用户, 沉默用户, 风控, 阈值, 分层, mob1, eKYC, 复借, 首贷, 黑话, 业务规则]
- **usage_hint**: 当用户问题涉及"什么算 X"、"X 的定义"、"X 的判断标准"
- **token_estimate**: 5200
- **always_inject**: false

## scheme.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/scheme.md
- **title**: StarRocks 物理 schema（主表 / 维度表 / 事件表 / UID 字段名）
- **keywords**: [schema, table, column, dwd_, ods_, dws_, fact_, dim_, 字段, 表结构, uid, user_uuid, individual_uuid]
- **usage_hint**: 任何涉及"查询哪张表"、"字段是什么类型"、"表之间怎么 JOIN"的问题
- **token_estimate**: 8500
- **always_inject**: true

## few.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/few.md
- **title**: 目标国原生验证代码（高频 SQL 模板 + 目标国本地化 quirks）
- **keywords**: [example, few-shot, 模板, sql 示例, 时区, 渠道, 风控标识]
- **usage_hint**: 默认作为基础 few-shot；本地化字段替换时优先级最高
- **token_estimate**: 12000
- **always_inject**: true

## all_examples .md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/all_examples .md
- **title**: 跨国全局 SQL 示例库（100+ 个 NL→SQL 历史成功 case，跨国宏观骨架）
- **keywords**: [完整示例, 历史 case, 高级查询, CTE, 漏斗, 跨国]
- **usage_hint**: 复杂查询场景下补充示例；提取纯逻辑骨架，禁止直接带入参考国字段
- **token_estimate**: 45000
- **always_inject**: false

## gem prompt.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/gem prompt.md
- **title**: Gemini 提示词补丁（gem 模型行为微调）
- **keywords**: [gemini, prompt patch, 模型微调]
- **usage_hint**: 仅 gem 模型路由命中时注入
- **token_estimate**: 1500
- **always_inject**: false
````

> **⚠️ token_estimate 实测填写（Phase 1 收尾必做）**：
> 上面给出的所有 `token_estimate` 数字仅是 **mexico 初始估算值（th 直接复用）**，必须按实测重写。Phase 1 两份 INDEX.md 写完后，**必须用以下批量脚本一次性回写所有 12 个 entry**（V1 双国 × 6 entry）：
>
> **Create**: `scripts/plan_07_fill_index_token_estimate.py`
> **完整代码**：
> ```python
> """Plan 07 Phase 1 收尾 — 批量按 estimate_tokens 实测值回写所有 INDEX.md 的 token_estimate 字段。
>
> 用法：python scripts/plan_07_fill_index_token_estimate.py
> 副作用：原地改写 V1 双国 INDEX.md（数据采集子项目内部）。
> V1 范围：mexico + thailand。未来扩展 indonesia / pakistan / philippines 时把 country code
> 加入 COUNTRIES，COUNTRY_CN_MAP 已预留 5 国映射。
> """
> import re
> from pathlib import Path
> from data_acquisition_agent.prompt_assembler import estimate_tokens
> from data_acquisition_agent.knowledge_base.index_parser import parse_index_md
> from data_acquisition_agent.manifest import REPO_ROOT
>
> # V1 仅 mx + th。未来扩展时把 indonesia / pakistan / philippines 加进来。
> COUNTRIES = ["mexico", "thailand"]
> COUNTRY_CN_MAP = {
>     "mexico": "墨西哥",
>     "thailand": "泰国",
>     "indonesia": "印尼",
>     "pakistan": "巴铁",
>     "philippines": "菲律宾",
> }
>
> def fix_one(country: str):
>     entries = parse_index_md(country)
>     index_md_path = REPO_ROOT / f"data_acquisition_agent/demo0/各国数据知识库汇总/{COUNTRY_CN_MAP[country]}/INDEX.md"
>     content = index_md_path.read_text(encoding="utf-8")
>     for e in entries:
>         file_path = REPO_ROOT / e["file"]
>         if not file_path.exists():
>             print(f"[{country}] SKIP missing file: {e['file']}")
>             continue
>         actual = estimate_tokens(file_path.read_text(encoding="utf-8"))
>         # 替换该 entry 块下第一处 - **token_estimate**: <number>
>         pattern = re.compile(
>             rf"(- \*\*path\*\*: {re.escape(e['file'])}.*?- \*\*token_estimate\*\*: )\d+",
>             re.DOTALL,
>         )
>         new_content, n = pattern.subn(rf"\g<1>{actual}", content, count=1)
>         if n == 1:
>             content = new_content
>             print(f"[{country}] {e['file']} -> {actual}")
>         else:
>             print(f"[{country}] WARN no token_estimate match for {e['file']}")
>     index_md_path.write_text(content, encoding="utf-8")
>
> if __name__ == "__main__":
>     for c in COUNTRIES:
>         fix_one(c)
> ```
>
> **执行 + 验证**：
> ```powershell
> python scripts/plan_07_fill_index_token_estimate.py
> # 验收：每条 entry 都打印 country + path + 真实数字
> # 2 国 × 6 entry = 12 行真实回写
> ```
> **不靠目测、不照抄、不跨国复用**。12 个 entry 都打印才算 Phase 1 通过。

> **提交提醒**：该脚本是 Phase 1 的可执行产物，必须随 Phase 1 commit 一起纳入 git，不能只本地运行后漏提交。

### Task 1.2 编写 local_dev/INDEX.md
**Create**: `data_acquisition_agent/configs/local_dev/INDEX.md`
**完整代码**：
````markdown
# Local Dev (MySQL 3-table) Knowledge Base — INDEX

> DA_LOCAL_DEV=1 时使用；4 个本地 mysql 用 md（无空格文件名）+ 跨国共享 system_prompt.md

---

## system_prompt.md
- **path**: data_acquisition_agent/demo0/system_prompt.md
- **title**: 跨国共享 system prompt
- **keywords**: [system, prompt, role, task_orientation, json_format_rules]
- **usage_hint**: 必须始终注入
- **token_estimate**: 3000
- **always_inject**: true

## scheme.md
- **path**: data_acquisition_agent/configs/local_dev/scheme.md
- **title**: 本地 mysql 3 表 schema
- **keywords**: [schema, table, mysql, 字段, 表结构]
- **usage_hint**: 涉及表名 / 字段问题
- **token_estimate**: 800
- **always_inject**: true

## business_logic.md
- **path**: data_acquisition_agent/configs/local_dev/business_logic.md
- **title**: 本地业务规则
- **keywords**: [活跃用户, 业务规则, 定义]
- **usage_hint**: 业务定义问题
- **token_estimate**: 600
- **always_inject**: false

## few.md
- **path**: data_acquisition_agent/configs/local_dev/few.md
- **title**: 本地 few-shot SQL 模板
- **keywords**: [example, few-shot, sql 示例]
- **usage_hint**: 默认 few-shot
- **token_estimate**: 1200
- **always_inject**: true

## all_examples.md
- **path**: data_acquisition_agent/configs/local_dev/all_examples.md
- **title**: 本地完整示例库
- **keywords**: [完整示例, 历史 case]
- **usage_hint**: 复杂查询补充
- **token_estimate**: 3000
- **always_inject**: false
````

### Task 1.3 创建 knowledge_base 模块入口 + COUNTRY_DIR_MAP
**Create**: `data_acquisition_agent/knowledge_base/__init__.py`
**完整代码**:
```python
"""Knowledge base subsystem (Plan 07).

提供 INDEX 路由 + BM25 检索 + learned/ 自动归档。
不修改 9 个核心 .py 之一（仅修改 prompt_assembler.py，受 164 tests 锁定）。
"""

# 英文 country code → 中文目录名（保留 5 国映射作为未来扩展接口；
# V1 仅 mx + th 进 parametrize / build_indexer，其余 3 国未填好 yaml + INDEX.md
# 时 bm25_indexer / router fail-soft 自动跳过）
COUNTRY_DIR_MAP: dict[str, str] = {
    "mexico": "墨西哥",
    "thailand": "泰国",
    "indonesia": "印尼",
    "pakistan": "巴铁",
    "philippines": "菲律宾",
}

# V1 范围：仅在这两国跑 BM25 build / 测试 parametrize / 启动自检。
# 未来扩展时把 indonesia / pakistan / philippines 加进来即可，无需改 Plan 07 代码。
V1_COUNTRIES: list[str] = ["mexico", "thailand"]

SUPPORTED_COUNTRIES: list[str] = sorted(COUNTRY_DIR_MAP.keys()) + ["local_dev"]
```

### Task 1.4 实现 INDEX.md parser（中/英文逗号双解析）
**Create**: `data_acquisition_agent/knowledge_base/index_parser.py`
**完整代码**:
```python
"""Parse INDEX.md to extract metadata (Plan 07 Phase 1)."""
import re
from pathlib import Path
from typing import TypedDict

from data_acquisition_agent.knowledge_base import COUNTRY_DIR_MAP
from data_acquisition_agent.manifest import REPO_ROOT


class IndexEntry(TypedDict):
    file: str  # repo 相对路径，来自 INDEX.md 的 path 字段
    title: str
    keywords: list[str]
    usage_hint: str
    token_estimate: int
    always_inject: bool


def _resolve_index_path(country: str) -> Path:
    """根据国家 code 找 INDEX.md。中文目录 / local_dev 双兼容。"""
    if country == "local_dev":
        return REPO_ROOT / "data_acquisition_agent/configs/local_dev/INDEX.md"
    cn = COUNTRY_DIR_MAP.get(country)
    if cn is None:
        return REPO_ROOT / "__nonexistent__/INDEX.md"
    return REPO_ROOT / f"data_acquisition_agent/demo0/各国数据知识库汇总/{cn}/INDEX.md"


def parse_index_md(country: str) -> list[IndexEntry]:
    index_path = _resolve_index_path(country)
    if not index_path.exists():
        return []
    content = index_path.read_text(encoding="utf-8")

    entries: list[IndexEntry] = []
    sections = re.split(r"\n## ", content)
    for sec in sections[1:]:  # 跳过文件 H1
        lines = sec.splitlines()
        entry: IndexEntry = {
            "file": "",
            "title": "",
            "keywords": [],
            "usage_hint": "",
            "token_estimate": 0,
            "always_inject": False,
        }
        for line in lines[1:]:
            line_stripped = line.strip()
            if line_stripped.startswith("- **path**:"):
                entry["file"] = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.startswith("- **title**:"):
                entry["title"] = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.startswith("- **keywords**:"):
                kw_str = line_stripped.split(":", 1)[1].strip().strip("[]")
                entry["keywords"] = [
                    k.strip().strip('"\'')
                    for k in re.split(r"[,，]", kw_str)
                    if k.strip()
                ]
            elif line_stripped.startswith("- **usage_hint**:"):
                entry["usage_hint"] = line_stripped.split(":", 1)[1].strip()
            elif line_stripped.startswith("- **token_estimate**:"):
                entry["token_estimate"] = int(line_stripped.split(":", 1)[1].strip())
            elif line_stripped.startswith("- **always_inject**:"):
                entry["always_inject"] = "true" in line_stripped.lower()
        if entry["file"]:
            entries.append(entry)
    return entries
```

> **顺序修复**：`scripts/plan_07_fill_index_token_estimate.py` 会 import `parse_index_md()`，所以 parser 必须在 Phase 1 先创建，不能等到 Phase 2。

### Task 1.5 实现 BM25 indexer（manifest 驱动，不 glob）
**Create**: `data_acquisition_agent/knowledge_base/bm25_indexer.py`
**完整代码**:
```python
"""BM25 keyword indexer (Plan 07 Phase 1) — manifest 驱动，不 glob 目录。"""
from pathlib import Path
import jieba
from rank_bm25 import BM25Okapi

from data_acquisition_agent.manifest import load_manifest


class BM25Indexer:
    """文件级 BM25 索引；索引源 = manifest 的 5 个 md key（不 glob 目录）"""

    def __init__(self, country: str):
        self.country = country
        self.doc_paths: list[str] = []
        self.bm25: BM25Okapi | None = None
        self._build()

    def _build(self):
        try:
            manifest = load_manifest(self.country)
        except Exception:
            return  # manifest 缺失则索引为空（router 走全量回退）
        md_paths: list[Path] = [
            manifest.system_prompt_md,
            manifest.business_logic_md,
            manifest.all_examples_md,
            manifest.schema_md,
            manifest.few_md,
        ]
        corpus: list[list[str]] = []
        for p in md_paths:
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8")
            tokens = list(jieba.cut(content))
            corpus.append(tokens)
            self.doc_paths.append(str(p))
        if corpus:
            self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 3) -> list[str]:
        if self.bm25 is None:
            return []
        query_tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(query_tokens)
        top_indices = scores.argsort()[-top_k:][::-1]
        return [self.doc_paths[i] for i in top_indices if scores[i] > 0]


# 单例缓存（lazy 构建）
_INDEXERS: dict[str, BM25Indexer] = {}


def get_indexer(country: str) -> BM25Indexer:
    if country not in _INDEXERS:
        _INDEXERS[country] = BM25Indexer(country)
    return _INDEXERS[country]
```

### Task 1.6 unit test（测试目录与现有 164 tests 同根 + 含中文路径 + 含空格文件名 + 启动自检）
**Create**: `data_acquisition_agent/tests/test_knowledge_base/__init__.py`（空文件）
**Create**: `data_acquisition_agent/tests/test_knowledge_base/test_bm25_indexer.py`

> ⚠️ **测试根目录决策**：所有 knowledge_base 单测放在 `data_acquisition_agent/tests/test_knowledge_base/`（与现有 164 tests 同根 `data_acquisition_agent/tests/`），**不放** `tests/data_acquisition_agent/`（顶层 tests 目录），避免分裂测试根。Phase 4 Task 4.7 一行 `pytest data_acquisition_agent/tests/ -v` 即可看到 163 + 新增。

**完整代码**:
```python
"""Plan 07 Phase 1 — BM25 indexer 单测。"""
from pathlib import Path

import pytest

from data_acquisition_agent.knowledge_base import V1_COUNTRIES
from data_acquisition_agent.knowledge_base import bm25_indexer as _bm25_module
from data_acquisition_agent.knowledge_base.bm25_indexer import get_indexer
from data_acquisition_agent.manifest import REPO_ROOT, load_manifest


@pytest.fixture(autouse=True)
def _reset_indexer_singleton():
    """BM25 有模块级单例 _INDEXERS；autouse 清理 避免 test 顺序敏感 / 跨调用污染"""
    _bm25_module._INDEXERS.clear()
    yield
    _bm25_module._INDEXERS.clear()


def _norm(p) -> str:
    """路径归一： manifest 返 REPO_ROOT/<rel> 绝对 Path 含反斜杠；INDEX.md 写相对 path 含正斜杠。
    两边 resolve() 后 §as_posix() 才能集合相减。"""
    return Path(p).resolve().as_posix()


@pytest.mark.parametrize("country", V1_COUNTRIES)
def test_indexer_builds_for_v1_countries(country):
    indexer = get_indexer(country)
    assert indexer.country == country
    # V1 双国 yaml + INDEX.md 都齐全，BM25 必能 build 出非空索引
    assert indexer.bm25 is not None
    assert len(indexer.doc_paths) >= 1


def test_doc_paths_are_real_files():
    """指向的所有 md 文件必须真实存在（防 glob 错路径回归）"""
    indexer = get_indexer("mexico")
    for p in indexer.doc_paths:
        assert Path(p).exists(), f"BM25 indexed missing file: {p}"


def test_chinese_directory_path():
    """墨西哥的 doc_paths 应该包含中文目录名 '墨西哥'"""
    indexer = get_indexer("mexico")
    chinese_paths = [p for p in indexer.doc_paths if "墨西哥" in p]
    assert len(chinese_paths) >= 1, "Expected at least one path containing 墨西哥"


def test_filename_with_space():
    """all_examples .md 含 1 个空格的文件名能被正确读到"""
    indexer = get_indexer("mexico")
    space_paths = [p for p in indexer.doc_paths if "all_examples .md" in p]
    assert len(space_paths) == 1, "Expected exactly one path with 'all_examples .md' (with space)"


def test_search_returns_only_existing_paths():
    indexer = get_indexer("mexico")
    results = indexer.search("活跃用户 7 天", top_k=3)
    assert len(results) <= 3
    for p in results:
        assert Path(p).exists(), f"BM25 search returned missing file: {p}"


def test_non_v1_country_falls_back_to_empty_indexer():
    """3 国（indonesia / pakistan / philippines）yaml 缺失或 INDEX.md 不存在时，
    bm25_indexer 必须 fail-soft（不抛异常，返回空 doc_paths），让 router 走全量回退"""
    indexer = get_indexer("indonesia")  # indonesia.yaml 仍是 placeholder
    # 不抛异常即可；具体行为是 doc_paths 为空 / bm25 为 None / 内部回退（实现选其一）
    assert hasattr(indexer, "doc_paths")


@pytest.mark.parametrize("country", V1_COUNTRIES)
def test_index_covers_manifest_5_md(country):
    """Spec §6.4 启动自检：INDEX.md 列出的 path 集合 ⊇ manifest 的 5 个 md key
    （防 INDEX 漏列文件 / 写错路径回归）

    ⚠️ 路径归一必须走 resolve().as_posix()：manifest 返回 `REPO_ROOT/<rel>` 绝对路径 + 反斜杠；
       INDEX.md 写 `data_acquisition_agent/...` 相对路径 + 正斜杠；不归一集合差永远不为空。
    """
    from data_acquisition_agent.knowledge_base.index_parser import parse_index_md
    manifest = load_manifest(country)
    manifest_paths = {
        _norm(manifest.system_prompt_md),
        _norm(manifest.business_logic_md),
        _norm(manifest.all_examples_md),
        _norm(manifest.schema_md),
        _norm(manifest.few_md),
    }
    entries = parse_index_md(country)
    # INDEX.md path 字段是仓库相对路径—拼上 REPO_ROOT 后 resolve
    index_paths = {_norm(REPO_ROOT / e["file"]) for e in entries}
    missing = manifest_paths - index_paths
    assert not missing, f"INDEX.md missing manifest md keys for {country}: {missing}"
```
> 该测试模块顶部需 `from data_acquisition_agent.knowledge_base import V1_COUNTRIES`，由 Task 1.3 的 `__init__.py` 导出。

**验证**:
```powershell
python -m pytest data_acquisition_agent/tests/test_knowledge_base/test_bm25_indexer.py -v
```
**预期**: 2 (V1 build parametrize) + 5 (独立：doc_paths_real / chinese_dir / filename_space / search_existing / non_v1_fallback) + 2 (启动自检 parametrize) = **9 case 全过**。

### Phase 1 commit（先 diff 后 commit；显式列 V1 双国中文路径，避免 PowerShell 通配符在中文路径下失效）
```powershell
git status --short
# ⚠️ 用户审核 diff 后再执行下面块
git add `
  'data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/INDEX.md' `
  'data_acquisition_agent/demo0/各国数据知识库汇总/泰国/INDEX.md' `
  data_acquisition_agent/configs/local_dev/INDEX.md `
    scripts/plan_07_fill_index_token_estimate.py `
  data_acquisition_agent/knowledge_base/ `
  data_acquisition_agent/tests/test_knowledge_base/
git commit -m "feat(07): phase 1 — V1 mx+th INDEX.md + manifest-driven BM25 indexer + index<->manifest self-check"
```

---

## Phase 2 — Router（INDEX + BM25 + 全量回退三级，manifest 驱动）

### Task 2.1 实现 router（manifest 驱动的全量回退 + always_inject 保护）
**Create**: `data_acquisition_agent/knowledge_base/router.py`
**完整代码**:
```python
"""Knowledge router — INDEX -> BM25 -> full fallback (Plan 07 Phase 2).

三级路由：
1. always_inject 文件强制注入（不进 budget trim 候选名单）
2. INDEX 关键词命中 + BM25 top_k 兜底（这两类才进 budget trim）
3. 全量回退（USE_FULL_KNOWLEDGE_INJECTION=1 或 INDEX 解析为空时）
"""
import os
from pathlib import Path
from .index_parser import parse_index_md
from .bm25_indexer import get_indexer


def route_knowledge(query: str, country: str, token_budget: int = 15000) -> list[str]:
    """返回应该加载的 md 文件**绝对路径字符串**（POSIX 形式）列表。

    INDEX.md 内 `file` 字段是 repo 相对路径，bm25 候选也可能是相对，本函数末尾统一
    用 `(REPO_ROOT / p).resolve().as_posix()` 规一化为绝对路径，调用方（assembler）
    可直接 `Path(p).read_text()` 而无需关心当前工作目录。
    """
    if os.getenv("USE_FULL_KNOWLEDGE_INJECTION") == "1":
        return _full_inject_from_manifest(country)

    entries = parse_index_md(country)
    if not entries:
        return _full_inject_from_manifest(country)

    # —— 1. always_inject 保护（不参与 budget 削减） ——
    must_inject: list[str] = [e["file"] for e in entries if e["always_inject"]]

    # —— 2. INDEX 关键词命中候选 ——
    optional: list[str] = []
    query_lower = query.lower()
    for e in entries:
        if e["always_inject"]:
            continue
        if any(kw.lower() in query_lower for kw in e["keywords"]):
            optional.append(e["file"])

    # —— 3. BM25 兜底候选（最多 3 个，不重复） ——
    if len(optional) < 3:
        bm25_results = get_indexer(country).search(query, top_k=3)
        for path in bm25_results:
            if path not in must_inject and path not in optional:
                optional.append(path)

    # —— 4. budget 削减只削 optional，must_inject 始终保留 ——
    file_to_estimate = {e["file"]: e["token_estimate"] for e in entries}
    used = sum(file_to_estimate.get(p, 5000) for p in must_inject)
    result = list(must_inject)
    for path in optional:
        est = file_to_estimate.get(path, 5000)
        if used + est <= token_budget:
            result.append(path)
            used += est

    if not result:
        return _full_inject_from_manifest(country)
    # P1 修复：统一规一化为绝对 POSIX 路径，调用方不必关心 cwd
    from data_acquisition_agent.manifest import REPO_ROOT
    return [(REPO_ROOT / p if not Path(p).is_absolute() else Path(p)).resolve().as_posix() for p in result]


def _full_inject_from_manifest(country: str) -> list[str]:
    """从 manifest 读 5 个 md key —— 不 glob 目录（避免漏 system_prompt 跨国共享 + 防止误吃 INDEX.md）"""
    try:
        from data_acquisition_agent.manifest import load_manifest
    except ImportError:
        return []
    try:
        manifest = load_manifest(country)
    except Exception:
        return []
    paths = [
        manifest.system_prompt_md,
        manifest.business_logic_md,
        manifest.all_examples_md,
        manifest.schema_md,
        manifest.few_md,
    ]
    # P1 修复：统一返回绝对路径字符串，manifest.<field>_md 已是绝对 Path，.resolve() 幂等。
    # 调用方（Plan 4.1 assembler 改造）只需信任返回是绝对路径，不需以 REPO_ROOT 拼接。
    return [Path(p).resolve().as_posix() for p in paths if p.exists()]
```

> **路径约定**：router 返回 **绝对路径字符串**（POSIX 形式，跨平台一致）。INDEX.md 路径与 manifest fallback 路径都被规一化为绝对 POSIX。Plan Task 4.1 中 `_label_for_path()` 可删掉 `if not p.is_absolute()` 兑底分支（因 router 保证总是绝对）。

### Task 2.2 unit test（含 always_inject + 路径存在断言）
**Create**: `data_acquisition_agent/tests/test_knowledge_base/test_router.py`
**完整代码**:
```python
"""Plan 07 Phase 2 — router 单测。"""
from pathlib import Path

import pytest

from data_acquisition_agent.knowledge_base.index_parser import parse_index_md
from data_acquisition_agent.knowledge_base.router import (
    route_knowledge,
    _full_inject_from_manifest,
)


def test_index_parses_chinese_keyword_comma():
    """INDEX.md 关键词用中文逗号或英文逗号都应能解析"""
    entries = parse_index_md("mexico")
    assert len(entries) >= 5
    # 至少一个 entry 的 keywords 非空
    assert any(len(e["keywords"]) > 0 for e in entries)


def test_index_resolves_real_paths():
    """每个 entry 的 file 字段必须指向真实存在的 md（防 INDEX 写错路径）"""
    from data_acquisition_agent.manifest import REPO_ROOT
    entries = parse_index_md("mexico")
    for e in entries:
        assert (REPO_ROOT / e["file"]).exists(), f"INDEX entry path does not exist: {e['file']}"


def test_route_returns_existing_files():
    from data_acquisition_agent.manifest import REPO_ROOT
    result = route_knowledge("查询活跃用户", "mexico", token_budget=15000)
    assert isinstance(result, list)
    assert len(result) >= 1
    for p in result:
        path = Path(p)
        if not path.is_absolute():
            path = REPO_ROOT / path
        assert path.exists(), f"Router returned missing file: {p}"


def test_always_inject_preserved_under_tight_budget():
    """budget=5000 极小时，always_inject 仍必须出现在结果里"""
    entries = parse_index_md("mexico")
    must_inject = {e["file"] for e in entries if e["always_inject"]}
    assert len(must_inject) >= 1, "INDEX must have at least one always_inject=true entry"
    result = route_knowledge("xyz完全不相关的查询", "mexico", token_budget=5000)
    for f in must_inject:
        assert f in result, f"always_inject file must survive tight budget: {f}"


def test_full_fallback_via_env(monkeypatch):
    monkeypatch.setenv("USE_FULL_KNOWLEDGE_INJECTION", "1")
    result = route_knowledge("anything", "mexico")
    # 全量回退应来自 manifest 5 个 md key（绝不含 INDEX.md）
    assert all(not p.endswith("INDEX.md") for p in result)
    assert len(result) >= 4  # 5 个 md，至少 4 个能在硬盘上找到


def test_full_fallback_uses_manifest_not_glob():
    """全量回退绝不能漏跨国共享 system_prompt.md"""
    result = _full_inject_from_manifest("mexico")
    assert any("system_prompt.md" in p for p in result)
```

### Task 2.3 验证
```powershell
python -m pytest data_acquisition_agent/tests/test_knowledge_base/ -v
```
**预期**: BM25 9 case（Phase 1 V1 双国 build 2 + 5 独立 + 启动自检 2，含 non_v1 fail-soft）+ Router 6 case = **15 case 全过**。

### Phase 2 commit（先 diff 后 commit）
```powershell
git status --short
git diff --stat HEAD
# ⚠️ 用户审核 diff 后再执行下一行
git add data_acquisition_agent/knowledge_base/ data_acquisition_agent/tests/test_knowledge_base/
git commit -m "feat(07): phase 2 router three-tier fallback (always_inject + manifest fallback)"
```

---

## Phase 3 — learned/ 自动归档闭环（fail-safe + 私有前缀）

### Task 3.1 实现 archiver（fail-safe 默认 false + build_table_script 私有前缀校验）
**Create**: `data_acquisition_agent/knowledge_base/archiver.py`
**完整代码**:
```python
"""Auto-archive successful SQL examples to learned/{country}/v1/ (Plan 07 Phase 3).

Zero Tolerance：
- 三个 gate 默认 False（fail-safe）：sql_judge_l1_pass / sql_judge_l2_pass / user_acked
- build_table_script 类 SQL 必须落在 manifest.analyst_private_prefix 下，否则拒绝归档
- learned/ 路径在 data_acquisition_agent/learned/{country}/v1/，不放 configs/ 下（避免污染原 yaml manifest）
"""
import json
import re
from datetime import datetime
from typing import Optional
from uuid import uuid4

from data_acquisition_agent.manifest import REPO_ROOT, load_manifest


MAX_TOKENS_PER_EXAMPLE = 1000
LEARNED_ROOT = REPO_ROOT / "data_acquisition_agent" / "learned"

# build_table_script 的识别：以 CREATE TABLE 起头的 DDL（启动可 IF NOT EXISTS）
# CREATE TABLE 是 archiver 需要检查的唯一 DDL 类型，包括两种合法写法：
#   - `CREATE TABLE t(...)`
#   - `CREATE TABLE IF NOT EXISTS t(...)`
# `INSERT INTO ... SELECT` 不属于 build_table_script（即使含 CREATE 关键字作为字符串也不算），不需前缀检查。
#
# ⚠️ 表名捕获用 [^\s\(]+ 而不是 \S+—后者会在 `CREATE TABLE my_table(col INT)`（表名与
#    左括号无空格）场景下贪婪吃到 `my_table(col`，导致 starts_with prefix 检查误判。
_DDL_RE = re.compile(r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(]+)", re.IGNORECASE | re.MULTILINE)


def _ddl_target_starts_with(sql: str, prefix: str) -> bool:
    """检查 DDL 目标 schema/table 是否以 analyst_private_prefix 开头。
    若 SQL 不是 DDL，返回 True（非 build_table_script 路径，跳过本检查）。
    """
    m = _DDL_RE.search(sql)
    if not m:
        return True  # 非 build_table_script，不需要前缀检查
    target = m.group(1).strip("`\"'")     # ← 仅 1 个捕获组，不是 .group(2)
    return target.startswith(prefix.rstrip("."))


def archive_example(
    nl_query: str,
    generated_sql: str,
    country: str,
    sql_judge_l1_pass: bool = False,  # ⚠️ fail-safe 默认 False
    sql_judge_l2_pass: bool = False,
    user_acked: bool = False,
    execution_success: Optional[bool] = None,
    keywords: Optional[list[str]] = None,
) -> Optional[str]:
    """归档一条 NL→SQL 成功 case 到 learned/{country}/v1/

    Returns: 归档文件绝对路径 / None（任何 gate 不过时）
    """
    # —— 1. 三 gate 必须全 True 才归档 ——
    if not (sql_judge_l1_pass and sql_judge_l2_pass and user_acked):
        return None

    # —— 2. token 上限 ——
    estimated_tokens = (len(nl_query) + len(generated_sql)) // 3
    if estimated_tokens > MAX_TOKENS_PER_EXAMPLE:
        return None

    # —— 3. build_table_script 私有前缀校验 ——
    try:
        manifest = load_manifest(country)
        prefix = manifest.analyst_private_prefix
    except Exception:
        return None  # manifest 缺失即拒绝归档
    if not _ddl_target_starts_with(generated_sql, prefix):
        return None  # 命中 DDL 但目标不在私有前缀，安全拒绝

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = uuid4().hex[:8]
    out_dir = LEARNED_ROOT / country / "v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"example_{ts}_{suffix}.md"
    nl_query_json = json.dumps(nl_query, ensure_ascii=False)
    title = nl_query.replace("\n", " ")[:50]

    md = f"""---
nl_query: {nl_query_json}
generated_sql: |
{_indent(generated_sql, 2)}
keywords: {json.dumps(keywords or [], ensure_ascii=False)}
sql_judge_l1_pass: {str(sql_judge_l1_pass).lower()}
sql_judge_l2_pass: {str(sql_judge_l2_pass).lower()}
user_acked: {str(user_acked).lower()}
user_acked_at: "{datetime.now().isoformat()}"
execution_success: {str(execution_success).lower() if execution_success is not None else 'null'}
---

# Example: {title}

## NL Query
{nl_query}

## Generated SQL
```sql
{generated_sql}
```
"""
    out_path.write_text(md, encoding="utf-8")
    return str(out_path)


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines())
```

### Task 3.2 本 Plan 不接运行时 ACK hook
**降级决策**：Plan 07 只实现 `archive_example()` 基础能力与安全单测，不修改 `app/api/orchestrator_routes.py`、不修改 `app/services/orchestrator_agent/agent_loop.py`。

**原因**：真实 ACK endpoint 的 body 只有 `confirm / tool_call_id / decision`，拿不到 `nl_query / generated_sql / country`；而 `agent_loop.py` 的 ACK 通过分支虽然有 `tool_input["request"]`、`tool_input["country"]`、`qr.sql_text`，但自动归档还需要 Plan 08 SQLJudge 的真实 L1/L2 结果。Plan 07 不硬编码 `sql_judge_l1_pass=True` / `sql_judge_l2_pass=True`，避免把未审查 SQL 伪装成已审查。

**后续接入点（不在 Plan 07 执行）**：Plan 08 完成后，在 `agent_loop.py` 的 ACK 通过分支，使用真实 SQLJudge 结果 + `user_acked=True` 调 `archive_example()`，并保证归档失败不阻塞 ACK 主流程。

### Task 3.3 unit test（含 fail-safe 默认 + DDL 前缀校验；测试目录与现有 164 tests 同根）
**Create**: `data_acquisition_agent/tests/test_knowledge_base/test_archiver.py`
**完整代码**:
```python
"""Plan 07 Phase 3 — archiver 单测（fail-safe + 前缀校验）。

⚠️ 默认走生产 yaml：调用 `load_manifest('mexico')` 不设 `DA_LOCAL_DEV` env
   返回生产配置，prefix = `dm_model.yyp_tmp_`。本测**动态取 manifest.analyst_private_prefix**，
   不硬预设字面量，不依赖“mexico.local.yaml 存在与否”。仅当用户手动 `$env:DA_LOCAL_DEV="1"` 才会拿到 local override（user_profile.tmp_），该场景不在本测预设范围内。
"""
from pathlib import Path

import pytest

import data_acquisition_agent.knowledge_base.archiver as archiver


def test_default_args_fail_safe(tmp_path, monkeypatch):
    """三个 gate 默认 False，仅传 country 必须不归档"""
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
    """build_table_script 落到非私有 schema 时必须拒绝"""
    monkeypatch.setattr(archiver, "LEARNED_ROOT", tmp_path / "learned")
    # 任何不以 manifest.analyst_private_prefix 开头的 DDL 都应被拒为越界
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
    """处于 analyst_private_prefix 下的 DDL 应被放行。

    ⚠️ 默认走生产 yaml：不设 DA_LOCAL_DEV env，load_manifest('mexico') 拿到 prefix=`dm_model.yyp_tmp_`。
       本测动态取 manifest.analyst_private_prefix，不硬预设具体值，不受 mexico.local.yaml 是否存在影响。
    """
    monkeypatch.delenv("DA_LOCAL_DEV", raising=False)  # 明确清除 env，避免外层 shell 污染
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
```

### Task 3.4 手动调用确认 learned/ 有文件（不走运行时 ACK）
```powershell
# 仅验证 archiver 基础能力，不代表运行时自动归档已接入。
# 归档路径锚定 REPO_ROOT；手动 smoke test 结束后删除本次生成文件，避免留下未跟踪样例。
$path = python -c "from data_acquisition_agent.knowledge_base.archiver import archive_example; print(archive_example('活跃用户 top 10','SELECT user_id FROM dwd_users LIMIT 10','mexico',sql_judge_l1_pass=True,sql_judge_l2_pass=True,user_acked=True) or '')"
Write-Output $path
Test-Path $path
Remove-Item $path -Force -ErrorAction Stop
```
**预期**: `$path` 形如 `.../data_acquisition_agent/learned/mexico/v1/example_*.md`，`Test-Path $path` 返回 `True`，随后删除本次 smoke test 产物。

### Phase 3 commit（先 diff 后 commit）
```powershell
git status --short
git diff --stat HEAD
# ⚠️ 用户审核 diff 后再执行下一行
git add data_acquisition_agent/knowledge_base/archiver.py data_acquisition_agent/tests/test_knowledge_base/test_archiver.py
git commit -m "feat(07): phase 3 learned archiver foundation (fail-safe + private prefix check)"
```

---

## Phase 4 — assembler 接入 + 验收 + [complete]

> ⚠️ **Zero Tolerance 红线**：本 Phase 改造 `prompt_assembler.py` 时必须保留：
> 1. 每个 md 文件经 `redact(raw)` 脱敏（**禁止跳过**）
> 2. `if tokens > TOKEN_LIMIT: raise ValueError(...)` 末尾兜底（**禁止删除**）
> 3. `assemble_prompt(request, manifest)` 现有签名（**禁止改成 `(query, country)`**）
> 4. 4-tuple 返回 `(prompt, tokens, files, total_hits)`（**禁止改成 `str`**）

### Task 4.0 新增「兜底未被绕过」单测（先写）
**Create**: `data_acquisition_agent/tests/test_knowledge_base/test_assembler_safety.py`
**完整代码**:
```python
"""Plan 07 Phase 4 Task 4.0 —— 守护 redactor 不被旁路 + TOKEN_LIMIT 不被删除。

⚠️ Phase 0 Task 0.1 已实测：
    data_acquisition_agent.schemas.GenerateRequest 含字段
     - natural_language_request: str
     - target_country: TargetCountry  (Enum，传 .value 得字符串如 "mexico")
   如果 schemas.py 字段名不一致，按 Task 0.1 STOP 条件回此处修字段名再继续。
"""
from unittest.mock import patch

import pytest

from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.prompt_assembler import (
    TOKEN_LIMIT,
    assemble_prompt,
)
from data_acquisition_agent.schemas import GenerateRequest, TargetCountry


@pytest.fixture
def mexico_manifest():
    return load_manifest("mexico")


def _build_request(query: str = "查找最近 7 天活跃用户的 top 10") -> GenerateRequest:
    """字段名以现有 schemas.py 实测为准（Phase 0 Task 0.1 已确认）"""
    return GenerateRequest(
        natural_language_request=query,
        target_country=TargetCountry.MEXICO,
    )


def test_redactor_called_per_md_file(mexico_manifest):
    """assemble_prompt 必须对每个被选中的 md 调用 redact()，不能整体或 0 次

    ⚠️ redact 返回签名是 tuple[str, int]（hits 是 int）—mock wraps 必须返 (raw, 0)，
       不是 (raw, [])；prompt_assembler 累加用 `total_hits += hits`，传 list 立即 TypeError。
    """
    with patch("data_acquisition_agent.prompt_assembler.redact", wraps=lambda raw: (raw, 0)) as mock_redact:
        prompt, tokens, files, hits = assemble_prompt(_build_request(), mexico_manifest)
    assert mock_redact.call_count >= 3, (
        f"redact() must be called for each selected md file (got {mock_redact.call_count})"
    )


def test_token_limit_still_raises_when_exceeded(mexico_manifest):
    """伪造 estimate_tokens 让 prompt 超 TOKEN_LIMIT，必须触发 ValueError

    ⚠️ 原文案 byte-identical：`prompt_too_large: {tokens} > {TOKEN_LIMIT}`（不是 "prompt exceeds TOKEN_LIMIT"）
    """
    with patch(
        "data_acquisition_agent.prompt_assembler.estimate_tokens",
        return_value=TOKEN_LIMIT + 1,
    ):
        with pytest.raises(ValueError, match=r"prompt_too_large:\s*\d+\s*>\s*\d+"):
            assemble_prompt(_build_request(), mexico_manifest)


def test_returns_4tuple(mexico_manifest):
    """signature 不能从 4-tuple 退化"""
    result = assemble_prompt(_build_request(), mexico_manifest)
    assert isinstance(result, tuple) and len(result) == 4
    prompt, tokens, files, hits = result
    assert isinstance(prompt, str) and len(prompt) > 0
    assert isinstance(tokens, int) and tokens > 0
    assert isinstance(files, list) and len(files) >= 1
    assert isinstance(hits, int) and hits >= 0
```
**前置**：Phase 0 Task 0.1 已确认 `GenerateRequest`/`schemas.py` 中真实字段名为 `natural_language_request` + `target_country: TargetCountry`。如 schemas 字段名实际不同，按 Task 0.1 STOP 条件回此处修字段名再继续。

**改造前守护验证（regression guard，不要求先红）**：
```powershell
python -m pytest data_acquisition_agent/tests/test_knowledge_base/test_assembler_safety.py -v
```
**预期**：3 case 全过——说明改造前的 prompt_assembler 已具备守护能力（redact + TOKEN_LIMIT + 4-tuple），可作为 Phase 4 改造前的 baseline；改造后再跑必须仍 100% 全过。

### Task 4.1 改造 prompt_assembler 接入 router（保留 redact + TOKEN_LIMIT + user_block）
**Modify**: `data_acquisition_agent/prompt_assembler.py`

> ⚠️ **改造原则（Surgical，严以 byte-identical）**：原文件 `assemble_prompt(request, manifest)` 函数体（实测位置：`def assemble_prompt(...)` 行 → 之后是「5-md 循环段」→ 然后是「`user_block = ( ... )` 6 大段拼接段」→ 函数末尾「`prompt = "\n\n".join(sections)` + token 检查 + 4-tuple 返回」三部分构成。**本 Plan 仅改造第一部分（`for label, p in [...]:` 5-md 循环段中"md 列表来源"），其余 byte-identical 全保留**：
> 1. 5-md 循环内的 `redact(raw)` + `total_hits += hits`（**hits 是 int，不是 list；用 `+= hits` 不要写 `+= len(hits)` 否则 TypeError**） + `sections.append(f"# === {label} ===\n{red}")` + `if label == "system_prompt": sections.append(SYSTEM_PROMPT_ENGINE)` 位置、顺序、拼接格式 全部 byte-identical
> 2. `user_block`（6 大段：user_request metadata + 5-key JSON 契约 + Minimal skeleton + task_orientation 0-5 + analyst_private_prefix 强制规则 + json_format_rules 1-6）全部 byte-identical 保留——删任何一段都会造成 build_table_script 越界保护丢失、JSON 契约断裂
> 3. 函数末尾 `prompt = "\n\n".join(sections)` + `tokens = estimate_tokens(prompt)` + `if tokens > TOKEN_LIMIT: raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")` + `return prompt, tokens, files, total_hits` 全部 byte-identical（**raise 文案 byte-identical：是 `prompt_too_large: {tokens} > {TOKEN_LIMIT}`，不是 `prompt exceeds TOKEN_LIMIT`**）
> 4. 函数外的 `SYSTEM_PROMPT_ENGINE` 字符串常量 / `estimate_tokens` / `TOKEN_LIMIT` / import 段全部 byte-identical
>
> ⚠️ **不写绝对行号**：v2 曾用 L87 / L105 / L151 / L152，与 ground truth (实测约 L83 / L99 / L154 / L155) 偏差 +/-3-6 行，且文件后续被改一行就让所有行号引用过期。v3 改用「函数体内位置感知」描述（如「`for label, p in [...]:` 5-md 循环段」），避免行号回归脆弱性。

**改造前实际代码**（Phase 0 Task 0.1 读取得到，以下为真实结构示意；user_block 6 大段实际行数 ~42 行，仅显示首与尾两行——**改造时必须 byte-identical 保留全部 6 大段**：从原文件 `user_block = (` 行起到对应右括号 `)` 行止，整段拷贝，**禁止省略 / 改写 / 重排**）:
```python
TOKEN_LIMIT = 800_000
SYSTEM_PROMPT_ENGINE = """... (原文件 L20-L75 大段定义，改造时 byte-identical 保留) ..."""

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - cjk
    return int(cjk * 1.5 + other / 4)

def assemble_prompt(request, manifest):
    sections = []
    files = []
    total_hits = 0
    # ╔════════ 本 Plan 仅替换以下 5-md 循环段（仅"md 列表来源"改成 router）════════╗
    for label, p in [
        ("system_prompt", manifest.system_prompt_md),
        ("business_logic", manifest.business_logic_md),
        ("all_examples", manifest.all_examples_md),
        ("schema", manifest.schema_md),
        ("few", manifest.few_md),
    ]:
        raw = p.read_text(encoding="utf-8")
        red, hits = redact(raw)            # ← hits 是 int，不是 list
        total_hits += hits                 # ← 直接 += hits（不能写 += len(hits)，否则 TypeError）
        sections.append(f"# === {label} ===\n{red}")
        if label == "system_prompt":
            sections.append(SYSTEM_PROMPT_ENGINE)   # ← 仅在 system_prompt md 紧后插，不能提到顶部
        files.append(str(p))
    # ╚════════ 替换段结束 ════════╝
    user_block = (
        f"# === user_request ===\ncountry={request.target_country.value}\n"
        f"action={request.target_action.value if request.target_action else 'auto'}\n"
        f"request:\n{request.natural_language_request}\n\n"
        # ... 原 L108-L145 6 大段 byte-identical 保留 ...
        # 包含：① 5-key JSON 契约（reasoning_summary / sql / sql_kind / python / audit_report）
        #       ② Minimal valid skeleton 范例
        #       ③ task_orientation 0-5（含 STRICT DEFAULT sql_kind="query_only"）
        #       ④ analyst_private_prefix 强制规则（"Any build_table_script DDL target MUST start with this exact prefix"）
        #       ⑤ json_format_rules 1-6
        "6. Example of correctly escaped SQL: \"sql\": \"SELECT uid\\nFROM dwb.t\\nWHERE channel='MEX017'\\nLIMIT 100\""
    )
    sections.append(user_block)
    prompt = "\n\n".join(sections)
    tokens = estimate_tokens(prompt)
    if tokens > TOKEN_LIMIT:                # ← Zero Tolerance：保留
        raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")  # ← 文案 byte-identical
    return prompt, tokens, files, total_hits
```

**改造后**（仅替换 5-md 循环段中"md 列表来源"。user_block 6 大段、SYSTEM_PROMPT_ENGINE、estimate_tokens、`raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")` 全部 byte-identical 保留）:
```python
from pathlib import Path as _Path
from data_acquisition_agent.knowledge_base.router import route_knowledge


# 路径 → manifest 上对应语义 label 的反查
# 必须用 resolve().as_posix() 规一化两侧路径：
#   manifest 字段是 REPO_ROOT/<rel>（绝对 Path + 反斜杠）
#   router 返回的 file 是 INDEX.md 中写的相对正斜杠 path
# 不规一化集合相减永远不为空（N-20 修复点）
def _label_for_path(path_str: str, manifest) -> str:
    from data_acquisition_agent.manifest import REPO_ROOT
    p = _Path(path_str)
    if not p.is_absolute():
        p = REPO_ROOT / p
    norm = p.resolve().as_posix()
    label_attr = (
        ("system_prompt", "system_prompt_md"),
        ("business_logic", "business_logic_md"),
        ("all_examples", "all_examples_md"),
        ("schema", "schema_md"),
        ("few", "few_md"),
    )
    for label, attr in label_attr:
        if _Path(getattr(manifest, attr)).resolve().as_posix() == norm:
            return label
    return "extra"  # learned/ 或 BM25 兜底命中的 md（V1 暂归 extra label）


def assemble_prompt(request, manifest):
    """V2：用 router 选 md，再走原有 redact + TOKEN_LIMIT 流程。

    Zero Tolerance：
      - 每个 md 必须经过 redact()（hits 是 int，用 += hits 不要 += len(hits)）
      - SYSTEM_PROMPT_ENGINE 必须仅在 system_prompt md 紧后插入（不能提到顶部）
      - user_block 6 大段 byte-identical 保留（含 5-key JSON 契约、Minimal skeleton、
        task_orientation 0-5、analyst_private_prefix 强制规则、json_format_rules 1-6）
      - 末尾 raise ValueError(f"prompt_too_large: ...") 文案 byte-identical
      - 4-tuple 返回 (prompt, tokens, files, total_hits) 不变
    字段名以 schemas.py 实测为准：GenerateRequest.natural_language_request / target_country.value
    """
    selected_paths = route_knowledge(
        query=request.natural_language_request,
        country=request.target_country.value,  # TargetCountry Enum -> "mexico" / "thailand" / ...
        token_budget=int(TOKEN_LIMIT * 0.03),   # ≈24K，仅给 md 列表用（router 内部裁剪；剩余 token 给
                                                # SYSTEM_PROMPT_ENGINE + user_block + 余量）。
                                                # Spec §5.3「整体感知预算」=30K（含 system + 4 段 md +
                                                # user_block 余量），与 budget_monitor.budget_target 同口径。
                                                # 不要误把这里的 24K md-only 预算与 budget_monitor 30K 整体口径混用。
    )

    sections = []
    files = []
    total_hits = 0

    # 兜底：router 必须保证 system_prompt 命中（always_inject=True），
    # 否则 SYSTEM_PROMPT_ENGINE 永远不会被注入 → 严重 bug
    has_system_prompt = any(
        _label_for_path(p, manifest) == "system_prompt"
        for p in selected_paths
        if _Path(p).exists()
    )
    if not has_system_prompt:
        raise RuntimeError(
            "router did not select system_prompt.md (always_inject contract broken). "
            "Check INDEX.md system_prompt entry has always_inject: true."
        )

    # ╔════════ 仅替换"循环遍历来源"，循环体内 redact / sections.append / SYSTEM_PROMPT_ENGINE 位置全部 byte-identical ════════╗
    for path_str in selected_paths:
        from data_acquisition_agent.manifest import REPO_ROOT
        p = _Path(path_str)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if not p.exists():
            continue  # router 应已过滤，这里再兜一层
        label = _label_for_path(path_str, manifest)
        raw = p.read_text(encoding="utf-8")
        red, hits = redact(raw)             # ← hits: int 保留
        total_hits += hits                  # ← += hits （**不是** len(hits)）
        sections.append(f"# === {label} ===\n{red}")    # ← 拼接格式 byte-identical
        if label == "system_prompt":
            sections.append(SYSTEM_PROMPT_ENGINE)        # ← 位置 byte-identical：紧跟 system_prompt md
        files.append(path_str)
    # ╚════════ 替换段结束 ════════╝

    # ⚠️ user_block 6 大段（原文件中位于 5-md 循环段之后、`prompt = "\n\n".join(...)` 之前的 `user_block = ( ... )`
    #    整段，含起 `(` 与终 `)`）byte-identical 保留——以下整段必须从原文件 `user_block = (` 起到对应右括号 `)` 止
    #    整段拷贝，**禁止省略 / 改写 / 重排**。任何遗漏都会导致 build_table_script
    #    越界保护丢失、JSON 5-key 契约断裂、analyst_private_prefix 强制规则失效。
    user_block = (
        f"# === user_request ===\ncountry={request.target_country.value}\n"
        f"action={request.target_action.value if request.target_action else 'auto'}\n"
        f"request:\n{request.natural_language_request}\n\n"
        "Return ONLY a JSON object with EXACTLY these 5 top-level keys. ALL 5 keys MUST be present in every response — do NOT omit any key. Use null for unused string fields; use the default object for audit_report when no risk applies.\n"
        "\n"
        "Required keys (all 5 mandatory, no additions, no omissions):\n"
        "  - reasoning_summary: string (under 300 words; never null, use \"\" if empty)\n"
        "  - sql: string or null (use null if no SQL is produced)\n"
        "  - sql_kind: 'query_only' or 'build_table_script' (MUST be one of these two literals; do NOT use 'select_data', 'extract', etc. If sql is null, set sql_kind to 'query_only'.)\n"
        "  - python: string or null (REQUIRED key; if Python is not needed, set \"python\": null — do NOT omit this key)\n"
        "  - audit_report: object — REQUIRED key, MUST always be present. Shape: {\"high_risk_ddl\": bool, \"final_verdict\": string}. If no risk applies, use the default: {\"high_risk_ddl\": false, \"final_verdict\": \"\"}.\n"
        "\n"
        "audit_report.high_risk_ddl must be true iff sql_kind=='build_table_script'.\n"
        "\n"
        "Minimal valid skeleton (illustrative — your real values go here, but every key shown below MUST appear):\n"
        "  {\n"
        "    \"reasoning_summary\": \"<your summary>\",\n"
        "    \"sql\": \"<select ...>\",\n"
        "    \"sql_kind\": \"query_only\",\n"
        "    \"python\": null,\n"
        "    \"audit_report\": {\"high_risk_ddl\": false, \"final_verdict\": \"\"}\n"
        "  }"
        "\n\n# === task_orientation ===\n"
        "0. STRICT DEFAULT: sql_kind MUST be \"query_only\" UNLESS the user's request literally contains an explicit build/persist/materialize intent (e.g. \"create a table\", \"build a result table\", \"persist\", \"materialize\", \"save into a new table\", \"建表\", \"物化\", \"落表\"). If unsure, choose \"query_only\". Returning \"build_table_script\" without explicit intent will be rejected and the request will fail.\n"
        "1. Default to sql_kind=\"query_only\" and return a single SELECT statement.\n"
        "2. Use sql_kind=\"build_table_script\" ONLY when the user explicitly asks to create, persist, save, materialize, or build a table.\n"
        "3. Do NOT generate Python code that connects to databases.\n"
        "4. Do NOT use pymysql, sqlalchemy, mysql.connector, starrocks connector, or any DB client in python.\n"
        "5. If SQL alone is sufficient to answer the request, set python to null.\n"
        "\n# === analyst_private_prefix ===\n"
        f"The analyst private table prefix is: {manifest.analyst_private_prefix}\n"
        "Any build_table_script DDL target MUST start with this exact prefix.\n"
        f"Example target: {manifest.analyst_private_prefix}<short_task_name>\n"
        "\n# === json_format_rules ===\n"
        "1. Output MUST be a single valid JSON object on one line or with properly escaped newlines.\n"
        "2. All newlines inside string values (especially sql and reasoning_summary) MUST be escaped as \\n — raw newlines will break JSON parsing.\n"
        "3. All double quotes inside string values MUST be escaped as \\\".\n"
        "4. Keep reasoning_summary under 300 words.\n"
        "5. Do NOT wrap the JSON in markdown code fences.\n"
        "6. Example of correctly escaped SQL: \"sql\": \"SELECT uid\\nFROM dwb.t\\nWHERE channel='MEX017'\\nLIMIT 100\""
    )
    sections.append(user_block)

    prompt = "\n\n".join(sections)
    tokens = estimate_tokens(prompt)
    if tokens > TOKEN_LIMIT:                # ← 保留
        raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")  # ← 文案 byte-identical
    return prompt, tokens, files, total_hits
```

> ✅ **router 接口契约**：本改造仍按 §2.2 router 返回 `list[str]` 设计，**不改 router 接口**；
> 通过 `_label_for_path()` 用 `Path.resolve().as_posix()` 规一化两侧路径完成反查（解决 N-20：路径未规一化导致集合相减永不为空）。
> §2.2 / §2.3 router 实现与单测保持不变。

**Zero Tolerance 改前自检**：
```powershell
Get-Content data_acquisition_agent/prompt_assembler.py | Select-String "redact|TOKEN_LIMIT|prompt_too_large|raise ValueError|user_request|task_orientation|analyst_private_prefix|json_format_rules|Required keys|Minimal valid skeleton"
```
**改后再次执行同命令**，匹配数必须 ≥ 改前数（不少于：redact 1 + TOKEN_LIMIT 2 + prompt_too_large 1 + raise 1 + user_request 1 + task_orientation 1 + analyst_private_prefix 2 + json_format_rules 1 + Required keys 1 + Minimal valid skeleton 1 = 12 行）。

**改后 byte-identical 关键句验证**（防 user_block / SYSTEM_PROMPT_ENGINE / raise 文案被误删 / 误改）：
```powershell
$matches = Get-Content data_acquisition_agent/prompt_assembler.py | Select-String "Required keys.*5 mandatory|Minimal valid skeleton|Any build_table_script DDL target MUST start with this exact prefix|Example of correctly escaped SQL|sql_kind MUST be|build_table_script.*ONLY when|prompt_too_large: \{tokens\} > \{TOKEN_LIMIT\}"
$matches.Count
# 预期：≥ 6（不少于 6 处命中）。如果 < 6 说明 user_block / raise 文案被误改，git reset --hard 重做。
```

### Task 4.2 加 token 用量监控
**Create**: `data_acquisition_agent/knowledge_base/budget_monitor.py`
**完整代码**:
```python
"""Plan 07 Phase 4 — token 实测落 jsonl，用于事后压缩比分析。

⚠️ Zero Tolerance：写入日志的 query_preview 必须先经 redact()，
   防止 NL query 中可能携带的凭据 / token / phone 等回流到磁盘。
"""
import json
from datetime import datetime
from pathlib import Path

from data_acquisition_agent.redactor import redact


def log_token_usage(
    query: str,
    country: str,
    prompt_tokens: int,
    response_tokens: int = 0,
    files: list[str] | None = None,
):
    """每次 SQL 生成后写一行 jsonl，便于事后复盘压缩比。

    ⚠️ budget_target = 30_000 是 Spec §5.3 定义的“整体感知预算”（含 SYSTEM_PROMPT_ENGINE ~3K
       + 4 段 md（按 always_inject 后裁剪 ~5-8K）+ user_block ~2K + 余量），与 router 的
       md-only token_budget = TOKEN_LIMIT * 0.03 ≈ 24K 是不同口径。
       prompt_tokens 是拼接后全部输入 token，与 budget_target 同口径，超过 30K 即记录 exceeded
       供事后复盘。
       ⚠️ 不要误写为与 router 的 24K md-only 预算比较：prompt_tokens 含 system + user_block，
       总是 > 24K，那样 exceeded 永远为 True（v2 的 25_000 取值就有此问题，v3 抬到 30_000 修复）。
    """
    # 截断后再脱敏；redact 始终返回 (red_text, hits)
    query_red, _hits = redact(query[:80])
    log_entry = {
        "ts": datetime.now().isoformat(),
        "country": country,
        "query_preview": query_red,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "budget_target": 30_000,                      # 与 Spec §5.3 表格“整体感知预算”一致
        "exceeded": prompt_tokens > 30_000,
        "files": files or [],
    }
    out = Path("outputs/da_token_log.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
```

### Task 4.3 调用监控（不动 9 个核心 .py）
**Modify**: 仅在 `prompt_assembler.py` 末尾、`return prompt, tokens, files, total_hits` 之前调用一次：
```python
from data_acquisition_agent.knowledge_base.budget_monitor import log_token_usage
try:
    log_token_usage(
        query=request.natural_language_request,
        country=request.target_country.value,
        prompt_tokens=tokens,
        files=files,
    )
except Exception:
    # 监控不能阻塞 SQL 生成主流程；日志失败后仍返回 prompt。
    pass
return prompt, tokens, files, total_hits
```
> ⚠️ 字段名以 Phase 0 Task 0.1 实测的 `data_acquisition_agent/schemas.py` 为准——
> `GenerateRequest.natural_language_request: str` + `target_country: TargetCountry`（Enum，传 `.value` 得字符串）。
> 如果实测结果不同（例如用了 `query` / `country` 字段），按 Task 0.1 STOP 条件改完字段名再继续。
> 如果用户希望 budget_monitor 调用挂在 orchestrator 而非 assembler，请保持当前位置——orchestrator 在 9 核心 .py 名单中不能动。

### Task 4.4 跑 10 条 NL 样本对比 token（与 Phase 0 baseline 对照）
**手动步骤**：用以下 10 条 NL（5 条与 Phase 0 Task 0.3 完全一致 + 5 条新增覆盖 build_table_script / 跨表 join / eKYC 等场景）：

```
# 与 Phase 0 baseline 一致的 5 条
1. "查找最近 7 天活跃用户的 top 10"
2. "统计本月有逾期记录的用户数量"
3. "导出 30 天内首贷通过且 mob1 无逾期的用户清单"
4. "对比上周和本周的 eKYC 拦截率"
5. "构建一张近 90 天复借首贷客群的标签宽表"

# 新增 5 条（覆盖更多路由分支）
6. "活跃用户漏斗（注册→KYC→首借）每一步的转化率"
7. "渠道维度的成本回收周期"
8. "本周新增黑名单用户的渠道分布"
9. "查询最近 24 小时催收成功率"
10. "导出某 UID 的全部行为时间线"
```

**记录**：每条记 `prompt_tokens`，平均落 `.reports/plan-07-phase4-tokens.txt`。
**预期**：
- 平均 ≤ 30K（整体感知预算，包含 SYSTEM_PROMPT_ENGINE + 裁剪后 md + user_block + 余量；vs Phase 0 baseline ≈ 250K）
- 压缩比 ≥ 8×
- `outputs/da_token_log.jsonl` 有 10 行新增

> 口径说明（P8 遺留防跨偏）：`router md_only token_budget ≈ 24K` 是仅限 md 段的上限，不是 prompt_tokens。
> `prompt_tokens ≤ 30K` 是**整体感知预算**（= SYSTEM_PROMPT_ENGINE ~3K + always_inject + bm25 trim md ~17K + user_block ~2K + 余量）。
> 两者不冲突：`budget_monitor.budget_target = 30_000` 与本预期对齐，与 Spec §5.3 表格 «总输入（实测目标）» 口径一致。

### Task 4.5 检索召回率人工抽查（与 Task 4.4 同样 10 条）
**手动步骤**: 对每条 NL，人工评判 `route_knowledge(...)` 选中的 md 文件名是否合理（schema 题选中 schema.md 且不漏 system_prompt 等）。
**预期**: 10 条中至少 9 条选中合理（≥ 90% 召回）。
**记录**: 召回结果填入 `.reports/plan-07-phase4-recall.txt`。

### Task 4.6 兜底回退验证
```powershell
$env:USE_FULL_KNOWLEDGE_INJECTION="1"
python -m pytest data_acquisition_agent/tests/test_knowledge_base/test_router.py::test_full_fallback_via_env -v
$env:USE_FULL_KNOWLEDGE_INJECTION=""
```
**预期**: env=1 时 router 返回 manifest 5 个 md（绝不含 INDEX.md），test 通过。

### Task 4.7 全量回归（与 Phase 0 baseline 文件比对，机器化校验，不依赖 PowerShell 跨 session 变量）
```powershell
mkdir -Force .reports
python -m pytest data_acquisition_agent/tests/ -v 2>&1 | Tee-Object -FilePath .reports/plan-07-final-tests.txt | Select-String "passed|failed|error" | Select-Object -Last 5

# 读基线 + 当前文件最后一行 passed 计数对比
$baseline = (Get-Content .reports/plan-07-baseline-tests.txt | Select-String "passed" | Select-Object -Last 1).ToString()
$final    = (Get-Content .reports/plan-07-final-tests.txt    | Select-String "passed" | Select-Object -Last 1).ToString()
Write-Host "BASELINE: $baseline"
Write-Host "FINAL   : $final"

# 机器化解析（育 P2-14: 不依赖肉眼比对）
$bp_match = [regex]::Match($baseline, "(\d+)\s+passed")
$fp_match = [regex]::Match($final,    "(\d+)\s+passed")
if (-not $bp_match.Success) { throw "BASELINE 未能解析 'N passed': $baseline" }
if (-not $fp_match.Success) { throw "FINAL    未能解析 'N passed': $final" }
$bp = [int]$bp_match.Groups[1].Value
$fp = [int]$fp_match.Groups[1].Value
Write-Host "baseline_passed = $bp"
Write-Host "final_passed    = $fp"
if ($fp -lt $bp + 22) {
    throw "FAIL: regression detected. final_passed ($fp) < baseline_passed ($bp) + 22"
}
Write-Host "PASS: final_passed >= baseline_passed + 22"
```
**预期**:
- baseline 记录的原 163 case 全部仍然 passed（不允许少 1 个）
- 新增至少 22 case：BM25 9（V1 双国 build 2 + 5 独立 + 启动自检 2）+ Router 6 + Archiver 5 + Assembler safety 3 - 1 (V1 fail-soft 计入 BM25 9 内) = **9 + 6 + 5 + 3 - 1 = 22**（保守下限；实际新增数视具体测试粒度可达 23-25）
- 终态 `passed` 数 ≥ baseline `passed` 数 + 22（机器化 throw 强校验）

### Phase 4 commit（先 diff 后 commit）
```powershell
git status --short
git diff --stat HEAD
git diff -- data_acquisition_agent/prompt_assembler.py
# ⚠️ 用户审核 diff 后再执行下面块（重点确认 SYSTEM_PROMPT_ENGINE / user_block 6 大段未被误删，仅 5-md 循环段被替换）
# ⚠️ outputs/ 在 .gitignore 里，不进 commit；da_token_log.jsonl 是运行时产出，本地保留即可
git add `
  data_acquisition_agent/prompt_assembler.py `
  data_acquisition_agent/knowledge_base/budget_monitor.py `
  data_acquisition_agent/tests/test_knowledge_base/test_assembler_safety.py
# .reports/ 已在 Phase 0 commit 中加进 .gitignore，不会上身
git commit -m "feat(07): phase 4 assembler integration + budget monitor (redact+TOKEN_LIMIT preserved)"
```

### Task 4.8 [complete] commit + push
```powershell
git commit --allow-empty -m "[complete] plan-07 — knowledge base (INDEX+BM25+learned, redact+TOKEN_LIMIT preserved)"
git push origin main
```
**前置**：Phase 4 Task 4.7 全部绿；用户已显式确认推送，并已核对当前 remote 指向批准仓库。

---

## 五点检查法（自审）

| # | 检查项 | 状态 |
|---|---|---|
| 1 | 精确文件路径 | ✅ V1 双国 INDEX 用中文目录 (`墨西哥/INDEX.md` + `泰国/INDEX.md`) + local_dev / learned/{country}/v1/；测试根固定为 `data_acquisition_agent/tests/test_knowledge_base/` 与现有 164 tests 同根 |
| 2 | 无占位符 | ✅ V1 双国 INDEX.md 内容已按真实 5 个 md 文件名（含空格）逐国全量展开（无「以墨西哥为例 其余复用」省略式占位）；assemble_prompt 改造前后均给出完整代码；Plan 07 已降级，不再保留 ACK hook 占位符 |
| 3 | 完整代码块 | ✅ index_parser/router/bm25/archiver/budget_monitor/assembler/baseline_tokens 全部给出完整可粘贴代码 |
| 4 | 验证命令 + 预期输出 | ✅ Phase 0 baseline tokens 落 .reports/ + Phase 4 final tests 与 baseline 文件比对，所有 pytest 命令含预期 case 数（22 新增下限 + 163 baseline） |
| 5 | 一个不熟悉项目的人能独立执行完 | ✅ Phase 0 Task 0.1 校字段名 + Task 0.6 确认不接运行时 ACK hook 后，Task 3.2 / 4.0 / 4.1 / 4.3 不会再卡 |
| **v3 收敛** | **V1 范围：mx + th 双国** | ✅ 测试 / 脚本 parametrize 全量缩到 `V1_COUNTRIES = ["mexico","thailand"]`；3 国 (id/pk/ph) 仅留 `COUNTRY_DIR_MAP` 映射 + bm25_indexer fail-soft 兜底，未来填好 yaml + INDEX.md 即可自动接入 |

---

## 回滚预案

**触发**：Phase 4 验收发现 SQL 生成质量下降 > 10%，或 redact()/TOKEN_LIMIT 兜底测试任一失败。

**软回滚（首选）**：
```powershell
$env:USE_FULL_KNOWLEDGE_INJECTION="1"   # 强制全量注入，等价旧行为
# 排查 router 问题，修复后再清空 env var
```

**硬回滚（最后手段）**：
```powershell
git reset --hard {baseline_commit}   # baseline commit hash 来自 §0.4
```

---

## 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Phase 1 INDEX.md keywords 写得不准 | 中 | 高 | env var 兜底全量回退 |
| BM25 jieba 分词冷启动慢 + 字典 ~50MB 占用磁盘 | 低 | 低 | 单例缓存 + 部署镜像预下载字典 |
| Phase 3 archiver 运行时接入依赖 Plan 08 | 中 | 中 | Plan 07 降级：只实现 archiver 基础能力，不接 ACK hook；Plan 08 完成 SQLJudge 后再单独接入 |
| Phase 4 改造误删 redact()/TOKEN_LIMIT | 低 | 致命 | Task 4.0 测试已守护；改前/改后 grep 行数对照 |
| 中文目录在 Windows / Linux 兼容性 | 低 | 中 | 统一 UTF-8 编码 + Path/PosixPath；CI 矩阵覆盖两平台 |
| `analyst_private_prefix` 检查误伤合法 DDL | 低 | 中 | DDL 正则严格匹配；合法 prefix 写在 mexico.yaml 由人工 review |

---

## 测试矩阵

| 类别 | 范围 | 触发 | 用例数 |
|---|---|---|---|
| BM25 indexer + V1 启动自检 + non-V1 fail-soft | data_acquisition_agent/tests/test_knowledge_base/test_bm25_indexer.py | Phase 1/4 | 9 (V1 build 2 + 5 独立含 non_v1 fallback + V1 启动自检 2) |
| Router (INDEX + always_inject + 全量回退) | data_acquisition_agent/tests/test_knowledge_base/test_router.py | Phase 2/4 | 6 |
| Archiver (fail-safe + DDL 前缀) | data_acquisition_agent/tests/test_knowledge_base/test_archiver.py | Phase 3/4 | 5 |
| Assembler safety (redact + TOKEN_LIMIT + 4-tuple) | data_acquisition_agent/tests/test_knowledge_base/test_assembler_safety.py | Phase 4 | 3 |
| 全量回归 | data_acquisition_agent/tests/（163 baseline + 上面 22 新增下限） | Phase 4 | baseline 163 + 新增 ≥ 22 |
| Token 实测 (10 NL) | 手动 + outputs/da_token_log.jsonl | Phase 4 | 10 |
| 召回率人工评判 | 手动 10 NL | Phase 4 | 10 |

---

## TASK.md 记一行

```markdown
- [ ] Knowledge Base 子系统（V1 mx + th 双国，Token 250K→≤30K，redact + TOKEN_LIMIT 保留）→ docs/plans/07-knowledge-base-plan.md
```
