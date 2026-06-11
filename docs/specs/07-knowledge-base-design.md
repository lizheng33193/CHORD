# Design Doc 07 — Knowledge Base 子系统（INDEX 路由 + BM25 + learned/）

> **STATUS**: ✅ READY-FOR-PLAN — v3（**V1 范围收敛为 mx + th 双国**），与 [docs/plans/07-knowledge-base-plan.md](../plans/07-knowledge-base-plan.md) v3 对齐
>
> **v3 修订点**（对照 v2，2026-05-06 用户范围决策同步）：
> - **范围收敛**：「5 国独立索引」→「V1 mx + th 双国独立索引；其余 3 国（indonesia / pakistan / philippines）暂不在 V1 范围，仅留 `COUNTRY_DIR_MAP` 映射 + bm25 fail-soft 兜底作为未来扩展接口」
> - **few 文件名修正**：v2 §0.1 「`few.md`(本国化 few-shot；**不是** few-shot.md)」断言对 mx / th / pk 成立，但对 indonesia / philippines 错（实测两国是 `few-shot.md`）。v3 标注：mx + th + pk 三国是 `few.md`，id + ph 两国是 `few-shot.md`，未来扩展 id / ph 时 yaml `few_md` 字段需指向 `.../few-shot.md`（菲律宾 yaml 已正确，印尼 yaml 待补）。
> - **token budget 修正**：v2 §5.3 表格「整体感知预算」与 `budget_monitor.budget_target` 实测取 25K，但加上 SYSTEM_PROMPT_ENGINE (~3K) + 4 段 md (~5-8K) + user_block (~2K) + 余量后总 prompt ≥ 30K，导致 `exceeded` 永真。v3 把 budget_target 抬到 30K（router md_only budget 维持 ≈ TOKEN_LIMIT * 0.03 ≈ 24K，是不同口径）。
>
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05（v2） / 2026-05-06（v3 mx+th 双国收敛）
> **关联 Plan**: `docs/plans/07-knowledge-base-plan.md`（v3 同步）
> **依赖前置**: 无（独立执行；与 Plan 05 country_packs/ 完全解耦，V1 双国知识库 md 已就绪）
> **关联文档**:
> - Harness Engineering 学习笔记 §7 Knowledge 层（SKILL.md 两层注入思想）
> - Harness Engineering 学习笔记 §6 Context 层（Token 预算管理）
> - `data_acquisition_agent/prompt_assembler.py`（现有 manifest 驱动全量注入实现）
> - `data_acquisition_agent/manifest.py`（CountryManifest yaml loader，REQUIRED_MD 5 个 key）
> - `data_acquisition_agent/redactor.py`（凭据脱敏管线，必经）
> - `data_acquisition_agent/configs/{mexico,thailand}.yaml`（V1 双国生产 manifest）；`{indonesia,pakistan,philippines}.yaml` 仅作为未来扩展接口（indonesia 是空 placeholder）
> - `data_acquisition_agent/demo0/各国数据知识库汇总/{墨西哥,泰国}/`（V1 双国实际中文目录）

---

## 0. 背景与目标

### 0.1 现状（以 git HEAD `bd05240` + PowerShell 实地核查 2026-05-05 为准）

**目录现状**（实测 `Get-ChildItem 'data_acquisition_agent/demo0/各国数据知识库汇总/'`）：
- 5 国子目录使用**中文国名**：`巴铁/ 菲律宾/ 墨西哥/ 泰国/ 印尼/`（**不是**英文 `pakistan/philippines/mexico/thailand/indonesia/`）
- **V1 双国（墨西哥 / 泰国）md 实测 5 个文件，文件名一字不差**：
  - `多国业务逻辑.md`（业务黑话词典）
  - `all_examples .md`（**含 1 个空格**，跨国参考代码）
  - `scheme.md`（物理 schema 唯一权威源；**不是** schema.md）
  - `few.md`（本国化 few-shot —— **mx / th / pk 三国实测是 `few.md`**；id / ph 两国实测是 `few-shot.md`，未来扩展时 yaml `few_md` 需对应）
  - `gem prompt.md`（**含 1 个空格**，5 国全部都有）
- **3 国（印尼 / 巴铁 / 菲律宾）实测**：4 个 md 与 V1 双国同名，第 5 个 few 文件名按国家而异（pk 是 `few.md`，id / ph 是 `few-shot.md`）。本 Plan 07 v3 不创建这 3 国 INDEX.md，仅留 `COUNTRY_DIR_MAP` 映射作为未来扩展接口。
- **跨国共享**：`data_acquisition_agent/demo0/system_prompt.md`（5 国共用，不在国家子目录下）

**Manifest 现状**（`data_acquisition_agent/configs/`）：
- 6 个 yaml manifest：`indonesia.yaml / mexico.yaml / mexico.local.yaml / pakistan.yaml / philippines.yaml / thailand.yaml`
  - **V1 范围**：`mexico.yaml` / `thailand.yaml` 已填好生产路径 + 私有前缀 `dm_model.yyp_tmp_`，`load_manifest()` 必能成功加载
  - **未来扩展接口（V1 不验证）**：`indonesia.yaml` 是空 placeholder（`# 留位，V1 不验证`），`load_manifest("indonesia")` 必抛 `ManifestNotImplemented`；`pakistan.yaml` / `philippines.yaml` 已填但未列入 V1 测试矩阵
- 每个 yaml 通过 5 个 key 显式列出 md 路径：`business_logic_md / all_examples_md / schema_md / few_md / system_prompt_md`（其中目录名是中文）
- 1 个 `local_dev/` 子目录：含 `all_examples.md / business_logic.md / few.md / scheme.md` 4 个本地 mysql 用 md
- `mexico.local.yaml` 是 **opt-in**：仅当 `DA_LOCAL_DEV=1` env var 设置时才被 `manifest.py::load_manifest()` 优先加载；**默认 / CI / 生产走生产 yaml**（不走该 override）。本 Plan 跑 baseline / §3.3 archiver test / pytest 都不设该 env，拿到生产 prefix `dm_model.yyp_tmp_`。

