# Plan 05: th risk-feature country pack 落地（A1 双模式 + 路径 Q 完整 v6.1）

> **STATUS**: ✅ **READY-TO-EXECUTE·v6.1 — Claude Code 插件可直接执行（已对齐实际代码）**
>
> **Phase 结构**：5 个 Phase（Phase 0 / 1 / 2 / 3 / 4）。Phase 0 只读不 commit；Phase 1、2、3、4 各 1 个 commit，共 4 个实施 commit（遵「每 Plan ≤4 commit」写作教训）。
>
> **关联 Spec**: `docs/specs/05-country-pack-design.md`（v6.1 LOCKED：路径 A1 + 路径 Q）
>
> **日期**: 2026-05-05（v1）/ … / 2026-05-07（v6 A1 双模式）/ 2026-05-07（v6.1 路径 Q + 5 CRITICAL + 5 MAJOR + 3 MINOR 全量代码对齐修订）

---

## v6.1 与 v6 关键差异（修订点全清单 — 共 13 处）

> 本表是 Claude Code 执行时必须 ⚠️ 关注的所有改动。每处差异在下文 Phase 章节内有完整代码块。

### CRITICAL（5 处 — 不修则上线必崩）

| # | v6 问题 | v6.1 修订 | 触达 Phase / Task |
|---|---|---|---|
| **C1** | Skill 透传仅 3 个（app/behavior/credit），漏 comprehensive / product_advice / ops_advice | 透传扩到 **6 个 Skill 全覆盖**；orchestrator `_analyze_comprehensive_module` / `_analyze_advisory_module` 调 skill.analyze 时透传 country_code | Phase 3 Task 3.5.3 / 3.6 |
| **C2** | cache key 升级仅给三个方法签名，未列调用点 | 列出 5 处 `_get_cached` / `_set_cached` 调用点全清单（含 `_analyze_comprehensive_module` 内 ×3 + `_analyze_advisory_module` 内 ×2） | Phase 3 Task 3.5.4 |
| **C3** | explainer 用伪代码 `_read_template()`（不存在），feature_builder 双模式没说怎么和 mx CreditPreparedRecord schema 共存 | **路径 Q**：CreditRawData 加 `risk_features_record: dict \| None` 字段；CreditExplainer.__init__ 接受 `prompt_paths: dict[str, Path]` 双模板字典；build_credit_run_context 新增 `profile_mode` 键；feature_builder 按 context["profile_mode"] 二分支（mx 行为零变更，th 走 _build_risk_features 新分支） | Phase 3 Task 3.6.5 |
| **C4** | "3 Skill 同构"注释带过，会引导 behavior/credit 强加 application_time 破坏 mx 契约 | 拆 3 段独立 patch，每段精确对应一个 Skill（App 已传 application_time / Behavior + Credit 仅加 country_code） | Phase 3 Task 3.6 |
| **C5** | schemas/request.py 用 `Literal[...]` 但没说补 import | 完整 import diff + 字段 diff 两段 patch | Phase 3 Task 3.1 |

### MAJOR（5 处 — 不修则 Claude Code 执行时多次卡顿求确认）

| # | v6 问题 | v6.1 修订 | 触达 |
|---|---|---|---|
| **M1** | `analyze_stream.py` 改动只用文字描述 | 给 `_run_analysis_in_thread` 完整 4 形参签名 + 调用更新 patch | Phase 3 Task 3.3 |
| **M2** | `batch_service.analyze_uids(self, uids)` 同样调 orchestrator.analyze 但未决策 | 加 `country_code: str = "mx"` 第 2 形参（默认 mx，文件批量上传场景兜底） | Phase 3 Task 3.4 |
| **M3** | 前端 `loadModuleForUid` 行号锚点缺失 | 锚定 `app/static/js/app.jsx` Line 212；`analyzeModule()` 调用 Line 228 / 251 / 255 / 258 / 259 / 296（共 6 处） | Phase 3 Task 3.10 |
| **M4** | `analyzeByFile` 文件模式未决策 | 收敛单方案：FormData append country + `analyze_users_from_file` 加 `country: Literal["mx","th"] = Form("mx")` | Phase 3 Task 3.9 |
| **M5** | hard-gate Python 多行 -c 跨平台风险 | 抽出 `scripts/v6_hard_gate.py` 独立脚本 | Phase 4 Task 4.4 |

### MINOR（3 处 — 执行体验/精度优化）

| # | v6 问题 | v6.1 修订 | 触达 |
|---|---|---|---|
| **m1** | Phase 2 `git add app/country_packs/th/` 太宽 | 精确列 4 个 th 文件 + 3 个 root registry + 1 个 mx credit | Phase 2 commit 行 |
| **m2** | Phase 0 NCB gate 范围（docs/）vs Phase 4 NCB gate 范围（app/country_packs/th/）混淆 | 在两处 gate 标题前加 「检查范围 = X」 注释 | Phase 0 Task 0.5 / Phase 4 Task 4.4 |
| **m3** | 新增 `tests/country_packs/__init__.py` 没说为啥 | 加注释「pytest collection 需要包形式，否则 module 路径冲突」 | Phase 2 Task 2.6 |

---

## 0. Baseline 共识（v6.1 修订点已并入）

- **核心策略**：复用 `app/country_packs/{app,behavior,credit}_profile.py` 中已存在的 `_X_COUNTRY_PACKS` 注册表 + `load_X_country_pack` 工厂 + mx fallback。
- **mx 现状（已 grep 验证）**：3 个 dataclass 单例已存在，业务字段已上线值。
  - `CreditCountryPack` 当前 9 字段（`country_code/display_name/default_language/report_language/prompt_language/currency_code/source_display_name/score_band_thresholds/account_type_labels`）
  - `MX_CREDIT_COUNTRY_PACK` 字面量值：score_band `(("A",700),("B",580),("C",460),("D",0))` + 8 项 account_type_labels
  - `BehaviorCountryPack` 12 字段；`AppCountryPack` 5 字段
  - `build_X_run_context(country_code: str | None = None)` **已支持** country_code 参数（contracts.py 中 fallback 到 settings.default_country_code）
- **th 任务**（v6.1 修订）：
  1. **扩展 `CreditCountryPack` dataclass**（mx 文件，加 3 字段，向后兼容）
  2. **扩展 `CreditRawData` TypedDict**（路径 Q：加 `risk_features_record` 字段）
  3. 创建 3 个对应 dataclass 单例（th_app / th_behavior / th_credit）
  4. 注册表各加 1 行
  5. **改造 CreditExplainer 构造函数**（双 prompt_path 字典） + 新建 th 专用 prompt 模板
  6. **改造 CreditFeatureBuilder.build**（按 context["profile_mode"] 分支） + th data_access 新分支
- **Skill 类保持 country-agnostic（不新增 Thailand 子类）**：6 个 Skill（app/behavior/credit/comprehensive/product_advice/ops_advice）的 `analyze(uid, **kwargs)` 全部从 `kwargs.get("country_code")` 读出后传给 `build_X_run_context(country_code=...)`。
- **后端模块缓存必须加 country 维度**：`_module_cache` 现为 `(uid, module, application_time)` 3 元组 key，需加 `country_code` 为 4 元组（v6.1 已列出 5 处调用点）。
- **Hard Boundary**：不动 `data_acquisition_agent/`（11 个 .py 文件锁定）。
- **Plan 03 不阻塞**：Maestro Spike Pending 不影响 v6.1。
- **mx 字段集 = 上线基线**：dataclass 类型扩展 3 字段（向后兼容），mx 实例字面量 0 改动。
- **v6.1 上线 hard-gate**：禁止 NCB / DEV-PLACEHOLDER 残留 + profile_mode 运行时断言 + risk_features_record 双模式断言。

---

## 1. 范围

### In Scope（v6.1 修订）
- ✅ 扩展 `app/country_packs/mx/credit_profile.py::CreditCountryPack` dataclass 加 3 字段
- ✅ **NEW（C3 路径 Q）**：扩展 `app/runtime_skills/credit_profile/contracts.py::CreditRawData` TypedDict 加 `risk_features_record` 字段
- ✅ **NEW（C3 路径 Q）**：扩展 `build_credit_run_context` 返回 dict 加 `profile_mode` 键
- ✅ 创建 `app/country_packs/th/{app,credit}_profile.py`（新建） + 扩展 `behavior_profile.py`
- ✅ 修改 3 个根级注册表各加 1 行
- ✅ 扩展 `app/country_packs/th/__init__.py` 导出
- ✅ 后端 schema：`AnalyzeRequest.country: Literal["mx", "th"] = "mx"` + import Literal（C5）
- ✅ 后端路由：`/api/analyze` `/api/analyze-module` `/api/analyze-stream` `/api/analyze-file` 4 个全部透传 country
- ✅ Orchestrator 全链路透传 + cache key 4 元组（5 处调用点全改 — C2）
- ✅ **6 个 Skill** `analyze()` 全部透传 country_code（C1）
- ✅ **CreditExplainer 改造**：`__init__(model_client, prompt_paths: dict[str, Path])` + `explain()` 内按 `context["profile_mode"]` 选模板（C3）
- ✅ **CreditFeatureBuilder 改造**：`build()` 内按 `context["profile_mode"]` 分支；mx 走原 `_build_buro_features`（行为零变更，仅函数名重命名），th 走新 `_build_risk_features`（C3）
- ✅ **CreditDataProvider.fetch 改造**：按 `context["profile_mode"]` 分支构造 risk_features_record（C3）
- ✅ 新建 `app/prompts/credit_profile_th_prompt.md`（5 段结构）
- ✅ 前端顶层 country state + URL 持久化 + `resetAnalysisStateForCountry()`
- ✅ Header dropdown + 切换二次确认 modal
- ✅ `analyzeModule(uid, module, applicationTime, country)` 多 1 形参 + 6 处调用点全改（M3）
- ✅ `analyzeByUid` / `analyzeByUidStream` body 加 country；`analyzeByFile` FormData 加 country（M4）
- ✅ 单元测试：`tests/country_packs/test_th_country_packs.py` + `tests/test_orchestrator_country_cache.py` + `tests/runtime_skills/test_credit_profile_mode_branching.py`
- ✅ mx 全量回归（每 Phase 跑）
- ✅ Phase 4 修正 `PLANNING.md` 第 341 行国别白名单 + profile_mode 流程说明
- ✅ **Phase 4 v6.1 hard-gate**：抽 `scripts/v6_hard_gate.py` 独立脚本（M5），禁止 NCB / DEV-PLACEHOLDER + profile_mode 运行时断言 + risk_features_record 类型断言

### Out of Scope
- ❌ `BaseCountryPack` 抽象（v3 已废）
- ❌ `TargetCountry` enum / `get_country_pack` 工厂（v3 已废）
- ❌ Schema Adapter 类层级（v3 已废）
- ❌ `data_acquisition_agent/` 任何修改（Surgical Hard Boundary）
- ❌ Maestro 路由切换（Plan 03 Spike Pending）
- ❌ id / pk / ph / co / pe / cl / br 国家落地（V2+）
- ❌ Skill 类 country 子类化（country-agnostic 已成立）
- ❌ TH 风控授信结论 / KPI 数值化打分（V2+，本 V1 仅做 markdown 报告）
- ❌ 为 TH 生成虚拟 FICO / 虚拟 account_type（v5 失败教训）
- ❌ TH 数据接入 LocalRepository 的真实 csv 解析逻辑（Phase 2-3 用空 risk_features_record 占位 + mock；真实 csv 接入归 Phase 5+ / 后续 plan）

---

## 2. 字段矩阵指针

> 所有业务字段值的唯一权威来源：`docs/specs/05-country-pack-design.md` v6.1
> - §2.1（App 5 字段）/ §2.2（Behavior 12 字段）/ §2.3（Credit 12 字段）
> - §2.4（不一致字段适配方案）
> - §2.5（TH risk_feature_labels 11 项）/ §2.6（TH sentinel_values 3 项）
> - §2.7（v6.1 hard-gate）
> - §3.5（profile_mode 分支策略 — v6.1 实现细化）
> - §6.4 + §6.4.1（落点 4 + 路径 Q CreditRawData 扩展）
>
> Phase 2-3 所有代码块严格按 Spec v6.1 §2 / §3.5 / §6.4 填值。