**注入现状**（实测 `data_acquisition_agent/prompt_assembler.py`，函数体内位置感知；不写绝对行号避免回归脆弱）：
- 真实接口签名：`def assemble_prompt(request, manifest)` —— 入参是 `GenerateRequest` 对象 + `CountryManifest` 对象，**不是** `(query: str, country: str)`
- 真实返回值是 4-tuple：`return prompt, tokens, files, total_hits`（**不是**单 `str`）
- 真实组装逻辑：按 manifest 的 5 个 key 顺序读取（**不 glob 目录**），每个 md 都过 `red, hits = redact(raw)` 凭据脱敏，再 `f"# === {label} ===\n{red}"` 拼接
- 硬上限：`prompt_assembler.py` 顶部 `TOKEN_LIMIT = 800_000`，超限直接 `raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")`
- 单次 LLM 调用 prompt 长度 **≈ 250K tokens**（接近但低于 800K 硬上限）

**三个问题**：
  1. **成本高**：每次 SQL 生成都全量计费 250K tokens
  2. **延迟高**：250K tokens 输入会拖慢首 token 响应
  3. **注意力稀释**：Lost in the Middle 效应，长 prompt 中段信息被忽略

### 0.2 目标
- **单次 LLM 输入 token 从 250K → ≤ 30K（≥ 8× 压缩）**
- 检索召回率 ≥ 90%（人工抽查 V1 双国 10 条 NL，命中预期文档）
- **V1 双国（mexico / thailand，对应中文目录 墨西哥 / 泰国）独立索引，互不混叠**；其余 3 国（indonesia / pakistan / philippines）仅在 `COUNTRY_DIR_MAP` 留映射作为未来扩展接口，bm25_indexer 对其 fail-soft（manifest 加载失败 / INDEX.md 缺失 → 返回空索引，让 router 走全量回退分支）
- learned/ 归档基础能力（DataAcq 通过的 SQL 可沉淀为 few-shot，但 **Plan 07 不接运行时 ACK hook**；自动归档依赖后续 Plan 08 SQLJudge 真实结果 + 人工 ack；fail-safe default = `user_acked=False`）
- **凭据脱敏不绕过（Zero Tolerance 硬约束）**：现有 `redactor.redact()` 必须仍然在每个 md 拼接前调用，与现有 `prompt_assembler.py` 5-md 循环段中 `red, hits = redact(raw)` 行为完全等价
- **`TOKEN_LIMIT = 800_000` 硬上限保留**：改造后 `prompt_assembler.py` 必须保留函数末尾 `if tokens > TOKEN_LIMIT: raise ValueError("prompt_too_large: ...")`
- **`build_table_script` SQL 必须落在 `analyst_private_prefix` 内**：archiver 入库前若 SQL 含 `CREATE TABLE` 必须校验前缀（如 `dm_model.yyp_tmp_`），否则拒绝归档；`INSERT INTO` 不在 Plan 07 V1 归档检查范围内

### 0.3 设计依据：Harness §7 SKILL.md 两层注入

> "Layer 1（目录）放在 System Prompt，Layer 2（全文）按需加载——既不浪费 Context 也不遗漏知识。本质是'先看目录再翻书'。"

本 Plan 把这个思想落地到 DataAcquisitionAgent 的 5 个 md 文件检索上：
- **Layer 1**: INDEX.md 路由表（每个 md 文件一行 metadata，~100 tokens/项）
- **Layer 2**: BM25 关键词召回（INDEX 没命中时兜底）
- **Layer 3**（保底）：全量回退（前两层都失败时使用，env var 控制）

---

## 1. 范围与非目标

### 1.1 ✅ 范围内
| 项 | 说明 |
|---|---|
| INDEX.md 路由 | **V1 双国（mx + th）各一份** + local_dev 一份，列出每国 5+1 个 md（5 个国家私有 + 1 个跨国共享 system_prompt.md），元数据采用 `## {file} \n - **k**: v` 形式。3 国（id / pk / ph）未来扩展时按相同模板补即可。 |
| `COUNTRY_DIR_MAP` 桥接 | `{"mexico": "墨西哥", "thailand": "泰国", "indonesia": "印尼", "pakistan": "巴铁", "philippines": "菲律宾"}` —— **保留 5 国映射作为未来扩展接口**，V1 仅 mx + th 进 `V1_COUNTRIES` 测试 / 脚本 parametrize |
| BM25 检索 | 文件级粒度（先 file 后 chunk，简单优先），**索引源 = manifest 的 5 个 md key**（不 glob 目录）。非 V1 国 yaml 加载失败时 fail-soft（返回空索引），让 router 走全量回退分支。 |
| learned/ 归档基础能力 | `archive_example()` 提供 fail-safe 归档函数；Plan 07 只实现函数 + 单测，不接 ACK 运行时 hook；落地路径 `data_acquisition_agent/learned/{country}/v1/`（与 demo0 平行，不污染 configs/） |
| **`build_table_script` 私有前缀校验** | archiver 入库前 SQL 含 `CREATE TABLE` 必须以 `manifest.analyst_private_prefix` 开头，否则拒绝归档；`INSERT INTO` 不在 Plan 07 V1 归档检查范围内 |
| prompt_assembler 改造 | 仅修改 `prompt_assembler.py` 一个文件（动业务核心）→ 必须 163 tests 全绿才算 [complete] |
| Token 预算管理 | system / examples / schema / current_query 各 budget；保留 `TOKEN_LIMIT = 800_000` 硬上限；**`budget_monitor.budget_target = 30_000`**（整体感知预算）与 router md_only `token_budget = TOKEN_LIMIT * 0.03 ≈ 24K` 是不同口径 |
| 全量回退保底 | env var `USE_FULL_KNOWLEDGE_INJECTION=1` 强制走旧路径（与 mock 降级等价） |
| **凭据脱敏不绕过（Zero Tolerance）** | 路由后的每个 md 仍然走 `redactor.redact()`，与现有 `prompt_assembler.py` 5-md 循环段中 `redact(raw)` 行为完全等价；新增 `test_redactor_still_called_per_file` 单测兜底 |

### 1.2 ❌ 非目标
| 项 | 推迟到 | 理由 |
|---|---|---|
| Vector embedding | V3 / 文件数 > 300 触发 | 当前 ~10-20 个 md 文件，BM25 够用 |
| Chunk 切分 | V2 | 文件级粒度优先，复杂度可控 |
| Rerank | V2 | INDEX + BM25 双保险已满足 90% 召回率目标 |
| 跨国知识共享 | 不做 | 严格按国隔离，避免污染（**例外**：`system_prompt.md` 跨国共享但内容稳定） |
| 修改 `redactor.py / manifest.py / orchestrator.py / executor.py / output_scanner.py / output_writer.py / connection.py / api.py / schemas.py` 共 9 个核心 .py | 不做 | PLANNING.md Surgical Hard Boundary（仅允许改 `prompt_assembler.py` 一个文件） |
| 修改 `app/services/orchestrator_agent/` | 不做 | 与本 Plan 解耦 |
| 修改 `.agents/skills/` | 不做 | Codex 编辑器辅助技能，不参与运行时 |

---

## 2. INDEX.md 路由设计（Layer 1：目录）

### 2.1 文件结构（严格反映实际路径，PowerShell 实测 2026-05-05）

```
data_acquisition_agent/
├── configs/                          # YAML manifest（不动现有 yaml，仅在 local_dev/ 新增 INDEX）
│   ├── indonesia.yaml                # 5 国 yaml + local override（不动；indonesia.yaml 是空 placeholder）
│   ├── mexico.yaml                   # ✅ V1 范围：已填好生产路径
│   ├── mexico.local.yaml
│   ├── pakistan.yaml                 # ⏸️ 未来扩展接口（V1 不验证）
│   ├── philippines.yaml              # ⏸️ 未来扩展接口（V1 不验证）
│   ├── thailand.yaml                 # ✅ V1 范围：已填好生产路径
│   └── local_dev/                    # 本地 mysql 4 md（不动 4 个 md，仅补 INDEX）
│       ├── INDEX.md                  # ✨ 新增：Layer 1 路由
│       ├── all_examples.md           # 文件名无空格（与 demo0/ 不同）
│       ├── business_logic.md
│       ├── few.md
│       └── scheme.md
├── demo0/                            # 知识库 md（不动现有 md，仅在 V1 双国子目录补 INDEX）
│   ├── system_prompt.md              # ⭐ 跨国共享（5 国 yaml 都指向此文件）
│   ├── 基于大模型的用户画像与客群分层方案（墨西哥市场）.md     # 长文档，不参与路由
│   ├── 基于埋点数据的现金贷APP用户流失归因与留存分析SOP.md  # 长文档，不参与路由
│   └── 各国数据知识库汇总/
│       ├── 巴铁/                     # 中文目录名（V1 不创建 INDEX.md）
│       │   ├── 多国业务逻辑.md
│       │   ├── all_examples .md      # 文件名含 1 个空格，不动
│       │   ├── few.md                # 巴铁实测是 few.md
│       │   ├── gem prompt.md         # 文件名含 1 个空格，不动
│       │   └── scheme.md
│       ├── 菲律宾/                   # 同上 5 个 md（few-shot.md 而非 few.md），V1 不创建 INDEX.md
│       ├── 墨西哥/                   # ✅ V1 范围
│       │   ├── INDEX.md              # ✨ 新增：Layer 1 路由
│       │   ├── 多国业务逻辑.md
│       │   ├── all_examples .md
│       │   ├── few.md
│       │   ├── gem prompt.md
│       │   └── scheme.md
│       ├── 泰国/                     # ✅ V1 范围（与墨西哥同结构 + INDEX.md）
│       └── 印尼/                     # ⏸️ yaml 空 placeholder + few-shot.md（V1 不创建 INDEX.md）
├── learned/                          # ✨ 新增目录：归档的 NL→SQL 历史 case（Plan 07 不自动接 hook）
│   └── {country}/v1/example_*.md
└── knowledge_base/                   # ✨ 新增子模块（不算侵入 .py 锁定区）
    ├── __init__.py                   # COUNTRY_DIR_MAP（5 国保留）+ V1_COUNTRIES（mx + th）+ 公共导出
    ├── router.py                     # 三级路由（INDEX → BM25 → 全量回退）
    ├── bm25_indexer.py               # 文件级 BM25 索引（manifest 驱动；非 V1 国 fail-soft）
    ├── index_parser.py               # 解析 INDEX.md 元数据（中/英文逗号都支持）
    ├── archiver.py                   # learned/ 归档基础能力（fail-safe + 私有前缀校验）
    └── budget_monitor.py             # Token 用量监控（budget_target=30K）
```

> **桥接层**：`knowledge_base/__init__.py` 提供 `COUNTRY_DIR_MAP = {"mexico": "墨西哥", "thailand": "泰国", "indonesia": "印尼", "pakistan": "巴铁", "philippines": "菲律宾"}`。所有路径拼装统一通过此映射，避免硬编码中文目录在 router/parser/indexer 三处。

> **重要说明**：在 `data_acquisition_agent/` 内新建 `knowledge_base/` + `learned/` 子目录不算"修改 data_acquisition_agent/"违反事项（PLANNING.md Surgical Hard Boundary）——但 `prompt_assembler.py` 是原封不动 9 个核心 .py 之一，本 Plan **会修改** `prompt_assembler.py`，需明确：163 tests 全量重跑 + 新增 knowledge_base 单测全绿是 [complete] 进阶门槛。

> **INDEX.md 落点决策**：放在 `demo0/各国数据知识库汇总/{中文国名}/INDEX.md`（与 5 个 md 同级），不是 `configs/{english}/INDEX.md`（该路径不存在）。`configs/local_dev/INDEX.md` 例外（local_dev 是平铺目录）。

### 2.2 INDEX.md 格式（每国 6 entries，按真实文件名一字不差）

> 每个 entry 用 `## {filename}` 起头（filename 与磁盘上一字不差，含空格），下方 5-6 行 `- **key**: value`。
> `keywords` 字段同时支持中文逗号 `，` 和英文逗号 `,` 分隔（parser 用 `re.split(r"[,，]", ...)`）。
> `token_estimate` 字段在 Phase 1 收尾**必须**用 Plan 07 Phase 1 的 `plan_07_fill_index_token_estimate.py` 脚本按 `estimate_tokens()` 实测重写（V1 双国共 12 entry = 2 国 × 6 entry），不靠目测、不照抄。下方模板中的具体数字仅是占位，执行前不要手动填这些值。

**完整模板（以墨西哥为例，泰国 INDEX.md 结构相同，仅文件路径前缀替换为 `泰国/`）**：