---

## Phase 0 — 只读核对（不写代码 / 不 commit）

### Task 0.1：Git baseline 标记

```powershell
cd c:\Users\v-yimingliu\agent-userprofile\MAPS-LZ
git status --short
git log -1 --oneline
git diff HEAD --stat
```

**STOP**：工作区必须干净。否则先 commit 一个 baseline commit（建议 message：`[baseline] plan-05-v6.1-start`）。

### Task 0.2：mx 全量回归 baseline

```powershell
python -m pytest tests/ -v --tb=short -x
```

**STOP**：必须全绿。**记录通过数 N₀ 到附录 A**。

### Task 0.3：核对 Legacy 注册表 + mx CreditCountryPack 字段数

```powershell
Get-Content app/country_packs/app_profile.py | Select-Object -First 30
Get-Content app/country_packs/behavior_profile.py | Select-Object -First 30
Get-Content app/country_packs/credit_profile.py | Select-Object -First 30
Write-Host "---mx CreditCountryPack 当前字段---"
Get-Content app/country_packs/mx/credit_profile.py
Write-Host "---CreditRawData 当前 TypedDict---"
Select-String -Path app/runtime_skills/credit_profile/contracts.py -Pattern "class CreditRawData" -Context 0,12
```

**预期**：
- mx CreditCountryPack 当前 **9 字段**（v6.1 Phase 2 Task 2.0 扩展为 12）
- CreditRawData 当前 **6 字段**（uid/country_code/source_meta/prepared_record/data_status/errors，v6.1 Phase 3 Task 3.6.5 扩展为 7：+ risk_features_record）

### Task 0.4：核对 th 子目录现状

```powershell
Get-ChildItem app/country_packs/th/
Get-Content app/country_packs/th/__init__.py
Get-Content app/country_packs/th/behavior_profile.py | Select-Object -First 20
```

**预期**：
- th `__init__.py`：空
- th `behavior_profile.py`：仅含 4 常量 + docstring（不存在 TH_BEHAVIOR_COUNTRY_PACK）
- 不存在 th `app_profile.py` / `credit_profile.py`

### Task 0.5：核对 v6.1 Spec 已 LOCKED + 主文档无 NCB 残留

> **检查范围 = `docs/specs/`**（与 Phase 4 Gate 1 范围 `app/country_packs/th/` 不同）

```powershell
Select-String -Path docs/specs/05-country-pack-design.md -Pattern "STATUS:.*LOCKED.*v6.1"
$ncb_hits = Select-String -Path docs/specs/05-country-pack-design.md -Pattern "National Credit Bureau" -SimpleMatch
$count = ($ncb_hits | Measure-Object).Count
Write-Host "NCB 残留行数: $count （v5→v6 差异表 + 决策记录章节合理上限 ≤ 5）"
if ($count -gt 5) {
    $ncb_hits | Format-Table Path,LineNumber,Line
    Write-Host "❌ 主文档 NCB 残留过多，请检查是否误删 v5→v6 差异表叙述"
}
Select-String -Path docs/specs/05-country-pack-design.md -Pattern "profile_mode|risk_features_record" | Measure-Object -Line
```

### Task 0.6：核对 PLANNING.md 国别白名单冲突

```powershell
Select-String -Path PLANNING.md -Pattern "国别白名单"
Get-ChildItem app/country_packs/ -Directory
```

**预期冲突**：PLANNING.md 第 341 行写 6 国，实际目录 `mx/` `th/` 2 国 → Phase 4 Task 4.3 修复。

### Task 0.7：核对 6 个 Skill 当前 build_X_run_context 调用点

```powershell
Write-Host "--- App / Behavior / Credit Skill 当前调用 ---"
Select-String -Path app/runtime_skills/app_profile_agent.py,app/runtime_skills/behavior_profile_agent.py,app/runtime_skills/credit_profile_agent.py -Pattern "build_.*_run_context" -Context 0,8
Write-Host "--- Comprehensive / Product / Ops Skill 当前调用 ---"
Select-String -Path app/runtime_skills/comprehensive_agent.py,app/runtime_skills/product_advice_agent.py,app/runtime_skills/ops_advice_agent.py -Pattern "build_.*_run_context" -Context 0,4
```

**预期**：6 个 Skill 当前**都没有**传 country_code（comprehensive/product/ops 三者甚至没有 application_time），Phase 3 Task 3.6 修补。

### Task 0.8：核对 orchestrator cache key 调用点

```powershell
Select-String -Path app/services/orchestrator.py -Pattern "_get_cached|_set_cached|_cache_key" -Context 0,1
```

**预期**：列出 5 处调用点（Plan v6.1 Task 3.5.4 表格已锚定）。

### Phase 0 出口

- [ ] 工作区干净
- [ ] mx baseline N₀ 已记录到附录 A
- [ ] mx CreditCountryPack 9 字段确认；CreditRawData 6 字段确认
- [ ] th 子目录现状一致
- [ ] Spec v6.1 STATUS LOCKED 验证通过
- [ ] PLANNING.md 冲突已记录（推迟 Phase 4 修复）
- [ ] 6 个 Skill 当前 build_X_run_context 调用现状已确认
- [ ] orchestrator 5 处缓存调用点已确认

---

## Phase 1 — 风控特征字段矩阵 + 路径 Q contracts 扩展确认（不写代码）

### Task 1.1：核对 Spec v6.1 已就绪

```powershell
Select-String -Path docs/specs/05-country-pack-design.md -Pattern "STATUS:.*LOCKED.*v6.1"
Select-String -Path docs/specs/05-country-pack-design.md -Pattern "risk_features_record|profile_mode" | Measure-Object -Line
```

**预期**：第一条命中 1 行；第二条 ≥ 35 行（v6.1 多处提及）。

### Task 1.2：用户审核 v6.1 双模式 + 路径 Q 假设（echo 报告 + 等用户确认）

报告模板（Claude Code 执行时 echo 到对话）：

```
=== Spec 05 v6.1 审核报告（双模式 + 路径 Q）===

1. CreditCountryPack dataclass 扩展（v6 已确认）
   profile_mode: Literal["buro", "risk_features"] = "buro"
   risk_feature_labels: dict[str, str] = field(default_factory=dict)
   sentinel_values: dict[str, tuple[str, ...]] = field(default_factory=dict)

2. CreditRawData TypedDict 扩展（v6.1 路径 Q 新增）
   risk_features_record: dict[str, Any] | None  # mx 永 None；th 填 11 维原始 dict

3. build_credit_run_context 扩展（v6.1 路径 Q 新增）
   返回 dict 新增 profile_mode 键，值 = pack.profile_mode

4. CreditExplainer 构造改造（v6.1 路径 Q 新增）
   __init__(model_client, prompt_paths: dict[str, Path])  # 不再是单一 prompt_path
   explain() 内按 context["profile_mode"] 选模板：
     "buro" → prompt_paths["buro"] = credit_profile_prompt.md
     "risk_features" → prompt_paths["risk_features"] = credit_profile_th_prompt.md

5. CreditFeatureBuilder.build 改造（v6.1 路径 Q 新增）
   if context.get("profile_mode") == "risk_features":
       return self._build_risk_features(raw_data, context)
   return self._build_buro_features(raw_data, context)  # 现有逻辑函数重命名

6. CreditDataProvider.fetch 改造（v6.1 路径 Q 新增）
   if context.get("profile_mode") == "risk_features":
       构造 risk_features_record dict（mock 或读 csv，保留 sentinel 字符串）
       prepared_record = build_empty_prepared_record(uid, country_code="th")  # 占位
   else:
       走现有 mx Buró 逻辑，risk_features_record = None

7. Skill 透传扩到 6 个（v6.1 C1 修正）
   app / behavior / credit / comprehensive / product_advice / ops_advice

8. v6.1 hard-gate（独立脚本 scripts/v6_hard_gate.py — M5 修正）
   Gate 1: 禁止 NCB / DEV-PLACEHOLDER 残留（范围 = app/country_packs/th/）
   Gate 2: profile_mode + 空字段 + risk_features_record 类型 6 点断言
   Gate 3: th prompt 模板 5 段结构验证
```

**STOP**：用户必须明示「v6.1 假设通过」才进 Phase 2。

### Phase 1 commit

```powershell
git commit --allow-empty -m "[plan-05][P1] Spec v6.1 双模式 + 路径 Q contracts 扩展审核通过"
```

---

## Phase 2 — th country pack 落地（仅 country pack 层 — 不动 Skill / contracts）

> ⚠️ **mx-touched**：Task 2.0 修改 mx 文件 + Task 2.4 改 3 个根 registry → commit 含 `[mx-touched]`。

### Task 2.0：扩展 `CreditCountryPack` dataclass（mx 文件，加 3 字段）

完整目标文件 `app/country_packs/mx/credit_profile.py`（覆盖式写入）：

```python
"""Mexico Credit Profile country pack (shared dataclass type).

v6: 引入 profile_mode 双模式 dataclass：
  - "buro": MX 信用局原始报告解读（FICO 评分 + 账户列表，本文件 mx 实例）
  - "risk_features": TH 风控特征聚合解读（11 维特征 + 哨兵值，详见 th/credit_profile.py）

新增字段（向后兼容 mx 现有实例）：
  - profile_mode: Literal["buro", "risk_features"] = "buro"
  - risk_feature_labels: dict[str, str] = field(default_factory=dict)
  - sentinel_values: dict[str, tuple[str, ...]] = field(default_factory=dict)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CreditCountryPack:
    """Static country configuration used by the Credit profile pipeline."""

    country_code: str
    display_name: str
    default_language: str
    report_language: str
    prompt_language: str
    currency_code: str
    source_display_name: str
    score_band_thresholds: tuple[tuple[str, int], ...]
    account_type_labels: dict[str, str] = field(default_factory=dict)
    profile_mode: Literal["buro", "risk_features"] = "buro"
    risk_feature_labels: dict[str, str] = field(default_factory=dict)
    sentinel_values: dict[str, tuple[str, ...]] = field(default_factory=dict)


MX_CREDIT_COUNTRY_PACK = CreditCountryPack(
    country_code="mx",
    display_name="墨西哥",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
    currency_code="MXN",
    source_display_name="Buró de Crédito（墨西哥）",
    score_band_thresholds=(
        ("A", 700),
        ("B", 580),
        ("C", 460),
        ("D", 0),
    ),
    account_type_labels={
        "CC": "信用卡",
        "TC": "信用卡",
        "TDC": "信用卡",
        "F": "零售信贷",
        "M": "个人贷款",
        "PL": "个人贷款",
        "AUTO": "车贷",
        "HOME": "房贷",
    },
)
```

> mx 实例字面量**字符级别 0 改动**，新 3 字段使用 dataclass 默认值。

### Task 2.1：创建 `app/country_packs/th/app_profile.py`（新建）

```python
"""Thailand App Profile country pack."""

from __future__ import annotations

from app.country_packs.mx.app_profile import AppCountryPack

TH_APP_COUNTRY_PACK = AppCountryPack(
    country_code="th",
    display_name="Thailand",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
)
```

### Task 2.2：创建 `app/country_packs/th/credit_profile.py`（新建 — v6.1 risk_features 模式）