```markdown
# Mexico Data Acquisition Knowledge Base — INDEX

> 本文件为 LLM 路由用，列出本目录下每个 md 文件的元数据。
> 路由优先级：always_inject > INDEX 关键词命中 > BM25 兜底 > 全量回退（env var）

---

## system_prompt.md
- **path**: data_acquisition_agent/demo0/system_prompt.md
- **title**: 跨国共享 system prompt（任务流程、JSON 输出契约、analyst_private_prefix 规则）
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
```

> **V1 INDEX.md 数量**：`{墨西哥, 泰国}` 各一份（**Plan 07 v3 仅创建这 2 份**），path 前缀替换为对应中文目录。3 国（巴铁 / 菲律宾 / 印尼）未来扩展时按相同模板补即可，注意印尼 / 菲律宾对应的 yaml `few_md` 字段需写 `.../few-shot.md`（不是 `few.md`）。
> **local_dev/INDEX.md** 不含 `gem prompt.md` 与 `多国业务逻辑.md`，仅 4 个：`scheme.md / business_logic.md / few.md / all_examples.md`（无空格）+ 跨国共享 `system_prompt.md`。

### 2.3 路由优先级算法（manifest 驱动 + always_inject 不被 trim）

```python
# data_acquisition_agent/knowledge_base/router.py
import os
from typing import Iterable
from data_acquisition_agent.knowledge_base.index_parser import parse_index_md, IndexEntry


def route_knowledge(query: str, country: str, token_budget: int = 15000) -> list[str]:
    """
    返回应该加载的 md 文件路径列表

    优先级（从高到低）：
    1. always_inject 标记的文件（无条件加载，trim 不会切掉）
    2. INDEX 关键词精确命中（用户 query 包含 keywords 中任意一个）
    3. BM25 兜底（前两步加起来召回 < 3 个文件时启用）
    4. 全量回退（env var USE_FULL_KNOWLEDGE_INJECTION=1 / 前三步全失败时）
    """
    if os.getenv("USE_FULL_KNOWLEDGE_INJECTION") == "1":
        return _full_inject_from_manifest(country)

    entries: list[IndexEntry] = parse_index_md(country)
    if not entries:
        return _full_inject_from_manifest(country)

    always_inject_files: list[str] = [e["file"] for e in entries if e["always_inject"]]
    selected: list[str] = list(always_inject_files)

    # Step 2: 关键词命中
    query_lower = query.lower()
    for e in entries:
        if e["file"] in selected:
            continue
        if any(kw.lower() in query_lower for kw in e["keywords"]):
            selected.append(e["file"])

    # Step 3: BM25 兜底
    if len(selected) < 3:
        from data_acquisition_agent.knowledge_base.bm25_indexer import get_indexer
        bm25_results = get_indexer(country).search(query, top_k=3)
        for path in bm25_results:
            if path not in selected:
                selected.append(path)

    if not selected:
        return _full_inject_from_manifest(country)

    # Step 4: token 预算 trim — always_inject 文件无条件保留
    return _trim_by_budget(selected, entries, always_inject_files, token_budget)


def _full_inject_from_manifest(country: str) -> list[str]:
    """全量回退 = 直接读 manifest 的 5 个 md key（与现有 prompt_assembler 等价）"""
    from data_acquisition_agent.manifest import load_manifest
    m = load_manifest(country)
    return [str(p) for p in (
        m.system_prompt_md, m.business_logic_md,
        m.all_examples_md, m.schema_md, m.few_md,
    )]


def _trim_by_budget(
    selected: list[str],
    entries: list[IndexEntry],
    always_inject_files: list[str],
    token_budget: int,
) -> list[str]:
    """优先保留 always_inject，剩余按预算 trim；超出 budget 时优先削 examples，schema 不能削"""
    estimate = {e["file"]: e["token_estimate"] for e in entries}
    # always_inject 无条件保留（即使超预算也保）
    result = list(always_inject_files)
    used = sum(estimate.get(p, 5000) for p in result)
    # 剩余按 selected 顺序填，超 budget 则停
    for path in selected:
        if path in result:
            continue
        est = estimate.get(path, 5000)
        if used + est <= token_budget:
            result.append(path)
            used += est
    return result
```

---

## 3. BM25 检索（Layer 2：全文兜底）

### 3.1 库选型

- **rank_bm25** （纯 Python，无外部依赖）
  - PyPI: `rank-bm25==0.2.2`
  - 优点：零依赖、5 分钟可集成
  - 缺点：纯 Python 性能一般，但 ~100 个文件级别足够（< 50ms / 次检索）

### 3.2 索引构建（manifest 驱动，不 glob 目录）

```python
# data_acquisition_agent/knowledge_base/bm25_indexer.py
from rank_bm25 import BM25Okapi
import jieba   # 中文分词；本 Plan Phase 0 新增到 requirements.txt
from pathlib import Path
from data_acquisition_agent.manifest import load_manifest


class BM25Indexer:
    """文件级 BM25 索引；索引源 = manifest 的 5 个 md key（不 glob 目录）"""

    def __init__(self, country: str):
        self.country = country
        self.doc_paths: list[str] = []
        self.bm25: BM25Okapi | None = None
        self._build()

    def _build(self):
        """启动时一次性建索引（manifest 驱动；冷启首次含 jieba 加载 ≤ 2s）"""
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
            tokens = list(jieba.cut(content))   # 中文分词
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
```

> **注意**：`country` 入参是英文 country code（与 `manifest.load_manifest()` 对齐），中文目录映射在 `manifest.py` 已隔离，BM25 索引器本身不需要 `COUNTRY_DIR_MAP`。

### 3.3 性能预算

| 操作 | 频率 | 预算 |
|---|---|---|
| 索引冷启首次构建（含 jieba 加载 ~50MB 字典） | 每个进程首个 country 1 次 | < 2s |
| 后续国家索引构建 | 每多一国 1 次 | < 200ms |
| 单次检索 | 每次 SQL 生成 | < 50ms |
| 索引内存占用 | 常驻 | < 10MB / 国 |

> **冷启策略**：`get_indexer()` 是 lazy 单例（首次调用才建），首次调用 `mexico` 阻塞 ≤ 2s（含 jieba 字典加载），后续国家 ≤ 200ms。

### 3.4 索引存储策略

- **V1**: 内存索引（每次进程启动重建）
  - 优点：实现简单，不需要文件管理
  - 缺点：进程重启慢一点（~500ms）
- **V2**（如有需要）: pickle 持久化到 `data_acquisition_agent/knowledge_base/cache/{country}_bm25.pkl`

> **决策**: V1 内存索引，遇到性能问题再升级。

---

## 4. learned/ 归档基础能力（CLAUDE.md artifact 安全 + 私有前缀校验）

> **Plan 07 降级决策**：本 Plan 只实现 `archive_example()` 与安全单测，不接入运行时 ACK hook。真实 ACK endpoint 只携带 `confirm / tool_call_id / decision`，拿不到归档需要的 `nl_query / generated_sql / country`；而可拿到上下文的 `agent_loop.py` ACK 通过分支还缺 Plan 08 SQLJudge 的真实 L1/L2 结果。自动归档接入留到 Plan 08 完成后单独执行，禁止在 Plan 07 里硬编码 `sql_judge_l1_pass=True` / `sql_judge_l2_pass=True`。

### 4.1 闭环流程

```
┌──────────────────────────────────────────────────────────┐
│ 1. 用户在 NL Chat 提问 "查找最近 7 天活跃用户的 top 10"  │
└──────────────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ 2. DataAcq 生成 SQL（artifact，不自动执行）              │
└──────────────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ 3. SQLJudge（Plan 08 后续）通过，产生真实 L1/L2 结果        │
└──────────────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ 4. 用户在前端 NL Chat 显式 ack（必须）                    │
│    fail-safe: archive 函数默认 user_acked=False           │
└──────────────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ 5. archive_example() 校验 build_table_script 的 SQL       │
│    必须以 manifest.analyst_private_prefix 开头才入库      │
└──────────────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ 6. 写入 data_acquisition_agent/learned/{country}/v1/       │
│    + 异步在 INDEX.md 的 [learned-archive] 段落追加 entry  │
└──────────────────────────────────────────────────────────┘
```

> **落地路径决策**：归档文件落到 `data_acquisition_agent/learned/{country}/v1/example_*.md`（与 demo0 平行的新顶层目录），**不落到** `configs/{country}/` 子目录（该目录不存在，且 configs/ 应保持纯 manifest）。Plan 07 仅提供手动/后续调用能力，不在运行时自动写入。

### 4.2 归档文件格式

```markdown
<!-- data_acquisition_agent/learned/mexico/v1/example_20260505_143022.md -->
---
nl_query: "查找最近 7 天活跃用户的 top 10"
generated_sql: |
  SELECT user_id, COUNT(*) as event_count
  FROM dwd_user_events
  WHERE event_date >= DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY)
  GROUP BY user_id
  ORDER BY event_count DESC
  LIMIT 10
sql_kind: query_only
keywords: [活跃用户, top, 最近 7 天, dwd_user_events]
sql_judge_l1_pass: true
sql_judge_l2_pass: true
user_acked_at: "2026-05-05T14:30:22"
execution_success: true
---

# Example: 最近 7 天活跃用户 top 10

## NL Query
查找最近 7 天活跃用户的 top 10

## Generated SQL
```sql
SELECT user_id, COUNT(*) as event_count
FROM dwd_user_events
WHERE event_date >= DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY)
GROUP BY user_id
ORDER BY event_count DESC
LIMIT 10
```
```

### 4.3 archive_example 函数签名（fail-safe default + 私有前缀校验）

> ⚠️ 签名与 Plan §3.1 实现严格一致：不接收 sql_kind 参数，内部用 `_ddl_target_starts_with()` + `_DDL_RE` 检测 CREATE TABLE；
>     仅在检测到 DDL 且 target 不以 `manifest.analyst_private_prefix` 开头时拒绝归档。这样调用方（前端 ack hook）不需预先判别 sql_kind，减少错位面。

```python
# data_acquisition_agent/knowledge_base/archiver.py
def archive_example(
    nl_query: str,
    generated_sql: str,
    country: str,
    sql_judge_l1_pass: bool = False,         # fail-safe: 默认 False
    sql_judge_l2_pass: bool = False,         # fail-safe: 默认 False
    user_acked: bool = False,                # fail-safe: 默认 False（CLAUDE.md artifact 安全）
    execution_success: Optional[bool] = None,
    keywords: Optional[list[str]] = None,
) -> Optional[str]:
    """归档一条 NL→SQL 成功 case；任何门槛未通过即拒绝归档。
    若 SQL 含 CREATE TABLE（由 _DDL_RE 检测），目标必须以 manifest.analyst_private_prefix 开头。
    """
    # 1. 三重门槛
    if not (sql_judge_l1_pass and sql_judge_l2_pass and user_acked):
        return None

    # 2. token 上限校验
    if (len(nl_query) + len(generated_sql)) // 3 > MAX_TOKENS_PER_EXAMPLE:
        return None

    # 3. build_table_script 私有前缀校验（CLAUDE.md SQL 安全）
    #    内部检测不依赖调用方传 sql_kind—如果 SQL 不是 DDL，_ddl_target_starts_with 返回 True 跳过本检查
    from data_acquisition_agent.manifest import load_manifest
    prefix = load_manifest(country).analyst_private_prefix  # 如 "dm_model.yyp_tmp_"
    if not _ddl_target_starts_with(generated_sql, prefix):
        return None  # 拒绝归档

    # 4. 写文件（落地 data_acquisition_agent/learned/{country}/v1/）
    ...
```

### 4.4 INDEX.md 更新（V2+，Plan 07 不落地运行时自动追加）

后续自动归档接入时，archiver 可在对应国家 INDEX.md 末尾追加一段；Plan 07 V1 不实现运行时异步追加，避免在 SQLJudge 结果尚未落地前污染索引：

```markdown
<!-- 自动追加段，由 archiver.py 维护，禁止手编 -->
## learned/{country}/v1/example_20260505_143022.md
- **path**: data_acquisition_agent/learned/{country}/v1/example_20260505_143022.md
- **title**: 最近 7 天活跃用户 top 10
- **keywords**: [活跃用户, top, 最近 7 天]
- **token_estimate**: 350
- **always_inject**: false
```

### 4.5 防膨胀策略

- learned/ 单文件 < 1000 tokens（超过则拒绝归档）
- 同 country 总归档数 > 200 → 触发清理（保留 100 条最近 + 100 条高频复用）
- INDEX.md 总长度 > 30K tokens → 触发主索引重建（V2 实现）