```python
"""Thailand Credit Profile country pack — risk_features 模式。

v6 业务模型重定向：
- TH credit 数据是公司风控特征聚合表（11 维特征 + 哨兵字符串），
  不是 NCB 信用局报告，不存在评分模型，不存在账户类型。
- profile_mode = "risk_features" 显式声明业务模型，
  下游 explainer / feature_builder / decision_engine 据此分支。

业务值来源: docs/specs/05-country-pack-design.md v6.1 §2.3 / §2.5 / §2.6
csv 数据来源: New data/thai72/credit/thailand_72_withdraw_user_credit_profile_20260201_0430.csv
"""

from __future__ import annotations

from app.country_packs.mx.credit_profile import CreditCountryPack

TH_CREDIT_COUNTRY_PACK = CreditCountryPack(
    country_code="th",
    display_name="泰国",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
    currency_code="THB",
    source_display_name="风控特征聚合表（泰国）",
    score_band_thresholds=(),                    # 永久空 — TH 数据不含评分模型
    account_type_labels={},                      # 永久空 — TH 数据不含账户类型
    profile_mode="risk_features",                # v6 显式声明业务模型（不是 buro）
    risk_feature_labels={
        # 身份核验类（1 项）
        "liveness_score": "人脸活体识别分数（防伪反欺诈）",
        # 申请行为类（3 项）
        "apply_7d_num": "近 7 天贷款申请次数",
        "apply_refuse_num": "历史申请被拒次数",
        "cashloan_app_num": "设备已安装的现金贷竞品 App 数量",
        # 还款履约类（2 项）
        "finished_assets_num": "历史已结清贷款笔数",
        "max_yuqi_days": "历史最大逾期天数",
        # 社交关系类（3 项）
        "contact_num": "通讯录联系人总数",
        "is_contact_black": "通讯录是否包含黑名单联系人（0/1）",
        "bankcard_user_num": "银行卡关联账户数量",
        # 规则命中类（2 项）
        "rule_hit_多头规则拦截": "多头借贷规则是否命中",
        "rule_hit_逾期未结清拦截": "逾期未结清规则是否命中",
    },
    sentinel_values={
        "liveness_score": ("无活体分",),
        "max_yuqi_days": ("无逾期",),
        "rule_hit_多头规则拦截": ("无记录",),
        "rule_hit_逾期未结清拦截": ("无记录",),
    },
)
```

### Task 2.3：扩展 `app/country_packs/th/behavior_profile.py`（保留 4 常量 + 追加 dataclass）

```python
"""
Thailand behavior profile constants.

Pay cycle data sources:
- BOT (Bank of Thailand) labor statistics: monthly pay dominant
- Large corporations and civil service: 25th-30th of month
- Confidence: medium (formal sector well-documented; SMEs may differ)

Primary channel rationale:
- LINE 在泰国渗透率 >90%，是 messaging + payment 主入口（区别于其他东南亚国家）

业务值来源: docs/specs/05-country-pack-design.md v6.1 §2.2

TODO(country-pack): validate against actual user transaction data once available.
"""

from __future__ import annotations

from app.country_packs.mx.behavior_profile import BehaviorCountryPack

TH_PAY_WINDOW = frozenset({25, 26, 27, 28, 29, 30, 31, 1, 2, 3})
TH_PAY_CYCLE_NAME = "เงินเดือน"
TH_PRIMARY_CHANNEL = "LINE"
TH_PAY_CYCLE_DESCRIPTION = "每月25-31号发薪"

TH_BEHAVIOR_COUNTRY_PACK = BehaviorCountryPack(
    country_code="th",
    display_name="泰国",
    default_language="zh-CN",
    prompt_language="zh-CN",
    report_language="zh-CN",
    source_display_name="Behavior Event Stream (TH)",
    default_contact_channel=TH_PRIMARY_CHANNEL,
    default_contact_time="19:00-21:00",
    stage_labels={
        "acquisition": "拉新与注册阶段",
        "discovery": "产品浏览阶段",
        "application": "申请与认证阶段",
        "repayment": "还款与履约阶段",
        "support": "客服与触达阶段",
        "unknown": "其他行为阶段",
    },
    journey_section_labels={
        "init": "初始化阶段",
        "basic_profile": "基础资料填写",
        "contact_entry": "联系人信息录入",
        "correction_retry": "反复尝试与格式纠错",
        "manual_fix": "密集手动修正",
        "dormancy_return": "深度流失/决策沉默",
        "bank_retry": "银行卡绑定重试",
        "offer_decision": "额度选择与权益决策",
        "unknown": "其他行为阶段",
    },
    stage_keywords={
        "acquisition": (
            "register", "signup", "login", "signin", "otp",
            "verify_phone", "face", "liveness",
            "ลงทะเบียน", "เข้าสู่ระบบ", "ยืนยันตัวตน", "บัตรประชาชน",
            "开户", "注册", "登录", "活体", "验证码",
        ),
        "discovery": (
            "home", "product", "offer", "coupon", "rate",
            "fee", "promo", "banner", "browse",
            "สินค้า", "ดอกเบี้ย", "โปรโมชั่น", "หน้าแรก",
            "产品", "利率", "优惠", "活动", "首页",
        ),
        "application": (
            "apply", "application", "kyc", "upload", "bank",
            "employment", "risk", "approval", "reject", "form",
            "สมัคร", "อนุมัติ", "ปฏิเสธ", "ธนาคาร", "เอกสาร",
            "申请", "认证", "审核", "拒绝", "表单", "绑卡",
        ),
        "repayment": (
            "repay", "payment", "due", "overdue", "collection",
            "renew", "settle",
            "ชำระ", "ค้างชำระ", "ติดตามหนี้", "ต่ออายุ", "ปิดบัญชี",
            "还款", "逾期", "催收", "续借", "结清",
        ),
        "support": (
            "support", "service", "help", "faq", "cs",
            "agent", "call", "line", "message",
            "บริการลูกค้า", "ช่วยเหลือ", "ติดต่อ", "ข้อความ",
            "客服", "帮助", "电话", "消息", "提醒",
        ),
    },
    contact_channel_keywords={
        "LINE": ("line", "line app", "line chat", "ไลน์"),
        "电话": ("call", "phone", "dial", "ivr", "voice", "โทร"),
        "短信": ("sms", "message", "text", "ข้อความ"),
        "App Push": ("push", "notification", "reminder", "แจ้งเตือน"),
    },
)
```

### Task 2.4：3 个根级注册表各加 1 行

文件 1：`app/country_packs/app_profile.py`

```python
from app.country_packs.mx.app_profile import AppCountryPack, MX_APP_COUNTRY_PACK
from app.country_packs.th.app_profile import TH_APP_COUNTRY_PACK   # NEW

_APP_COUNTRY_PACKS: dict[str, AppCountryPack] = {
    MX_APP_COUNTRY_PACK.country_code: MX_APP_COUNTRY_PACK,
    TH_APP_COUNTRY_PACK.country_code: TH_APP_COUNTRY_PACK,         # NEW
}
```

文件 2：`app/country_packs/behavior_profile.py`

```python
from app.country_packs.mx.behavior_profile import (
    BehaviorCountryPack,
    MX_BEHAVIOR_COUNTRY_PACK,
)
from app.country_packs.th.behavior_profile import TH_BEHAVIOR_COUNTRY_PACK   # NEW

_BEHAVIOR_COUNTRY_PACKS: dict[str, BehaviorCountryPack] = {
    MX_BEHAVIOR_COUNTRY_PACK.country_code: MX_BEHAVIOR_COUNTRY_PACK,
    TH_BEHAVIOR_COUNTRY_PACK.country_code: TH_BEHAVIOR_COUNTRY_PACK,         # NEW
}
```

文件 3：`app/country_packs/credit_profile.py`

```python
from app.country_packs.mx.credit_profile import CreditCountryPack, MX_CREDIT_COUNTRY_PACK
from app.country_packs.th.credit_profile import TH_CREDIT_COUNTRY_PACK   # NEW

_CREDIT_COUNTRY_PACKS: dict[str, CreditCountryPack] = {
    MX_CREDIT_COUNTRY_PACK.country_code: MX_CREDIT_COUNTRY_PACK,
    TH_CREDIT_COUNTRY_PACK.country_code: TH_CREDIT_COUNTRY_PACK,         # NEW
}
```

### Task 2.5：扩展 `app/country_packs/th/__init__.py`（覆盖式）

```python
"""Thailand country pack."""

from app.country_packs.th.app_profile import TH_APP_COUNTRY_PACK
from app.country_packs.th.behavior_profile import (
    TH_BEHAVIOR_COUNTRY_PACK,
    TH_PAY_CYCLE_DESCRIPTION,
    TH_PAY_CYCLE_NAME,
    TH_PAY_WINDOW,
    TH_PRIMARY_CHANNEL,
)
from app.country_packs.th.credit_profile import TH_CREDIT_COUNTRY_PACK

__all__ = [
    "TH_APP_COUNTRY_PACK",
    "TH_BEHAVIOR_COUNTRY_PACK",
    "TH_CREDIT_COUNTRY_PACK",
    "TH_PAY_CYCLE_DESCRIPTION",
    "TH_PAY_CYCLE_NAME",
    "TH_PAY_WINDOW",
    "TH_PRIMARY_CHANNEL",
]
```

### Task 2.6：单元测试 `tests/country_packs/test_th_country_packs.py`（新建）

> 若 `tests/country_packs/` 目录不存在，先创建目录 + `__init__.py`：
>
> ```powershell
> New-Item -ItemType Directory -Path tests/country_packs -Force
> New-Item -ItemType File -Path tests/country_packs/__init__.py -Force   # m3：pytest collection 需要包形式，否则 module 路径冲突
> ```

```python
"""th country pack 单元测试 — v6.1 双模式断言（risk_features vs buro）。"""

import logging

import pytest

from app.country_packs.app_profile import load_app_country_pack
from app.country_packs.behavior_profile import load_behavior_country_pack
from app.country_packs.credit_profile import load_credit_country_pack


def test_load_app_country_pack_th_returns_th_pack():
    pack = load_app_country_pack("th")
    assert pack.country_code == "th"
    assert pack.display_name == "Thailand"


def test_load_app_country_pack_mx_unchanged():
    pack = load_app_country_pack("mx")
    assert pack.country_code == "mx"
    assert pack.display_name == "Mexico"


def test_load_behavior_country_pack_th_uses_line_channel():
    pack = load_behavior_country_pack("th")
    assert pack.country_code == "th"
    assert pack.default_contact_channel == "LINE"
    assert pack.display_name == "泰国"
    assert "LINE" in pack.contact_channel_keywords
    assert "ลงทะเบียน" in pack.stage_keywords["acquisition"]


def test_load_credit_country_pack_th_is_risk_features_not_buro():
    """v6.1 核心断言 — TH credit 走 risk_features 模式，不是 buro。"""
    pack = load_credit_country_pack("th")
    assert pack.country_code == "th"
    assert pack.profile_mode == "risk_features"
    assert pack.source_display_name == "风控特征聚合表（泰国）"
    assert pack.currency_code == "THB"
    assert pack.score_band_thresholds == ()
    assert pack.account_type_labels == {}
    assert pack.risk_feature_labels  # 非空
    assert pack.sentinel_values  # 非空
    assert pack.risk_feature_labels["liveness_score"] == "人脸活体识别分数（防伪反欺诈）"
    assert pack.risk_feature_labels["max_yuqi_days"] == "历史最大逾期天数"
    assert "rule_hit_多头规则拦截" in pack.risk_feature_labels
    assert pack.sentinel_values["liveness_score"] == ("无活体分",)
    assert pack.sentinel_values["max_yuqi_days"] == ("无逾期",)


def test_load_credit_country_pack_th_no_ncb_residue():
    """v6.1 hard-gate 提前在单测中守门 — TH pack 不能含任何 NCB 语义。"""
    pack = load_credit_country_pack("th")
    assert "NCB" not in pack.source_display_name
    assert "National Credit Bureau" not in pack.source_display_name
    assert pack.score_band_thresholds == ()
    assert pack.account_type_labels == {}


def test_load_credit_country_pack_mx_buro_mode_unchanged():
    """v6.1 向后兼容 — mx credit pack 行为零变更。"""
    pack = load_credit_country_pack("mx")
    assert pack.country_code == "mx"
    assert pack.profile_mode == "buro"
    assert pack.source_display_name == "Buró de Crédito（墨西哥）"
    assert pack.currency_code == "MXN"
    assert pack.score_band_thresholds[0] == ("A", 700)
    assert pack.account_type_labels["CC"] == "信用卡"
    assert pack.risk_feature_labels == {}
    assert pack.sentinel_values == {}


def test_load_country_pack_unknown_falls_back_to_mx(caplog):
    with caplog.at_level(logging.WARNING):
        pack = load_credit_country_pack("xx")
    assert pack.country_code == "mx"
    assert pack.profile_mode == "buro"
```

### Task 2.7：mx 全量回归

```powershell
python -m pytest tests/ -v --tb=short -x
```

**STOP**：通过数 ≥ N₀_passed + 7（Task 2.6 新增 7 个用例）。
**且**：失败 case 集合 ⊆ N₀_failed_cases（不允许出现新的 failed case；允许保留基线已知失败，详见 `.reports/plan-05-baseline-tests.txt`）。

### Phase 2 出口

- [ ] CreditCountryPack dataclass 已扩展 3 字段
- [ ] mx 实例字面量未改动，行为零变更
- [ ] th 3 个 dataclass 单例 + 4 常量可被 import
- [ ] 3 个根级注册表均含 `"th": TH_X_COUNTRY_PACK`
- [ ] `load_X_country_pack("th")` 返回 th 单例
- [ ] mx 全量回归通过数 ≥ N₀_passed + 7，且失败 case 集合 ⊆ N₀_failed_cases
- [ ] commit message 含 `[mx-touched]` 标注

### Phase 2 commit（m1：精确文件清单）

```powershell
git add `
    app/country_packs/mx/credit_profile.py `
    app/country_packs/th/__init__.py `
    app/country_packs/th/app_profile.py `
    app/country_packs/th/behavior_profile.py `
    app/country_packs/th/credit_profile.py `
    app/country_packs/app_profile.py `
    app/country_packs/behavior_profile.py `
    app/country_packs/credit_profile.py `
    tests/country_packs/__init__.py `
    tests/country_packs/test_th_country_packs.py
git commit -m "[plan-05][P2][mx-touched] CreditCountryPack 双模式扩展 + th risk_features country pack 落地（向后兼容 mx）"
```

---

## Phase 3 — country_code 全链路贯穿 + profile_mode 分支 + 路径 Q contracts 扩展

> ⚠️ **mx-touched**：本 Phase 修改 4 个 API 路由 + orchestrator + 6 个 Skill + Credit explainer / feature_builder / data_access / contracts → commit 必须含 `[mx-touched]` + mx 全量回归。

### Task 3.1（C5 修订）：后端 schema —— `app/schemas/request.py`

> **C5 完整 patch**：补 import + 加字段，不只改字段。

变更 1（import 行）：

```python
# 修改前
from typing import List, Optional

# 修改后
from typing import List, Literal, Optional
```

变更 2（字段定义）：

```python
class AnalyzeRequest(BaseModel):
    """Accept either a single uid or a list of uids in one request."""

    uid: Optional[str] = None
    uids: Optional[List[str]] = None
    application_time: Optional[str] = None
    country: Literal["mx", "th"] = "mx"   # NEW
```

> `model_validator` / `get_uid_list` 不动。

### Task 3.2：后端 `/api/analyze-module` GET query 加 country —— `app/api/analyze_module.py`

```python
"""Module-level analysis endpoint for progressive frontend loading."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.services.orchestrator import shared_orchestrator

router = APIRouter()


@router.get("/analyze-module", summary="Analyze one module for one uid")
def analyze_user_module(
    uid: str = Query(..., description="Single uid"),
    module: str = Query(
        ...,
        description="One of: app, behavior, credit, comprehensive, product, ops",
    ),
    application_time: str | None = Query(
        None, description="Optional ISO datetime for App install decay"
    ),
    country: Literal["mx", "th"] = Query(  # NEW
        "mx", description="Country code"
    ),
) -> dict:
    """Run one page module and return a structured status payload."""
    return shared_orchestrator.analyze_module(
        uid.strip(),
        module.strip().lower(),
        application_time=application_time,
        country_code=country,   # NEW
    )
```

### Task 3.3（M1 修订）：后端 `analyze-stream` 透传 country —— `app/api/analyze_stream.py`

> **M1 完整 patch**：`_run_analysis_in_thread` 第 2 形参插入 `country_code: str`，调用点同步。

```python
def _run_analysis_in_thread(
    uids: list[str],
    application_time: str | None,
    country_code: str,   # NEW
    q: queue.Queue,
) -> None:
    """Background thread entry: run orchestrator + push events into queue."""
    try:
        q.put({
            "type": "analysis_started",
            "uids": uids,
            "total_skills_per_uid": TOTAL_SKILLS_PER_UID,
        })

        def cb(evt: dict[str, Any]) -> None:
            q.put(evt)

        response = shared_orchestrator.analyze(
            uids,
            application_time=application_time,
            country_code=country_code,   # NEW
            progress_callback=cb,
        )

        q.put({
            "type": "analysis_completed",
            "results": [r.model_dump(mode="json") for r in response.results],
        })
    except Exception as exc:  # noqa: BLE001 — bottom-of-stack guard
        q.put({"type": "stream_error", "error_message": str(exc)})
    finally:
        q.put(None)  # sentinel


@router.post("/analyze-stream", summary="Stream analysis progress as Server-Sent Events")
async def analyze_stream(request: AnalyzeRequest) -> StreamingResponse:
    uids = request.get_uid_list()
    application_time = request.application_time
    country_code = request.country   # NEW
    q: queue.Queue = queue.Queue()

    thread = threading.Thread(
        target=_run_analysis_in_thread,
        args=(uids, application_time, country_code, q),   # NEW
        daemon=True,
    )
    thread.start()
    # 后续 event_gen() / return StreamingResponse 不变
```

### Task 3.4（M2 修订）：`batch_service.py` 双方法都加 country_code

```python
"""Batch analysis service shared by analyze and analyze-file APIs."""

from __future__ import annotations

from app.schemas.final_response import AnalyzeResponse
from app.schemas.request import AnalyzeRequest
from app.services.orchestrator import AnalysisOrchestrator


class BatchAnalysisService:
    """Provide one place for single/batch uid orchestration."""

    def __init__(self, orchestrator: AnalysisOrchestrator) -> None:
        self.orchestrator = orchestrator

    def analyze_request(self, request: AnalyzeRequest) -> AnalyzeResponse:
        return self.orchestrator.analyze(
            request.get_uid_list(),
            application_time=request.application_time,
            country_code=request.country,   # NEW
        )

    def analyze_uids(self, uids: list[str], country_code: str = "mx") -> AnalyzeResponse:   # NEW 第 2 形参
        return self.orchestrator.analyze(uids, country_code=country_code)
```

### Task 3.5（C2 修订 — 5 处调用点全改）：Orchestrator 透传 + cache key 4 元组

#### 3.5.1 `analyze() / _analyze_single_user()` 加 country_code

```python
def analyze(
    self,
    uids: list[str],
    application_time: str | None = None,
    country_code: str = "mx",   # NEW
    progress_callback=None,
) -> AnalyzeResponse:
    results = [
        self._analyze_single_user(
            uid,
            application_time=application_time,
            country_code=country_code,   # NEW
            progress_callback=progress_callback,
        )
        for uid in uids
    ]
    return AnalyzeResponse(results=results)


def _analyze_single_user(
    self,
    uid: str,
    application_time: str | None = None,
    country_code: str = "mx",   # NEW
    progress_callback=None,
) -> UserAnalysisResult:
    logger.info("Start analyze uid=%s", uid)
    started = perf_counter()

    all_results = self.registry.run_all(
        uid=uid,
        progress_callback=progress_callback,
        repository=self.repository,
        application_time=application_time,
        country_code=country_code,   # NEW —— 透传到所有 Skill 的 kwargs
    )
    # 后续 build_standardized_labels / UserAnalysisResult 构造不变
```

#### 3.5.2 `analyze_module() / _run_single_module()` + `_analyze_comprehensive_module() / _analyze_advisory_module()` 全部加 country_code

```python
def analyze_module(
    self,
    uid: str,
    module: str,
    application_time: str | None = None,
    country_code: str = "mx",   # NEW
) -> dict:
    normalized_uid = str(uid or "").strip()
    normalized_module = str(module or "").strip().lower()
    if not normalized_uid:
        return self._module_error_payload(uid=normalized_uid, module=normalized_module or "unknown",
                                          code="invalid_uid", message="UID is required.")
    if normalized_module not in self.SUPPORTED_MODULES:
        return self._module_error_payload(uid=normalized_uid, module=normalized_module or "unknown",
                                          code="invalid_module", message=f"Unsupported module: {normalized_module}")
    if normalized_module == "comprehensive":
        return self._analyze_comprehensive_module(
            normalized_uid, application_time=application_time, country_code=country_code,   # NEW
        )
    if normalized_module in ("product", "ops"):
        return self._analyze_advisory_module(
            normalized_uid, normalized_module,
            application_time=application_time, country_code=country_code,   # NEW
        )
    return self._run_single_module(
        normalized_uid, normalized_module,
        application_time=application_time, country_code=country_code,   # NEW
    )


def _run_single_module(
    self, uid: str, module: str,
    application_time: str | None = None,
    country_code: str = "mx",   # NEW
) -> dict:
    started = perf_counter()
    skill_name = self.MODULE_SKILL_MAP[module]
    skill = self.registry.get(skill_name)
    try:
        kwargs: dict = {"uid": uid, "repository": self.repository, "country_code": country_code}   # NEW
        if module == "app":
            kwargs["application_time"] = application_time
        result = skill.analyze(**kwargs)
        logger.info("Module done uid=%s module=%s duration=%.2fs",
                    uid, module, perf_counter() - started)
        self._set_cached(uid, module, application_time, country_code, result)   # NEW（C2 调用点 1/5）
        return {"uid": uid, "module": module, "status": "ok", "data": result, "error": None}
    except Exception as exc:
        logger.exception("Module failed uid=%s module=%s: %s", uid, module, exc)
        return self._module_error_payload(uid=uid, module=module,
                                          code="module_runtime_error", message=str(exc))


def _analyze_comprehensive_module(
    self, uid: str,
    application_time: str | None = None,
    country_code: str = "mx",   # NEW
) -> dict:
    upstream: dict[str, dict] = {}
    for mod in ("app", "behavior", "credit"):
        cached = self._get_cached(uid, mod, application_time, country_code)   # NEW（C2 调用点 2/5）
        if cached is not None:
            upstream[mod] = cached
            continue
        payload = self._run_single_module(
            uid, mod, application_time=application_time, country_code=country_code,   # NEW
        )
        if payload.get("status") == "ok" and isinstance(payload.get("data"), dict):
            upstream[mod] = payload["data"]
            continue
        return self._module_error_payload(uid=uid, module="comprehensive",
                                          code="dependency_module_failed",
                                          message=f"Dependency module failed: {mod}")
    started = perf_counter()
    try:
        comp_skill = self.registry.get("comprehensive_profile")
        result = comp_skill.analyze(
            uid=uid,
            repository=self.repository,
            country_code=country_code,   # NEW（C1 — comprehensive Skill 透传）
            app_profile_result=upstream["app"],
            behavior_profile_result=upstream["behavior"],
            credit_profile_result=upstream["credit"],
        )
        logger.info("Module done uid=%s module=comprehensive duration=%.2fs",
                    uid, perf_counter() - started)
        self._set_cached(uid, "comprehensive", application_time, country_code, result)   # NEW（C2 调用点 3/5）
        return {"uid": uid, "module": "comprehensive", "status": "ok", "data": result, "error": None}
    except Exception as exc:
        logger.exception("Comprehensive module failed uid=%s: %s", uid, exc)
        return self._module_error_payload(uid=uid, module="comprehensive",
                                          code="module_runtime_error", message=str(exc))


def _analyze_advisory_module(
    self, uid: str, module: str,
    application_time: str | None = None,
    country_code: str = "mx",   # NEW
) -> dict:
    comp_cached = self._get_cached(uid, "comprehensive", application_time, country_code)   # NEW（C2 调用点 4/5）
    if comp_cached is None:
        comp_payload = self._analyze_comprehensive_module(
            uid, application_time=application_time, country_code=country_code,   # NEW
        )
        if comp_payload.get("status") != "ok":
            return self._module_error_payload(uid=uid, module=module,
                                              code="dependency_module_failed",
                                              message="Comprehensive module failed")
        comp_cached = comp_payload["data"]
    started = perf_counter()
    skill_name = self.MODULE_SKILL_MAP[module]
    try:
        skill = self.registry.get(skill_name)
        result = skill.analyze(
            uid=uid,
            repository=self.repository,
            country_code=country_code,   # NEW（C1 — product/ops Skill 透传）
            comprehensive_profile_result=comp_cached,
        )
        logger.info("Module done uid=%s module=%s duration=%.2fs",
                    uid, module, perf_counter() - started)
        self._set_cached(uid, module, application_time, country_code, result)   # NEW（C2 调用点 5/5）
        return {"uid": uid, "module": module, "status": "ok", "data": result, "error": None}
    except Exception as exc:
        logger.exception("Advisory module failed uid=%s module=%s: %s", uid, module, exc)
        return self._module_error_payload(uid=uid, module=module,
                                          code="module_runtime_error", message=str(exc))
```