---

## 5. prompt_assembler 改造（Harness Context 层 + 凭据脱敏不绕过）

### 5.1 现状（实测 `data_acquisition_agent/prompt_assembler.py`，函数体内位置感知；不写绝对行号避免回归脆弱）

```python
# 现有真实接口（不是 (query: str, country: str)）
TOKEN_LIMIT = 800_000

def assemble_prompt(request, manifest):
    """request: GenerateRequest, manifest: CountryManifest. 返回 4-tuple"""
    sections = []
    files = []
    total_hits = 0
    for label, p in [
        ("system_prompt", manifest.system_prompt_md),
        ("business_logic", manifest.business_logic_md),
        ("all_examples", manifest.all_examples_md),
        ("schema", manifest.schema_md),
        ("few", manifest.few_md),
    ]:
        raw = p.read_text(encoding="utf-8")
        red, hits = redact(raw)                      # ⭐ 凭据脱敏，必经
        total_hits += hits                           # ⚠️ hits 是 int，累加用 += hits（不是 += len(hits)）
        sections.append(f"# === {label} ===\n{red}")
        if label == "system_prompt":
            sections.append(SYSTEM_PROMPT_ENGINE)
        files.append(str(p))
    # ⚠️ user_block 包含 6 大段（user_request metadata + 5-key JSON 契约 + Minimal skeleton +
    #    task_orientation 0-5 + analyst_private_prefix 强制规则 + json_format_rules 1-6）。
    #    位于原文件 5-md 循环段之后、`prompt = "\n\n".join(...)` 之前的 `user_block = ( ... )`
    #    整段，**本节仅示意首与尾**，Plan §4.1 改造后代码块拼贴完整 byte-identical 原文。
    user_block = (
        f"# === user_request ===\ncountry={request.target_country.value}\n"
        f"action={request.target_action.value if request.target_action else 'auto'}\n"
        f"request:\n{request.natural_language_request}\n\n"
        "Return ONLY a JSON object with EXACTLY these 5 top-level keys. ...(以下 5 key 契约 + Minimal skeleton + task_orientation 0-5 + analyst_private_prefix + json_format_rules §6 条 byte-identical 保留。完整原文见 Plan §4.1 改造后代码块)...\n"
        "6. Example of correctly escaped SQL: \"sql\": \"SELECT uid\\nFROM dwb.t\\nWHERE channel='MEX017'\\nLIMIT 100\""
    )
    sections.append(user_block)
    prompt = "\n\n".join(sections)
    tokens = estimate_tokens(prompt)
    if tokens > TOKEN_LIMIT:
        raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")  # ⚠️ 文案 byte-identical，不能改为 "prompt exceeds TOKEN_LIMIT"
    return prompt, tokens, files, total_hits
```

### 5.2 改造后（仍保留 redact 调用 + TOKEN_LIMIT 硬上限）

```python
# 改造后：仅替换 5 个 md 的“全量读取”为“router 路由后读取”，redact + TOKEN_LIMIT 不变
from pathlib import Path
from data_acquisition_agent.knowledge_base.router import route_knowledge


def _label_for_path(path_str: str, manifest) -> str:
    """路径 → manifest 语义 label，两侧 Path.resolve().as_posix() 规一化后反查。

    ⚠️ manifest 字段是绝对 Path（REPO_ROOT/<rel>）；router 返回的 path 可能是
       INDEX.md 里写的相对路径，也可能是 _full_inject_from_manifest 返回的绝对路径。
       不规一化（例如直接用 str(manifest.system_prompt_md) 作为 dict key）在 Windows 上会因
       反斜杠 vs 正斜杠、相对 vs 绝对、Path normalize 差异而不命中。
    """
    norm = Path(path_str).resolve().as_posix()
    label_attr = (
        ("system_prompt", "system_prompt_md"),
        ("business_logic", "business_logic_md"),
        ("all_examples", "all_examples_md"),
        ("schema", "schema_md"),
        ("few", "few_md"),
    )
    for label, attr in label_attr:
        if Path(getattr(manifest, attr)).resolve().as_posix() == norm:
            return label
    return "extra"  # learned/ 或 BM25 兑底命中的 md（V1 暂归 extra）


def assemble_prompt(request, manifest):
    """改造点：
    1. 不再硬编码 5 个 md key，改由 route_knowledge() 决定加载哪几个
    2. label 仍按 system_prompt / business_logic / all_examples / schema / few 五段拼装
    3. 每个 md 仍走 redact()，与改造前完全等价
    4. TOKEN_LIMIT 硬上限保留、`raise ValueError(f"prompt_too_large: ...")` 文案 byte-identical
    5. 4-tuple 返回 (prompt, tokens, files, total_hits) 不变
    """
    # 1. 路由（Layer 1: INDEX + Layer 2: BM25 + Layer 3: 全量回退）
    #    token_budget 口径统一为 int(TOKEN_LIMIT * 0.03) ≈ 24_000（仅 md 预算），
    #    与 Plan §4.1 改造后代码严格一致。Spec §5.3 中 30K 是 budget_monitor 的整体感知预算（含
    #    SYSTEM_PROMPT_ENGINE + 4 段 md + user_block + 余量），与这里 router md_only 24K 是不同口径。
    selected_files: list[str] = route_knowledge(
        query=request.natural_language_request,
        country=request.target_country.value,
        token_budget=int(TOKEN_LIMIT * 0.03),
    )

    sections = []
    files = []
    total_hits = 0

    # 2. router 选中的 path 进入循环；redact + label 拼接 + SYSTEM_PROMPT_ENGINE 位置全 byte-identical
    for path_str in selected_files:
        p = Path(path_str)
        if not p.exists():
            continue
        label = _label_for_path(path_str, manifest)
        raw = p.read_text(encoding="utf-8")
        red, hits = redact(raw)                       # ⭐ 凭据脱敏，与改造前等价；hits 是 int，+= hits
        total_hits += hits
        sections.append(f"# === {label} ===\n{red}")
        if label == "system_prompt":
            sections.append(SYSTEM_PROMPT_ENGINE)
        files.append(path_str)

    # 3. user_block 不变（6 大段 byte-identical 保留）— 以下为原文件 5-md 循环段之后的
    #    `user_block = ( ... )` 整段完整原文，Plan §4.1 改造后代码块中拼贴同一份，两份必须严格相同。
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

    # 4. TOKEN_LIMIT 硬上限不变（与现有函数末尾等价）、raise 文案 byte-identical
    if tokens > TOKEN_LIMIT:
        raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")

    # 5. 监控（新增，但不影响主流程）—与 Plan §4.3 参数一致：files=files、不传 response_tokens
    from data_acquisition_agent.knowledge_base.budget_monitor import log_token_usage
    log_token_usage(
        query=request.natural_language_request,
        country=request.target_country.value,
        prompt_tokens=tokens,
        files=files,
    )
    return prompt, tokens, files, total_hits
```

> **关键变更点（与改造前 diff）**：
> 1. ✅ 接口签名不变（仍 `(request, manifest)` + 4-tuple 返回）
> 2. ✅ `redact()` 调用对每个 md 仍执行（凭据脱敏不绕过 — Zero Tolerance）
> 3. ✅ `TOKEN_LIMIT = 800_000` 硬上限保留
> 4. ✅ user_block / SYSTEM_PROMPT_ENGINE / SYSTEM_PROMPT 都保留
> 5. ⚠️ 5 个 md 的 "全量逐个读" 改为 "route_knowledge() 选中后读"
> 6. ✨ 末尾新增 `log_token_usage()` 监控

### 5.3 Token 预算分配（`budget_monitor.budget_target=30_000` 整体感知预算 vs `int(TOKEN_LIMIT * 0.03) ≈ 24_000` md-only 预算）

> **v3 P8 修复**：v2 把整体预算定 25K，但加上 SYSTEM_PROMPT_ENGINE (~3K) + 4 段 md（按 always_inject 后裁剪 ~5-8K）+ user_block (~2K) + 余量后 prompt_tokens ≥ 30K，导致 `exceeded=prompt_tokens>25_000` 永真。v3 把 budget_target 抬到 30K，让 exceeded 真正反映"突破整体预算"事件。
>
> **预算口径区分（避免 30K 整体 vs 24K md-only 混淆）**：
> - `budget_monitor.budget_target = 30_000`：本节表格描述的**整体感知预算**，含 SYSTEM_PROMPT_ENGINE + INDEX 目录 + 4 段 md（always_inject 后裁剪）+ user_block + 生成余量。
> - `route_knowledge(token_budget=int(TOKEN_LIMIT * 0.03)) ≈ 24_000`：仅传给 router 用来 trim md 列表的**纯 md 预算**（不含 system / user_block），是不同口径。
> - 两数本质独立：router md_only 24K 用于 always_inject 之外的 extra md trim；budget_target 30K 用于事后整体预算监控。

| 段 | 预算 | 占比 | 备注 |
|---|---|---|---|
| SYSTEM_PROMPT_ENGINE + system_prompt.md（INDEX 目录 + 任务流程 + JSON 契约） | 5000 tokens | 17% | always_inject |
| Schema（scheme.md，always_inject） | 8500 tokens | 28% | 永远注入 |
| Few-shot（few.md，always_inject） | 12000 tokens | 40% | 永远注入 |
| 关键词命中或 BM25 召回的额外 md（all_examples / 业务逻辑等） | ≤ 2500 tokens | 8% | 受 router 的 md-only 预算 24K trim |
| user_block 6 大段 + Current user query | 2000 tokens | 7% | 任务上下文 |
| **总输入（实测目标）** | **≈ 30K tokens** | **100%** | budget_target 阈值 |
| 生成空间（output reservation，由调 LLM 时控制） | 2500 tokens | — | 不计入输入 |

> **整体预算 30K vs router md_only 24K 关系**：30K 是 budget_monitor 用来记录 prompt_tokens 是否破阈的整体口径；24K 是 router 用来 trim non-always_inject 的纯 md 子预算。两者不同源（router 不感知 system + user_block），刻意分离避免一处改动牵连另一处。超 30K 则 budget_monitor 记录 `exceeded=true` 供事后复盘，不会中断请求（中断仅发生于 §5.2 的 TOKEN_LIMIT=800K）。
>
> **硬约束**：超 30K 整体预算时优先削减 examples（`all_examples .md` / `gem prompt.md`），**`scheme.md` / `few.md` / `system_prompt.md` 永不削（always_inject=true）**。
>
> **TOKEN_LIMIT 兜底**：即便 router 出 bug 把所有文件都选上，最终 `tokens > 800K` 时仍会 raise，与改造前等价。

### 5.4 Token 用量监控

```python
# data_acquisition_agent/knowledge_base/budget_monitor.py
# ⚠️ Zero Tolerance：写入日志的 query_preview 必须先经 redact()，
#    防止 NL query 中可能携带的凭据 / token / phone 等回流到磁盘日志。
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
    """每次 SQL 生成后写日志，便于复盘。

    ⚠️ budget_target = 30_000 是 §5.3 定义的「整体感知预算」(v3 P8 修复，v2 取 25K 永真 exceeded)，
       prompt_tokens 含 SYSTEM_PROMPT_ENGINE + 4 段 md（always_inject 后裁剪）+ user_block + 余量。
       与 router 的 24K md-only 预算不同口径；这里超过 30K 即记录 exceeded，供事后压缩比复盘。
    """
    query_red, _hits = redact(query[:80])
    log_entry = {
        "ts": datetime.now().isoformat(),
        "country": country,
        "query_preview": query_red,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "budget_target": 30_000,
        "exceeded": prompt_tokens > 30_000,
        "files": files or [],
    }
    out = Path("outputs/da_token_log.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
```

---

## 6. 开放问题

### 6.1 BM25 索引存内存还是 pickle 持久化？
- 选项 A：内存（V1 简单，重启慢 ~2s 含 jieba 加载）
- 选项 B：pickle 到 cache/

> **推荐**: A（V1 内存），有性能问题再升级。

### 6.2 INDEX.md keywords 谁维护？
- 选项 A：人工维护（INDEX.md 手写）
- 选项 B：LLM 自动提取（每次更新 md 时 LLM 生成 keywords）
- 选项 C：人工 + 自动结合（人工写初始版本，learned/ 归档时 LLM 自动追加）

> **推荐**: C（结合）。Phase 1 人工写初始版，Phase 3 learned/ 闭环时自动追加。