#### 3.5.3 `_module_cache` 类型 + 三方法签名升级

```python
def __init__(self) -> None:
    self.repository = self._init_repository()
    self.model_client = ModelClient()
    self.registry = self._build_registry()
    self._module_cache: dict[tuple[str, str, str, str], dict] = {}   # NEW 4 元组类型
    self._cache_lock = RLock()


def _cache_key(
    self, uid: str, module: str,
    application_time: str | None, country_code: str,
) -> tuple[str, str, str, str]:
    return (uid, module, str(application_time or ""), country_code)


def _get_cached(
    self, uid: str, module: str,
    application_time: str | None, country_code: str,
) -> dict | None:
    with self._cache_lock:
        cached = self._module_cache.get(self._cache_key(uid, module, application_time, country_code))
        return dict(cached) if isinstance(cached, dict) else None


def _set_cached(
    self, uid: str, module: str,
    application_time: str | None, country_code: str,
    result: dict,
) -> None:
    with self._cache_lock:
        self._module_cache[self._cache_key(uid, module, application_time, country_code)] = dict(result)
```

> ✅ **C2 调用点全清单**（5 处，已在 3.5.2 中标注）：
> 1. `_run_single_module` 内 `_set_cached(...)` ×1
> 2. `_analyze_comprehensive_module` 内 for 循环 `_get_cached(...)` ×1（mod=app/behavior/credit 三模块共用一行）
> 3. `_analyze_comprehensive_module` 内 comprehensive 完成后 `_set_cached(...)` ×1
> 4. `_analyze_advisory_module` 入口 `_get_cached(uid, "comprehensive", ...)` ×1
> 5. `_analyze_advisory_module` 内 advisory 完成后 `_set_cached(...)` ×1

### Task 3.6（C1 + C4 修订 — 6 个 Skill 同时改，分 3 段独立 patch）

#### 3.6.A：App Skill — 仅在原有 application_time 后追加 country_code

文件：`app/runtime_skills/app_profile_agent.py`

```python
def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
    """Execute the App profile pipeline end to end."""
    repository = kwargs.get("repository")
    application_time = kwargs.get("application_time")
    country_code = kwargs.get("country_code")   # NEW
    context = build_app_run_context(
        uid,
        application_time=application_time,
        country_code=country_code,   # NEW
        source_preference=settings.data_source,
        enable_llm_explanation=True,
    )
    # 后续逻辑不变
```

#### 3.6.B：Behavior Skill — 仅加 country_code（**不动 application_time，不破坏现有契约**）

文件：`app/runtime_skills/behavior_profile_agent.py`

```python
def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
    """Execute the Behavior profile pipeline end to end."""
    repository = kwargs.get("repository")
    country_code = kwargs.get("country_code")   # NEW（仅此一处）
    context = build_behavior_run_context(
        uid,
        country_code=country_code,   # NEW（不加 application_time）
        source_preference=settings.data_source,
        enable_llm_explanation=True,
    )
    # 后续逻辑不变
```

#### 3.6.C：Credit Skill — 仅加 country_code（**不动 application_time**）

文件：`app/runtime_skills/credit_profile_agent.py`

```python
def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
    """Execute the Credit profile pipeline end to end."""
    repository = kwargs.get("repository")
    country_code = kwargs.get("country_code")   # NEW（仅此一处）
    context = build_credit_run_context(
        uid,
        country_code=country_code,   # NEW（不加 application_time）
        source_preference=settings.data_source,
        enable_llm_explanation=True,
    )
    # 后续逻辑不变
```

#### 3.6.D：Comprehensive Skill — 加 country_code 透传到 build_comprehensive_run_context

文件：`app/runtime_skills/comprehensive_agent.py`

```python
def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
    context = build_comprehensive_run_context(
        uid,
        application_time=kwargs.get("application_time"),
        country_code=kwargs.get("country_code"),   # NEW（C1 修复）
    )
    upstream = self.upstream_provider.fetch(
        uid, context,
        app_result=kwargs.get("app_profile_result", {}),
        behavior_result=kwargs.get("behavior_profile_result", {}),
        credit_result=kwargs.get("credit_profile_result", {}),
    )
    # 后续逻辑不变
```

> **前置依赖**：若 `build_comprehensive_run_context` 当前签名不接收 `country_code`，需要先扩展该函数（与 build_app/behavior/credit_run_context 同构）。Claude Code 执行时先 grep 该函数定义，若已有 `country_code` 参数（默认 None）则直接传；若没有，按 build_app_run_context 的模式扩展（仅加 `country_code: str | None = None` 形参 + fallback 到 settings.default_country_code）。

#### 3.6.E：Product / Ops Advice Skill — 同 Comprehensive 模式

文件：`app/runtime_skills/product_advice_agent.py`

```python
def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
    context = build_product_advice_run_context(
        uid,
        country_code=kwargs.get("country_code"),   # NEW（C1 修复）
    )
    # 后续逻辑不变
```

文件：`app/runtime_skills/ops_advice_agent.py`

```python
def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
    context = build_ops_advice_run_context(
        uid,
        country_code=kwargs.get("country_code"),   # NEW（C1 修复）
    )
    # 后续逻辑不变
```

> **前置依赖**：与 3.6.D 同 — `build_product_advice_run_context` / `build_ops_advice_run_context` 需先支持 `country_code: str | None = None`。Claude Code 先 grep 现状，缺则扩展。**该扩展属于纯加可选形参，向后兼容，零行为变更。**

### Task 3.6.5（C3 修订 — v6.1 路径 Q：CreditRawData 扩展 + Explainer 双模板 + FeatureBuilder 二分支 + DataProvider 二分支）

#### 3.6.5.A：扩展 `CreditRawData` TypedDict（路径 Q 核心）

文件：`app/runtime_skills/credit_profile/contracts.py`

变更 1（TypedDict 字段扩展）：

```python
class CreditRawData(TypedDict):
    """Canonical raw-data contract used after repository access.

    v6.1 路径 Q：新增 risk_features_record 字段，承载 TH 风控特征聚合表原始数据。
    - mx (profile_mode="buro"): risk_features_record 永远为 None
    - th (profile_mode="risk_features"): risk_features_record 填 11 维原始 dict（保留哨兵字符串不转 None）
    """

    uid: str
    country_code: str
    source_meta: dict[str, Any]
    prepared_record: CreditPreparedRecord
    risk_features_record: dict[str, Any] | None   # NEW（v6.1 路径 Q）
    data_status: str
    errors: list[str]
```

变更 2（`build_credit_run_context` 返回 dict 加 `profile_mode` 键）：

```python
def build_credit_run_context(
    uid: str,
    *,
    application_time: str | None = None,
    country_code: str | None = None,
    trace_id: str = "",
    source_preference: str | None = None,
    enable_llm_explanation: bool = True,
    language: str | None = None,
    channel: str = "api",
) -> CreditRunContext:
    """Create a stable run context for the Credit profile pipeline."""
    pack = load_credit_country_pack(country_code or settings.default_country_code)
    application_time_value = application_time or datetime.now(timezone.utc).isoformat()
    return {
        "uid": uid,
        "country_code": pack.country_code,
        "application_time": application_time_value,
        "trace_id": trace_id,
        "source_preference": source_preference or settings.data_source,
        "enable_llm_explanation": enable_llm_explanation,
        "language": language or pack.default_language,
        "channel": channel or "api",
        "profile_mode": pack.profile_mode,   # NEW（v6.1 路径 Q）
    }
```

变更 3（`CreditRunContext` TypedDict 同步增字段）：

```python
class CreditRunContext(TypedDict):
    uid: str
    country_code: str
    application_time: str
    trace_id: str
    source_preference: str
    enable_llm_explanation: bool
    language: str
    channel: str
    profile_mode: str   # NEW（v6.1 路径 Q）— 取值 "buro" 或 "risk_features"
```

#### 3.6.5.B：扩展 `CreditDataProvider.fetch` 加 risk_features 分支

文件：`app/runtime_skills/credit_profile/data_access.py`

> 在现有 `fetch` 方法的入口处加 profile_mode 分支。mx 走原 buro 分支（行为零变更，仅 `_build_raw_data` 内部新增传 `risk_features_record=None`）。th 走新分支构造 risk_features_record。

```python
def fetch(self, uid: str, context: CreditRunContext) -> CreditRawData:
    """v6.1 路径 Q：按 profile_mode 分支。"""
    if context.get("profile_mode") == "risk_features":
        return self._fetch_risk_features(uid, context)
    return self._fetch_buro(uid, context)   # 原 fetch 逻辑重命名为 _fetch_buro


def _fetch_buro(self, uid: str, context: CreditRunContext) -> CreditRawData:
    """原有 mx Buró 解读逻辑 — 行为零变更（仅 _build_raw_data 内部加 risk_features_record=None）。"""
    # 此处粘贴原 fetch 方法内 67 行业务逻辑（不动）
    ...


def _fetch_risk_features(self, uid: str, context: CreditRunContext) -> CreditRawData:
    """v6.1 路径 Q：TH 风控特征聚合表分支。

    V1 实现策略：
    - 仅从 repository.get_credit_data(uid) 拿原始 payload（结构待 LocalRepository 后续扩展）
    - 不强行解析 csv（属于后续 plan 范围）
    - prepared_record 用 build_empty_prepared_record(uid, country_code="th") 占位（满足 contracts 类型）
    - risk_features_record 直接透传 raw_payload.get("risk_features", {}) 或 None
    - 保留哨兵字符串原状不转 None（feature_builder 层负责识别）
    """
    raw_payload = self.repository.get_credit_data(uid) or {}
    fetched_at = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []

    if not isinstance(raw_payload, dict) or not raw_payload:
        logger.warning("TH credit raw data missing uid=%s", uid)
        return {
            "uid": uid,
            "country_code": context["country_code"],
            "source_meta": {
                "source_type": "",
                "origin_ref": "",
                "source_variant": "missing",
                "fetched_at": fetched_at,
            },
            "prepared_record": build_empty_prepared_record(uid, country_code=context["country_code"]),
            "risk_features_record": None,
            "data_status": "missing",
            "errors": [],
        }

    # V1 透传策略：repository 给什么就用什么
    risk_features_record = raw_payload.get("risk_features")
    if not isinstance(risk_features_record, dict):
        risk_features_record = None

    return {
        "uid": uid,
        "country_code": context["country_code"],
        "source_meta": {
            "source_type": str(raw_payload.get("source_type", "") or ""),
            "origin_ref": str(raw_payload.get("source_file", "") or raw_payload.get("source_ref", "") or ""),
            "source_variant": str(raw_payload.get("source_kind", "") or "").strip().lower() or "th_risk_features_v1",
            "fetched_at": fetched_at,
        },
        "prepared_record": build_empty_prepared_record(uid, country_code=context["country_code"]),
        "risk_features_record": risk_features_record,
        "data_status": "ok" if risk_features_record else "missing",
        "errors": errors,
    }
```

> **`_build_raw_data` 现有方法**：在所有 `return self._build_raw_data(...)` 调用上加 `risk_features_record=None`，且函数签名加 `risk_features_record=None` 形参（保 mx 行为零变更）。具体改动 Claude Code 按现状 grep 后实施。

#### 3.6.5.C：扩展 `CreditFeatureBuilder.build` 加 profile_mode 分支

文件：`app/runtime_skills/credit_profile/feature_builder.py`

```python
class CreditFeatureBuilder:
    """Build deterministic Credit features from prepared repository data."""

    def build(
        self,
        raw_data: CreditRawData,
        context: CreditRunContext,
    ) -> CreditFeatureBundle:
        """v6.1 路径 Q：按 profile_mode 分支。"""
        if context.get("profile_mode") == "risk_features":
            return self._build_risk_features(raw_data, context)
        return self._build_buro_features(raw_data, context)

    def _build_buro_features(
        self,
        raw_data: CreditRawData,
        _context: CreditRunContext,
    ) -> CreditFeatureBundle:
        """原 build 方法内全部逻辑 — 行为零变更，仅函数名重命名。"""
        # 此处粘贴原 build 方法内全部业务逻辑（mx Buró schema 解读，不动一行）
        ...

    def _build_risk_features(
        self,
        raw_data: CreditRawData,
        context: CreditRunContext,
    ) -> CreditFeatureBundle:
        """v6.1 路径 Q：TH 风控特征聚合解读 V1 极简版。

        V1 策略：
        - 不做复杂特征工程（11 维原始字段直接透传给 explainer prompt）
        - feature_status="ok" 当 risk_features_record 非空
        - feature_status="missing" 当 risk_features_record 为 None
        - summary_features / account_features / derived_signals 留空 dict（contracts 兼容）
        """
        risk_record = raw_data.get("risk_features_record")
        feature_status = "ok" if risk_record else "missing"
        return {
            "uid": raw_data["uid"],
            "country_code": raw_data["country_code"],
            "prepared_record": raw_data.get("prepared_record", {}),
            "summary_features": {},
            "account_features": {},
            "derived_signals": {
                "risk_features_record": risk_record or {},
                "profile_mode": "risk_features",
            },
            "feature_status": feature_status,
            "errors": list(raw_data.get("errors", [])),
        }
```

#### 3.6.5.D：扩展 `CreditDecisionEngine.decide` 加 profile_mode 分支

文件：`app/runtime_skills/credit_profile/decision_engine.py`

```python
class CreditDecisionEngine:
    def decide(
        self,
        feature_bundle: CreditFeatureBundle,
        context: CreditRunContext,
    ) -> CreditDecisionResult:
        """v6.1 路径 Q：按 profile_mode 分支。"""
        if context.get("profile_mode") == "risk_features":
            return self._decide_risk_features(feature_bundle, context)
        return self._decide_buro(feature_bundle, context)

    def _decide_buro(
        self,
        feature_bundle: CreditFeatureBundle,
        _context: CreditRunContext,
    ) -> CreditDecisionResult:
        """原 decide 方法内全部逻辑 — 行为零变更，仅函数名重命名。"""
        # 此处粘贴原 decide 方法内全部业务逻辑（不动）
        ...

    def _decide_risk_features(
        self,
        feature_bundle: CreditFeatureBundle,
        context: CreditRunContext,
    ) -> CreditDecisionResult:
        """v6.1 路径 Q：TH 风控特征 V1 极简决策（不分等级，不打分）。"""
        risk_record = feature_bundle.get("derived_signals", {}).get("risk_features_record", {})
        return {
            "uid": feature_bundle["uid"],
            "country_code": feature_bundle["country_code"],
            "decision_status": "ok" if risk_record else "missing",
            "summary_seed": "TH 风控特征聚合 V1 — 由 LLM explainer 解读 11 维原始信号",
            "evidence_seed": {"risk_features_record": risk_record},
            "financial_maturity": {},
            "debt_pressure": {},
            "credit_stability": {},
            "borrowing_urgency": {},
            "credit_signal_score": 0,
            "metrics": {"profile_mode": "risk_features"},
            "tags_rule": [],
            "llm_fallback_profile": {"summary": "", "tags": [], "report_markdown": ""},
            "errors": list(feature_bundle.get("errors", [])),
        }

    def build_prompt_payload(
        self,
        feature_bundle: CreditFeatureBundle,
        decision_result: CreditDecisionResult,
    ) -> dict[str, Any]:
        """既有方法：v6.1 加上 profile_mode + risk_feature_labels + sentinel_values 注入。"""
        # 在原 payload dict 末尾加：
        # payload["profile_mode"] = decision_result.get("metrics", {}).get("profile_mode", "buro")
        # payload["risk_features_record"] = decision_result.get("evidence_seed", {}).get("risk_features_record", {})
        # 然后在 explainer 里通过 country pack 取 risk_feature_labels / sentinel_values
        ...
```

#### 3.6.5.E：改造 `CreditExplainer.__init__` 双模板字典 + `explain()` 选模板

文件：`app/runtime_skills/credit_profile/explainer.py`

```python
class CreditExplainer:
    """Generate LLM explanation fields on top of deterministic Credit decisions."""

    def __init__(
        self,
        model_client: ModelClient,
        prompt_paths: dict[str, Path],   # NEW（v6.1 — 不再是单一 prompt_path）
    ) -> None:
        self.model_client = model_client
        self.prompt_paths = {k: Path(v) for k, v in prompt_paths.items()}
        # 防御性断言：必须含 buro / risk_features 两个键
        assert "buro" in self.prompt_paths, "Credit explainer 必须配置 buro prompt 模板"
        assert "risk_features" in self.prompt_paths, "Credit explainer 必须配置 risk_features prompt 模板"

    def explain(
        self,
        uid: str,
        feature_bundle: CreditFeatureBundle,
        decision_result: CreditDecisionResult,
        prompt_payload: dict[str, Any],
        context: CreditRunContext,
    ) -> CreditExplanationResult:
        country_code = context["country_code"]
        profile_mode = context.get("profile_mode", "buro")

        # v6.1 路径 Q：按 profile_mode 选模板路径
        active_prompt_path = self.prompt_paths.get(profile_mode, self.prompt_paths["buro"])

        # 后续逻辑不变 —— 用 active_prompt_path 取代原 self.prompt_path
        # 例如 self._build_prompt(uid, ..., prompt_path=active_prompt_path) 等
        ...
```

#### 3.6.5.F：`CreditProfileSkill.__init__` 传双 prompt_path

文件：`app/runtime_skills/credit_profile_agent.py`

```python
def __init__(self, model_client: ModelClient) -> None:
    self.model_client = model_client
    buro_prompt_path = settings.resolve_path(f"{settings.prompt_dir}/credit_profile_prompt.md")
    th_prompt_path = settings.resolve_path(f"{settings.prompt_dir}/credit_profile_th_prompt.md")
    self.feature_builder = CreditFeatureBuilder()
    self.decision_engine = CreditDecisionEngine()
    self.explainer = CreditExplainer(
        model_client,
        prompt_paths={
            "buro": buro_prompt_path,
            "risk_features": th_prompt_path,
        },
    )
    self.assembler = CreditPageAssembler(model_client)
```

#### 3.6.5.G：新建 `app/prompts/credit_profile_th_prompt.md`（5 段结构骨架）

> Claude Code 实施时按下述骨架填充完整 prompt 文本。骨架结构必须含 5 个二级标题：身份核验 / 申请行为 / 还款履约 / 社交关系 / 规则命中。

```markdown
# Thailand Risk Feature Profile（风控特征聚合解读）

## 数据来源声明
本用户的「Credit Profile」数据为公司内部反欺诈风控特征聚合表（{source_display_name}），
共 11 维特征，**不是信用局信用报告**，**不存在 FICO 评分**，**不存在账户类型列表**。
请勿生成虚拟信用等级或账户类型。

## 输入字段语义（risk_feature_labels 11 项）
{risk_feature_labels 字典 markdown 化}

## 哨兵值语义（sentinel_values）
- liveness_score 取值「无活体分」= 用户未进入活体环节，**不要**判定为低分
- max_yuqi_days 取值「无逾期」= 历史无逾期（积极信号），必须在解读中明示
- rule_hit_xxx 取值「无记录」= 规则未触发判定，**不要**默认按命中处理

## 用户原始数据
{risk_features_record dict 序列化}

## 输出要求（5 段 markdown）

### 1. 身份核验
（解读 liveness_score）

### 2. 申请行为
（解读 apply_7d_num / apply_refuse_num / cashloan_app_num — 重点判断多头借贷倾向）

### 3. 还款履约
（解读 finished_assets_num / max_yuqi_days）

### 4. 社交关系
（解读 contact_num / is_contact_black / bankcard_user_num）

### 5. 规则命中
（解读两条规则命中状态）

## 严禁行为
- ❌ 输出 FICO 分数 / 信用等级 A/B/C/D
- ❌ 输出 account_type 列表
- ❌ 把「无活体分」/「无逾期」/「无记录」当作有效数值参与计算
```

#### 3.6.5.H：单元测试 `tests/runtime_skills/test_credit_profile_mode_branching.py`（新建）

> 若 `tests/runtime_skills/` 目录不存在，先创建 + `__init__.py`。

```python
"""v6.1 路径 Q + profile_mode 分支单测。"""

import pytest

from app.country_packs.credit_profile import load_credit_country_pack
from app.runtime_skills.credit_profile.contracts import build_credit_run_context


def test_build_credit_run_context_th_emits_risk_features_profile_mode():
    """v6.1 路径 Q — TH context 必须含 profile_mode='risk_features'。"""
    context = build_credit_run_context("u_th_1", country_code="th")
    assert context["country_code"] == "th"
    assert context["profile_mode"] == "risk_features"


def test_build_credit_run_context_mx_emits_buro_profile_mode():
    """v6.1 路径 Q — mx context 必须含 profile_mode='buro'。"""
    context = build_credit_run_context("u_mx_1", country_code="mx")
    assert context["country_code"] == "mx"
    assert context["profile_mode"] == "buro"


def test_credit_explainer_accepts_dual_prompt_paths(tmp_path):
    """v6.1 路径 Q — CreditExplainer.__init__ 必须接受 prompt_paths 字典。"""
    from pathlib import Path
    from app.core.model_client import ModelClient
    from app.runtime_skills.credit_profile.explainer import CreditExplainer

    buro = tmp_path / "buro.md"
    risk = tmp_path / "th.md"
    buro.write_text("buro template")
    risk.write_text("risk_features template")

    explainer = CreditExplainer(
        ModelClient(),
        prompt_paths={"buro": buro, "risk_features": risk},
    )
    assert "buro" in explainer.prompt_paths
    assert "risk_features" in explainer.prompt_paths


def test_th_pack_does_not_leak_into_buro_path():
    """TH pack 的 score_band_thresholds 永远空，feature_builder 必须按 profile_mode 跳过 mx 路径。"""
    pack = load_credit_country_pack("th")
    assert pack.profile_mode == "risk_features"
    assert pack.score_band_thresholds == ()


def test_mx_pack_does_not_use_risk_feature_labels():
    """mx pack 在 buro 路径下不依赖 risk_feature_labels（向后兼容）。"""
    pack = load_credit_country_pack("mx")
    assert pack.profile_mode == "buro"
    assert pack.risk_feature_labels == {}
    assert pack.sentinel_values == {}
```

### Task 3.7：前端 country state + 切换清空 React state —— `app/static/js/app.jsx`

> 锚点：在 `analysisResults / moduleStates / moduleStatesByUid / traceSeedByUid` 等 useState 声明后插入。