### 6.3 learned/ 多少条触发自动重建主索引？
- 选项 A：固定阈值（如 50 条）
- 选项 B：定时任务（每周一次）
- 选项 C：手动触发

> **推荐**: A（50 条），自动化优先。

### 6.4 INDEX.md 与 yaml manifest 的同步关系？
- 选项 A：双单独维护，启动自检 INDEX 列出文件 ⊇ yaml 5 个 md（不一致 raise）
- 选项 B：INDEX.md 自动从 yaml 生成（人工只填 keywords/usage_hint）
- 选项 C：彻底放弃 INDEX.md，元数据合并进 yaml

> **推荐**: A（单独维护 + 启动自检）。yaml 是 manifest 唯一真相，INDEX 是路由元数据；二者职责分离但启动时强制校验包含关系。
> **实施落点（已下沉到 Plan）**: 校验由测试承担——见 [docs/plans/07-knowledge-base-plan.md](../plans/07-knowledge-base-plan.md) Phase 1 Task 1.5 中 `test_index_covers_manifest_5_md`（5 国 parametrize），任一国缺漏立即测试红，CI 阻断合入。运行时 `bm25_indexer._build()` 不再单独 assert（避免重复抛异常），统一由该测试守护。

---

## 7. 验收清单

### 7.1 Phase 0（baseline 核对）
- [ ] `data_acquisition_agent/prompt_assembler.py` 现有真实接口签名 `(request, manifest)` 已确认（不是 `(query, country)`）
- [ ] 当前 SQL 生成调用的 token 用量基线统计完成（跑 5 条样本 NL，记录平均值，预期 ≈ 250K）
- [ ] `rank-bm25==0.2.2` 加入 `requirements.txt`
- [ ] `jieba>=0.42.1` 加入 `requirements.txt`（实测当前不在）
- [ ] 已确认 Plan 07 不接运行时 ACK hook；自动归档接入依赖 Plan 08 SQLJudge 真实结果，后续单独执行

### 7.2 Phase 1-2（INDEX + BM25 + Router）
- [ ] `data_acquisition_agent/demo0/各国数据知识库汇总/{巴铁,菲律宾,墨西哥,泰国,印尼}/INDEX.md` 5 国各一份人工填写完成（每份 6 个 entry：system_prompt + 5 个国家私有 md）
- [ ] `data_acquisition_agent/configs/local_dev/INDEX.md` 人工填写完成（5 个 entry：system_prompt + 4 个 local md）
- [ ] `data_acquisition_agent/knowledge_base/__init__.py` `COUNTRY_DIR_MAP` 5 国映射就位
- [ ] `data_acquisition_agent/knowledge_base/bm25_indexer.py` 实现 + manifest 驱动 + unit test（含中文路径 + 含空格文件名断言）
- [ ] `data_acquisition_agent/knowledge_base/index_parser.py` 实现 + 中/英文逗号双解析 + unit test
- [ ] `data_acquisition_agent/knowledge_base/router.py` 实现 + always_inject 不被 trim + unit test
- [ ] 启动自检：INDEX.files ⊇ manifest 5 个 md path（开放问题 6.4 决策）

### 7.3 Phase 3（learned 归档基础能力）
- [ ] `data_acquisition_agent/knowledge_base/archiver.py` 实现 + fail-safe default (`user_acked=False`)
- [ ] archiver 内 build_table_script 私有前缀校验单测（`dm_model.yyp_tmp_` 开头 vs 不以此开头 两个 case）
- [ ] 不接入前端 NL Chat ack API，不修改 `app/api/` / `agent_loop.py`
- [ ] 手动调用 `archive_example(..., user_acked=True, sql_judge_l1_pass=True, sql_judge_l2_pass=True)` 确认 `data_acquisition_agent/learned/mexico/v1/` 下有归档文件；该手动验证不代表运行时自动归档已接入

### 7.4 Phase 4（assembler 接入 + 验收）
- [ ] `prompt_assembler.py` 改造接入 router；接口签名 `(request, manifest)` 不变
- [ ] `redact()` 调用对每个 md 仍然执行（新增 `test_redactor_still_called_per_file`）
- [ ] `TOKEN_LIMIT = 800_000` 硬上限保留（新增 `test_token_limit_still_raises`）
- [ ] 单次 LLM 输入 token：250K → 25K（用 budget_monitor 实测，跑同样 5 条 NL 对比）
- [ ] 检索召回率 > 90%（人工抽 10 条 NL，命中预期文档）
- [ ] 5 国独立索引不混叠（cross-test：`mexico` query 不返回 `tailand` 路径）
- [ ] env var `USE_FULL_KNOWLEDGE_INJECTION=1` 能强制走旧路径（兜底验证 + 测试）
- [ ] `data_acquisition_agent/tests/` 现有 163 tests 全绿（不允许减少）
- [ ] 新增 knowledge_base 单测全绿

---

## 8. 风险与回退预案

### 8.1 已知风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| BM25 召回不准导致 SQL 质量下降 | 中 | 高 | INDEX 关键词精确命中作为第一道防线；env var 兜底全量回退 |
| INDEX.md 关键词维护跟不上 md 更新 | 中 | 中 | learned/ 归档闭环自动追加 keywords；定期人工巡检 |
| jieba 中文分词对 SQL 关键词分词不准 | 低 | 低 | BM25 是兜底，INDEX 命中优先 |
| Token 预算分配不合理导致 examples 不够 | 中 | 中 | budget_monitor 日志监控，超预算告警 |

### 8.2 回退预案

**触发条件**: Phase 4 验收发现 SQL 生成质量下降 > 10%

**回退步骤**:
1. 设置环境变量 `USE_FULL_KNOWLEDGE_INJECTION=1`，立即恢复全量注入
2. 排查是 INDEX 路由问题还是 BM25 召回问题（看 budget_monitor 日志）
3. 修复后再切回路由模式

---

## 9. 参考文档

- Harness Engineering 学习笔记 §7 Knowledge 层（SKILL.md 两层注入）
- Harness Engineering 学习笔记 §6 Context 层（4 级压缩，本 Plan 是 Level 1 思想的应用）
- `RAG面试题学习笔记.md` Q14（检索优化四层框架）
- `data_acquisition_agent/prompt_assembler.py` 现有实现