```jsx
const [country, setCountry] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const v = params.get("country");
    return v === "th" ? "th" : "mx";
});

useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("country", country);
    window.history.replaceState({}, "", url.toString());
}, [country]);

function resetAnalysisStateForCountry() {
    setAnalysisResults([]);
    setSelectedResultIndex(0);
    setModuleStates(createInitialModuleStates());
    setModuleStatesByUid({});
    setErrorMessage("");
    setTraceSeedByUid({});
}

function handleCountryChange(next) {
    if (next === country) return;
    if (!window.confirm("切换国家会清空当前分析结果，是否继续？")) return;
    resetAnalysisStateForCountry();
    setCountry(next);
}
```

### Task 3.8：Header dropdown

> 在 Header / DashboardView 区域加 `<select value={country} onChange={(e) => handleCountryChange(e.target.value)}>` 渲染 mx/th 两选项。具体位置由 Claude Code 按现有 Header 布局插入；通过 props 把 `country` 和 `handleCountryChange` 从 app.jsx 顶层传下去。

### Task 3.9（M4 修订）：前端 fetch 透传 —— `app/static/js/services/api.js`

```javascript
async function analyzeByUid(trimmedUid, normalizedApplicationTime, country) {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      uid: trimmedUid,
      application_time: normalizedApplicationTime,
      country: country || 'mx',   // NEW
    })
  });
  // 后续不变
}

async function analyzeByFile(file, country) {   // NEW 第 2 形参
  const formData = new FormData();
  formData.append('file', file);
  formData.append('country', country || 'mx');   // NEW（M4 修订：FormData 加 country）
  const response = await fetch('/api/analyze-file', { method: 'POST', body: formData });
  // 后续不变
}

async function analyzeByUidStream(trimmedUid, normalizedApplicationTime, onEvent, signal, country) {
  const body = trimmedUid && trimmedUid.length === 18
    ? {
        uid: trimmedUid,
        application_time: normalizedApplicationTime,
        country: country || 'mx',   // NEW
      }
    : null;
  // 后续不变
}

async function analyzeModule(targetUid, moduleName, normalizedApplicationTime, country) {   // NEW 第 4 形参
  const params = new URLSearchParams({
    uid: targetUid,
    module: moduleName,
    country: country || 'mx',   // NEW
  });
  if (normalizedApplicationTime) {
    params.set('application_time', normalizedApplicationTime);
  }
  const res = await fetch(`/api/analyze-module?${params.toString()}`);
  // 后续不变
}
```

> **后端 `/api/analyze-file` 同步加 country**（M4 必跑）：

文件：`app/api/analyze.py`

```python
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

@router.post(
    "/analyze-file",
    response_model=AnalyzeResponse,
    summary="Analyze users from an uploaded txt or csv file",
)
async def analyze_users_from_file(
    file: UploadFile = File(...),
    country: Literal["mx", "th"] = Form("mx"),   # NEW（M4 修订）
) -> AnalyzeResponse:
    raw_bytes = await file.read()
    try:
        normalized_uids = parse_uid_file(file.filename or "", raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return batch_service.analyze_uids(normalized_uids, country_code=country)   # NEW（M2 修订）
```

### Task 3.10（M3 修订）：app.jsx 6 处 `analyzeModule` 调用全加 country 参数

> **M3 锚点清单**（`app/static/js/app.jsx` 实测行号）：

| 行号 | 当前调用 | 修改后 |
|---|---|---|
| L228 | `analyzeModule(targetUid, moduleName, normalizedApplicationTime)` | `analyzeModule(targetUid, moduleName, normalizedApplicationTime, country)` |
| L251 | `loadModuleForUid(targetUid, m, normalizedApplicationTime)` | （由 Task 3.10 内 loadModuleForUid 函数体改动间接传透 country，此调用点不动） |
| L255 | `loadModuleForUid(targetUid, 'comprehensive', normalizedApplicationTime)` | （同上不动） |
| L258 | `loadModuleForUid(targetUid, 'product', normalizedApplicationTime)` | （同上不动） |
| L259 | `loadModuleForUid(targetUid, 'ops', normalizedApplicationTime)` | （同上不动） |
| L296 | `loadModuleForUid(targetUid, moduleName, normalizedApplicationTime)` | （同上不动） |

`loadModuleForUid` 函数体改动（L212）：

```jsx
async function loadModuleForUid(targetUid, moduleName, normalizedApplicationTime) {
    // ... 函数体内只改 analyzeModule 调用一行：
    const payload = await analyzeModule(targetUid, moduleName, normalizedApplicationTime, country);
    // 后续逻辑不变
}
```

> 因为 `country` 是 app.jsx 顶层 useState（Task 3.7），`loadModuleForUid` 是同文件内的闭包函数，可直接访问 `country`。所以 `loadModuleForUid` 函数签名**不需要**加 country 参数，只需在内部传给 `analyzeModule`。

### Task 3.11：单元测试 — cache key 国家维度隔离

文件：`tests/test_orchestrator_country_cache.py`（新建）

```python
"""验证同 uid/module/application_time 下，mx 和 th cache 不互相命中（v6.1 C2）。"""

from app.services.orchestrator import shared_orchestrator as orchestrator


def test_module_cache_isolated_by_country():
    orchestrator._set_cached("u1", "app", None, "mx", {"data": "mx_payload"})
    assert orchestrator._get_cached("u1", "app", None, "mx") == {"data": "mx_payload"}
    assert orchestrator._get_cached("u1", "app", None, "th") is None

    orchestrator._set_cached("u1", "app", None, "th", {"data": "th_payload"})
    assert orchestrator._get_cached("u1", "app", None, "mx") == {"data": "mx_payload"}
    assert orchestrator._get_cached("u1", "app", None, "th") == {"data": "th_payload"}

    # 清理（避免污染其他测试）
    orchestrator._module_cache.pop(orchestrator._cache_key("u1", "app", None, "mx"), None)
    orchestrator._module_cache.pop(orchestrator._cache_key("u1", "app", None, "th"), None)
```

### Task 3.12：mx 全量回归 + 前端 smoke

```powershell
python -m pytest tests/ -v --tb=short
```

前端手动 smoke：
1. `localhost:8000/?country=mx`：跑 mx 真实 UID → 4 tab 全部正常 + Network 看 `country=mx`，Credit tab 显示 score_band 等级 + account_type 列表
2. `localhost:8000/?country=th`：跑 th UID → Network 看 `country=th`，**Credit tab 显示 5 段风控特征 markdown（不显示 score_band / account_type）**
3. 切换国家 → confirm modal → analysisResults / moduleStates 全部清空，无 stale UI

### Phase 3 出口

- [ ] `app/schemas/request.py` import Literal + AnalyzeRequest.country 字段（C5）
- [ ] `/api/analyze-module` GET query 加 country 并透传 orchestrator
- [ ] `/api/analyze` `analyze_stream.py` `analyze.py::analyze_users_from_file` `batch_service.py` 4 处全部透传 country（M1/M2/M4）
- [ ] orchestrator analyze / analyze_module / _run_single_module / _analyze_comprehensive_module / _analyze_advisory_module 全链路透传 + cache key 5 处调用点全改（C2）
- [ ] **6 个 Skill** analyze() 全部透传 country_code（C1 + C4）
- [ ] **CreditRawData TypedDict 加 risk_features_record 字段**（C3 路径 Q）
- [ ] **CreditRunContext TypedDict 加 profile_mode 字段 + build_credit_run_context 注入 profile_mode**
- [ ] **CreditDataProvider.fetch / CreditFeatureBuilder.build / CreditDecisionEngine.decide 三层按 profile_mode 二分支**（C3）
- [ ] **CreditExplainer.__init__ 接受 prompt_paths: dict[str, Path]**（C3）
- [ ] **新建 `app/prompts/credit_profile_th_prompt.md`**（5 段结构）
- [ ] 前端 app.jsx 顶层 country state + URL 持久化 + resetAnalysisStateForCountry()
- [ ] api.js 4 个 fetch 函数透传 country（M4）
- [ ] app.jsx loadModuleForUid 调用 analyzeModule 时传 country（M3）
- [ ] tests 新增 7 个用例（test_th_country_packs.py 7 个 — Phase 2）+ 5 个用例（test_credit_profile_mode_branching.py 5 个）+ 1 个用例（test_orchestrator_country_cache.py 1 个）
- [ ] mx 回归通过数 ≥ N₀_passed + 13（7 + 5 + 1），且失败 case 集合 ⊆ N₀_failed_cases
- [ ] 前端 Network 抓包 mx UID 走 country=mx，th UID 走 country=th
- [ ] Credit tab 在 th 模式下不显示 score_band / account_type，显示 5 段风控特征 markdown

### Phase 3 commit

```powershell
git add `
    app/schemas/request.py `
    app/api/analyze.py `
    app/api/analyze_module.py `
    app/api/analyze_stream.py `
    app/services/batch_service.py `
    app/services/orchestrator.py `
    app/runtime_skills/app_profile_agent.py `
    app/runtime_skills/behavior_profile_agent.py `
    app/runtime_skills/credit_profile_agent.py `
    app/runtime_skills/comprehensive_agent.py `
    app/runtime_skills/product_advice_agent.py `
    app/runtime_skills/ops_advice_agent.py `
    app/runtime_skills/credit_profile/contracts.py `
    app/runtime_skills/credit_profile/data_access.py `
    app/runtime_skills/credit_profile/feature_builder.py `
    app/runtime_skills/credit_profile/decision_engine.py `
    app/runtime_skills/credit_profile/explainer.py `
    app/prompts/credit_profile_th_prompt.md `
    app/static/js/app.jsx `
    app/static/js/services/api.js `
    tests/test_orchestrator_country_cache.py `
    tests/runtime_skills/__init__.py `
    tests/runtime_skills/test_credit_profile_mode_branching.py
git commit -m "[plan-05][P3][mx-touched] country_code 6-Skill 全链路透传 + cache 5 处调用点 + Credit 双模式（路径 Q：CreditRawData 扩展 + Explainer 双模板 + FeatureBuilder 二分支）"
```

> ⚠️ **若 Task 3.6.D/E 触发了 build_comprehensive_run_context / build_product_advice_run_context / build_ops_advice_run_context 的扩展，这三个 contracts.py 文件也需 git add**。Claude Code 实施时按实际改动补 add 路径。

---

## Phase 4 — 验收 + PLANNING.md 同步 + v6.1 hard-gate（独立脚本） + [complete]

### Task 4.1：mx 全量回归

```powershell
python -m pytest tests/ -v --tb=short
```

**STOP**：通过数必须 ≥ N₀_passed + 13（Phase 2 的 7 + Phase 3 的 5 + 1）。
**且**：失败 case 集合 ⊆ N₀_failed_cases（即不允许出现新的 failed case，pre-existing 失败可保留 — 详见 `.reports/plan-05-baseline-tests.txt`）。

### Task 4.2：th E2E 抽样（人工）

- 浏览器切到 Thailand → 输入 th UID（或 mock）
- App tab：显示 "Thailand"
- Behavior tab：联系渠道 LINE
- **Credit tab（v6.1 关键验证）**：source_display_name 显示「风控特征聚合表（泰国）」+ **不显示** score_band/account_type + 显示 5 段 markdown + 哨兵值「无活体分」/「无逾期」/「无记录」有正确语义解读
- Comprehensive tab：summary 引用上述无矛盾，**不**生成虚拟信用等级

### Task 4.3：修改 `PLANNING.md` 第 341 行

修改为：

```
- **国别白名单**：V1 实际集合 `country_code ∈ ["mx", "th"]`，Pydantic schema 强制（`Literal["mx", "th"]`）。新增国别需：(1) 在 `app/country_packs/{cc}/` 落地三个 dataclass 单例（app_profile / behavior_profile / credit_profile），其中 credit_profile 必须显式声明 `profile_mode`（"buro" 或 "risk_features"）；(2) 在 `app/country_packs/{X}_profile.py` 注册表加 1 行；(3) 在 `docs/skills/orchestrator/{cc}.md` 落地规则文件；(4) 同步扩展前后端 Literal 国家集合；(5) 若新国家走非 buro 业务模型，需新建对应 prompt 模板（如 `app/prompts/credit_profile_{cc}_prompt.md`）+ 在 explainer / feature_builder / decision_engine 内加 profile_mode 分支。
```

### Task 4.4（M5 修订）：v6.1 hard-gate（独立 Python 脚本 + PowerShell grep）

> **检查范围 = `app/country_packs/th/` 与 `app/runtime_skills/credit_profile/`**（与 Phase 0 Task 0.5 范围 `docs/specs/` 不同）

#### 4.4.A：新建 `scripts/v6_hard_gate.py`（M5 修订 — 抽出独立脚本）

```python
"""v6.1 hard-gate：profile_mode + 路径 Q 双模式六点运行时断言。

用法：python scripts/v6_hard_gate.py
退出码：0 = 通过；非 0 = 失败
"""

from __future__ import annotations

import sys


def main() -> int:
    from app.country_packs.credit_profile import load_credit_country_pack
    from app.runtime_skills.credit_profile.contracts import build_credit_run_context

    # === TH 路径六点断言 ===
    p_th = load_credit_country_pack("th")
    assert p_th.profile_mode == "risk_features", f"TH must be risk_features, got {p_th.profile_mode!r}"
    assert p_th.source_display_name == "风控特征聚合表（泰国）", f"TH source mismatch: {p_th.source_display_name!r}"
    assert p_th.score_band_thresholds == (), f"TH score_band must be empty, got {p_th.score_band_thresholds!r}"
    assert p_th.account_type_labels == {}, f"TH account_type must be empty, got {p_th.account_type_labels!r}"
    assert p_th.risk_feature_labels, "TH risk_feature_labels must be non-empty"
    assert p_th.sentinel_values, "TH sentinel_values must be non-empty"

    # === MX 路径行为零变更断言 ===
    p_mx = load_credit_country_pack("mx")
    assert p_mx.profile_mode == "buro", f"MX must be buro, got {p_mx.profile_mode!r}"
    assert p_mx.score_band_thresholds[0] == ("A", 700), "MX score_band changed (regression!)"
    assert p_mx.account_type_labels.get("CC") == "信用卡", "MX account_type changed (regression!)"

    # === 路径 Q：context 必须含 profile_mode ===
    ctx_th = build_credit_run_context("u_test", country_code="th")
    ctx_mx = build_credit_run_context("u_test", country_code="mx")
    assert ctx_th.get("profile_mode") == "risk_features", f"TH context profile_mode wrong: {ctx_th.get('profile_mode')!r}"
    assert ctx_mx.get("profile_mode") == "buro", f"MX context profile_mode wrong: {ctx_mx.get('profile_mode')!r}"

    print("✅ v6.1 hard-gate 全部断言通过 — TH risk_features + MX buro + 路径 Q profile_mode 注入正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

#### 4.4.B：执行三 Gate

```powershell
# Gate 1：禁止 NCB / DEV-PLACEHOLDER 残留（范围 = app/country_packs/th/ + app/runtime_skills/credit_profile/）
$bad = Select-String `
    -Path app/country_packs/th/, app/runtime_skills/credit_profile/ `
    -Pattern "National Credit Bureau|NCB|DEV-PLACEHOLDER" `
    -Recurse
$count = ($bad | Measure-Object).Count
Write-Host "Gate 1 (NCB/DEV-PLACEHOLDER 残留行数): $count"
if ($count -gt 0) {
    $bad | Format-Table Path,LineNumber,Line
    Write-Host "❌ Gate 1 失败：TH risk_features 路径不允许残留 NCB / DEV-PLACEHOLDER 语义"
    exit 1
}
Write-Host "✅ Gate 1 通过"

# Gate 2：profile_mode + 路径 Q 运行时六点断言（独立脚本）
python scripts/v6_hard_gate.py
if ($LASTEXITCODE -ne 0) { Write-Host "❌ Gate 2 失败"; exit 1 }

# Gate 3：th prompt 模板 5 段结构验证
$th_prompt = "app/prompts/credit_profile_th_prompt.md"
if (-not (Test-Path $th_prompt)) {
    Write-Host "❌ Gate 3 失败：$th_prompt 不存在"
    exit 1
}
$prompt_content = Get-Content $th_prompt -Raw
$sections = @("身份核验", "申请行为", "还款履约", "社交关系", "规则命中")
$missing = $sections | Where-Object { $prompt_content -notmatch $_ }
if ($missing.Count -gt 0) {
    Write-Host "❌ Gate 3 失败：prompt 模板缺失 section: $($missing -join ', ')"
    exit 1
}
Write-Host "✅ Gate 3 通过 — th prompt 模板 5 段结构齐全"
```

**STOP（最严格）**：三 Gate 必须全绿才进 Task 4.5。

### Task 4.5：[complete] commit

```powershell
git add PLANNING.md scripts/v6_hard_gate.py
git commit -m "[plan-05][P4][complete] th risk-feature country pack 上线 — PLANNING.md 国别白名单同步 + v6.1 三 Gate（NCB 残留禁令 + profile_mode 双模式 + 路径 Q + th prompt 模板）通过"
```

### Phase 4 出口

- [ ] mx 全量回归通过数 ≥ N₀_passed + 13，且失败 case 集合 ⊆ N₀_failed_cases
- [ ] th E2E 抽样 4 tab 全部正常（**Credit tab 显示 5 段风控特征 markdown**）
- [ ] PLANNING.md 第 341 行修正为 V1 实际集合 `["mx", "th"]` + profile_mode 流程说明
- [ ] v6.1 三 Gate 全部通过（NCB 残留禁令 / profile_mode + 路径 Q 运行时断言 / prompt 模板 5 段结构）
- [ ] [complete] commit message 已落

---

## 附录 A：执行记录

| 节点 | 时间 | 通过测试数 | git commit |
|---|---|---|---|
| Phase 0 baseline N₀ | (待填) | (待填) | n/a |
| Phase 1 commit | (待填) | n/a | (待填) |
| Phase 2 commit (≥ N₀+7) | (待填) | (待填) | (待填) |
| Phase 3 commit (≥ N₀+13) | (待填) | (待填) | (待填) |
| Phase 4 commit | (待填) | (待填) | (待填) |
| v6.1 Gate 1 (NCB 残留行数) | (待填) | n/a | n/a |
| v6.1 Gate 2 (profile_mode + 路径 Q 断言) | (待填) | n/a | n/a |
| v6.1 Gate 3 (prompt 模板 5 段) | (待填) | n/a | n/a |

---

## 附录 Z：v3 → v4 → v5 → v6 → v6.1 决策记录

### Z.1 v3 BLOCKED 原因

1. v3 `BaseCountryPack` 抽象层与既有 `_X_COUNTRY_PACKS` 注册表正交但冗余 → 架空既有架构
2. Plan 03/05 国别白名单冲突未处理（拉美 6 vs 亚洲 5，交集仅 {mx, th}）
3. v3 Schema Adapter 类层级把字段适配分散到 4 个地方
4. Phase 数 6 违反「每 Plan ≤4 commit」教训
5. 时机错误：4 BUG 未修复 + mx StarRocks 数据未导入

### Z.2 v4 决策（路径 A）

- 走路径 A：复用既有注册表 + dataclass 单例
- 删除 BaseCountryPack / TargetCountry / get_country_pack / Schema Adapter / Skill 子类
- Phase 数 6 → 5（4 个实施 commit）
- PLANNING.md 第 341 行修正为 V1 实际集合 `["mx", "th"]`

### Z.3 v4 BLOCKED for Claude Code 原因

- v4 §2 字段矩阵 4 张表全空 → Phase 1 阻塞用户提供 schema → Claude Code 无法 self-contained 执行

### Z.4 v5 BLOCKED 原因（业务建模错误）

- v5 把 TH credit 错认为 NCB 信用局报告
- 设计了 FICO 风格 placeholder（A/B/C/D + 9 项 account_type_labels）
- DEV-PLACEHOLDER hard-gate 方向是「上线前替换为 NCB 真值」
- **实际 TH 数据是公司内部反欺诈风控聚合表**（11 维特征），不存在 NCB / FICO 模型 → v5 整套 placeholder 是业务建模错误
- 用户审核 csv 实测后改方向

### Z.5 v6 决策（A1 双模式）

- 走路径 A1：CreditCountryPack 加 3 个显式字段（`profile_mode` / `risk_feature_labels` / `sentinel_values`）
- TH `profile_mode = "risk_features"`，MX `profile_mode = "buro"`（默认）
- TH `score_band_thresholds = ()` / `account_type_labels = {}` 永久空（不是 placeholder）
- TH `source_display_name = "风控特征聚合表（泰国）"`
- explainer / feature_builder / decision_engine 按 `pack.profile_mode` 分支
- 新建 `app/prompts/credit_profile_th_prompt.md`（5 段：身份核验/申请行为/还款履约/社交关系/规则命中）
- Phase 4 hard-gate 三 Gate
- Plan / commit 节奏保 v5（5 Phase / 4 commit）

### Z.6 v6.1 决策（路径 Q + 5 CRITICAL 代码对齐）

| 修订点 | v6 → v6.1 |
|---|---|
| **C1**：Skill 透传 | 3 个 → **6 个**（+ comprehensive / product_advice / ops_advice） |
| **C2**：cache key 调用点 | 仅给方法签名 → 列出 5 处调用点全清单（_run_single_module ×1 + _analyze_comprehensive_module ×3 + _analyze_advisory_module ×2） |
| **C3**：profile_mode 分支实现 | 伪代码 `_read_template()`（不存在） → **路径 Q**：CreditRawData 加 `risk_features_record` 字段 + CreditRunContext 加 `profile_mode` 字段 + CreditExplainer.__init__ 接受 `prompt_paths: dict[str, Path]` + DataProvider/FeatureBuilder/DecisionEngine 三层按 context["profile_mode"] 二分支（mx 走 _build_buro_features 行为零变更，th 走新 _build_risk_features） |
| **C4**：Skill 同构注释 | 一句"3 Skill 同构"带过 → **拆 3 段独立 patch**（App 已传 application_time / Behavior + Credit 仅加 country_code） |
| **C5**：schemas import | 漏 import Literal → 补 `from typing import List, Literal, Optional` |
| **M1-M5** | analyze_stream / batch_service / app.jsx 行号 / analyzeByFile / hard-gate Python 脚本 全部精确化 |
| **m1-m3** | Phase 2 commit 精确文件清单 / NCB gate 范围注释 / pytest collection __init__.py 注释 |

### Z.7 既有架构对齐

| 维度 | 既有架构 | v6.1 决策 |
|---|---|---|
| 注册位置 | `_X_COUNTRY_PACKS: dict[str, XCountryPack]` | 沿用 |
| 单例形式 | `MX_X_COUNTRY_PACK = XCountryPack(country_code="mx", ...)` | th 同构 |
| Skill 路由 | country-agnostic + `build_X_run_context(country_code)` | 保持 + **6 Skill 全覆盖透传** |
| 字段适配 | `data_access.py` + `XCountryPack` 业务字段 | + profile_mode 分支落点 4 + 路径 Q CreditRawData 扩展 |
| 工厂函数 | `load_X_country_pack(country_code) -> XCountryPack` | 沿用（不引入 enum） |
| dataclass | mx CreditCountryPack 9 字段 | mx 12 字段（向后兼容默认值） |
| TypedDict | mx CreditRawData 6 字段 | **7 字段**（+ risk_features_record，路径 Q） |
| Context dict | mx CreditRunContext 8 键 | **9 键**（+ profile_mode，路径 Q） |
| explainer prompt | 单一 prompt_path | **prompt_paths: dict[str, Path]**（buro / risk_features 两键） |

> v6.1 完全对齐既有架构 + 显式声明业务模型（profile_mode）+ 突破 contracts 类型分离两条业务路径（路径 Q），解决 v5 业务建模错误 + v6 代码对齐缺陷，Claude Code 插件可自动 / 半自动执行 5 个 Phase。
