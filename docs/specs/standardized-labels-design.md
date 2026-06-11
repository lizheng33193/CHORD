# Standardized Labels — Design Doc

> 状态：Draft（Step 1）
> 关联任务：把 6 个 Skill 的 structured_result 映射到方案文档 §九 标签体系
> 关联文件：
> - 方案 §九：`data_acquisition_agent/demo0/基于大模型的用户画像与客群分层方案（墨西哥市场）.md`
> - 现有 schema：`app/schemas/final_response.py`、`app/schemas/{app,behavior,credit,comprehensive}_profile.py`、`app/schemas/{product,ops}_advice.py`
> - 现有编排：`app/services/orchestrator.py`

---

## 1. 背景与目标

### 1.1 背景
当前系统已有 6 个 Skill（`app_profile` / `behavior_profile` / `credit_profile` / `comprehensive_profile` / `product_advice` / `ops_advice`），各自产出形状不一的 `structured_result`：
- `app_profile` 顶层有 `risk_assessment` / `financial_maturity` / `consumption_profile` 等强类型块；
- `behavior_profile` / `credit_profile` 关键级别藏在 `metrics: dict[str, Any]` 内；
- `comprehensive_profile` 把 `segment` / `confidence_level` 写进 `metrics`；
- `product_advice` / `ops_advice` 输出策略子块（`outreach_channel.primary` 等）。

业务方案 §九 定义了一套面向运营的统一标签体系（4 大类 + 元数据，共 17 维度）。当前 API 响应没有"标签层"统一出口，业务侧需在多个 Skill 顶层取数，且字段路径分散、有 fallback。

### 1.2 目标
- 在 `UserAnalysisResult` 上新增一个稳定形状的 `standardized_labels` 顶层字段；
- 由独立 `label_builder` 模块负责跨 Skill 字段抽取 + 派生 + fallback；
- **零侵入**：不修改任何 Skill 的 assembler / decision_engine / explainer，不修改 6 个 Skill 的 schema；
- 17 个 key **始终存在**，不可得固定为 `"unknown"`，绝不编造业务值。

### 1.3 非目标
见 §11。

---

## 2. 标准标签结构

### 2.1 顶层形状
按 4 大类 + 元数据分 5 组，每组下挂若干维度。**纯值结构**——叶子直接是字符串值，不嵌 `{value, source, ...}`。

### 2.2 JSON 示例（一个三维完整用户）
```json
{
  "basic_attributes": {
    "age_band": "unknown",
    "occupation_type": "unknown",
    "banking_level": "medium",
    "geo_region": "unknown"
  },
  "risk_labels": {
    "multi_loan_risk": "medium",
    "credit_stability": "medium_high",
    "debt_pressure": "medium",
    "borrow_hunger": "high"
  },
  "behavior_labels": {
    "repayment_willingness": "medium_high",
    "credit_line_willingness": "high",
    "churn_risk": "low",
    "outreach_preference": "WhatsApp"
  },
  "value_labels": {
    "consumption_power": "high",
    "lifestyle": "S2 稳健经营客",
    "segment": "S2"
  },
  "metadata": {
    "profile_confidence": "high",
    "data_completeness": "三维完整"
  }
}
```

### 2.3 不变量（invariants）
- 5 个顶层分组 key 一定存在；
- 17 个叶子 key 一定存在；
- 任何叶子值类型为 `str`；
- 不可得字段固定 `"unknown"`，**不编造**年龄 / 职业 / 地理 / 任何业务级别；
- 整个对象为浅拷贝可序列化的 plain dict（不挂 Pydantic 实例）。

---

## 3. 字段映射表

| 标签大类 | 标签维度 | 标准 key | 来源 Skill | 来源字段路径 | source_status | 缺失默认值 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 基础属性 | 年龄层 | `age_band` | none | not_available | not_available | `"unknown"` | 上游无字段，固定 unknown |
| 基础属性 | 职业类型 | `occupation_type` | none | not_available | not_available | `"unknown"` | 同上 |
| 基础属性 | 银行化程度 | `banking_level` | app_profile | `structured_result.financial_maturity.level` | available | `"unknown"` | 值域：unknown/low/medium/high（schema 默认 unknown） |
| 基础属性 | 地理区域 | `geo_region` | none | not_available | not_available | `"unknown"` | 上游无字段 |
| 风险标签 | 多头风险 | `multi_loan_risk` | app_profile | `structured_result.risk_assessment.level` | available | `"unknown"` | 值域：low/medium/high |
| 风险标签 | 信用稳定性 | `credit_stability` | credit_profile | `structured_result.metrics.credit_stability_level` | available | `"unknown"` | 值域：low/medium/medium_high/high |
| 风险标签 | 负债压力 | `debt_pressure` | credit_profile | `structured_result.metrics.debt_pressure_level` | available | `"unknown"` | 值域：low/medium/medium_high/high |
| 风险标签 | 借贷饥渴度 | `borrow_hunger` | credit_profile | `structured_result.metrics.borrowing_urgency_level` → fallback `structured_result.metrics.borrowing_hunger_level` | available | `"unknown"` | 系统主 key 是 urgency；保留 hunger 作 fallback |
| 行为标签 | 还款意愿 | `repayment_willingness` | behavior_profile | `structured_result.metrics.repayment_willingness_level` | available | `"unknown"` | 值域：low/medium/medium_high/high；§九 原为 ★1-5，本期不做星级映射 |
| 行为标签 | 提额意愿 | `credit_line_willingness` | behavior_profile | `structured_result.metrics.product_sensitivity_level` | available | `"unknown"` | 系统名为产品敏感度，作为提额意愿近似（见 §10 风险项） |
| 行为标签 | 流失风险 | `churn_risk` | behavior_profile（主） / ops_advice（次） | `behavior_profile.structured_result.metrics.churn_risk_level` → fallback `ops_advice.structured_result.churn_warning.level` | available | `"unknown"` | behavior 是事实源；ops_advice 是建议层映射，仅在 behavior 缺失时回退 |
| 行为标签 | 触达偏好 | `outreach_preference` | ops_advice（主） / product_advice（次） / behavior_profile（底） | `ops_advice.structured_result.outreach_channel.primary` → fallback `product_advice.structured_result.recommended_channel.primary` → fallback `behavior_profile.structured_result.evidence.contact_preference.best_channel` | available | `"unknown"` | 三源同义，按 stage 优先级回退 |
| 价值标签 | 消费能力 | `consumption_power` | app_profile | `structured_result.consumption_profile.level` | available | `"unknown"` | 值域：unknown/low/medium/high |
| 价值标签 | 生活方式 | `lifestyle` | comprehensive_profile | `structured_result.persona` | available | `"unknown"` | 当前为聚合字符串，本期直接透出，不二次拆解 |
| 价值标签 | 客群归属 | `segment` | comprehensive_profile（主） / product_advice（次） / ops_advice（底） | `comprehensive_profile.structured_result.metrics.segment` → fallback `product_advice.structured_result.segment` → fallback `ops_advice.structured_result.segment` | available | `"unknown"` | 值域：S1-S6 |
| 元数据 | 画像置信度 | `profile_confidence` | comprehensive_profile | `structured_result.metrics.confidence_level` | available | `"unknown"` | 值域：high/medium/low |
| 元数据 | 数据完整度 | `data_completeness` | derived | 由 app/behavior/credit 三个 `status` 派生（见 §4） | derived | `"unknown"` | 见 §4 |

source_status 取值集合：`available` / `derived` / `not_available` / `unknown`。

合计：13 available + 1 derived + 3 not_available = 17。

---

## 4. data_completeness 派生规则

输入：`app_profile.structured_result.status` / `behavior_profile.structured_result.status` / `credit_profile.structured_result.status`。

定义"ok"为 `status == "ok"`（与现有 Skill assembler 一致，`data_missing` / `model_unavailable` 等其它值均视为非 ok）。

派生表（按优先级匹配，命中即返回）：

| 条件 | 输出 |
| --- | --- |
| app ok 且 behavior ok 且 credit ok | `"三维完整"` |
| app ok 且 behavior ok 且 credit 非 ok | `"缺征信"` |
| 只有 app ok（behavior 与 credit 均非 ok） | `"仅APP数据"` |
| 其它（含 app 非 ok 等所有剩余情况） | `"不完整"` |

**说明**：
- 只读 app_profile / behavior_profile / credit_profile 三个画像 Skill 的 status，不参考 product_advice / ops_advice，因为后者是 stage 2 advisory，并非数据完整度的事实来源。
- comprehensive 不参与派生，因其本身依赖前三者。
- 输出值是中文枚举，对齐方案 §九 的描述。
- 顶层异常 / 无法判断 → `"unknown"`（见 §5.4 / §9.2）；正常可判断但三者均非 ok → `"不完整"`。

---

## 5. `label_builder.py` 接口设计

### 5.1 文件位置
`app/services/label_builder.py`，与 `orchestrator.py` 同层。单文件，预计 ~150 行。

### 5.2 公共接口

```python
def build_standardized_labels(
    *,
    app_profile: dict | None,
    behavior_profile: dict | None,
    credit_profile: dict | None,
    comprehensive_profile: dict | None,
    product_advice: dict | None,
    ops_advice: dict | None,
) -> dict[str, Any]:
    """根据 6 个 AgentOutput dict 组装 17 维度标准化标签。

    输入：每个参数是 AgentOutput 的 dict 形式（含 summary / structured_result /
          charts / report_markdown），允许为 None。
    输出：5 分组 17 key 的纯值 dict（见 §2.2）。
          任何分支异常或字段缺失，对应叶子返回 "unknown"，整体仍保持完整 17 key。
    """
```

仅 keyword-only 参数，避免位置参数误传。

### 5.3 私有 helper

| helper | 职责 |
| --- | --- |
| `_structured(agent_output: dict \| None) -> dict` | 安全取 `agent_output["structured_result"]`，非 dict 返回 `{}` |
| `_is_ok(agent_output: dict \| None) -> bool` | `_structured(...).get("status") == "ok"` |
| `_get_path(d: dict, path: list[str], default: str = "unknown") -> str` | 沿路径取值，路径中断或最终值为空字符串 / None 返回 default；强制 `str(...)` |
| `_first_non_empty(*candidates: str) -> str` | 返回第一个非空且非 `"unknown"` 的字符串，全空则返回 `"unknown"` |
| `_derive_data_completeness(app, behavior, credit) -> str` | 实现 §4 派生表 |
| `_default_labels() -> dict[str, Any]` | 返回 17 key 全 `"unknown"`（含 `data_completeness` = `"unknown"`）的兜底 dict，用于顶层异常 fallback |

### 5.4 异常策略
- 单维度抽取异常 → 落到 `"unknown"`（局部降级）；
- 顶层 `build_standardized_labels` 用一层 `try/except` 包住主体，未捕获异常 → 返回 `_default_labels()`（整体降级），同时 `logger.warning` 记录原因。
- 不向上抛出异常，保证 orchestrator 调用必不中断响应。

### 5.5 与 Skill 的耦合度
- 只读 dict 字段路径，**不 import** 任何 `app/runtime_skills/...` 模块；
- 不 import Pydantic schema 类（避免循环依赖）；
- 仅依赖标准库 + 项目 logger。

---

## 6. orchestrator 接入点

修改 `app/services/orchestrator.py` 的 `_analyze_single_user`：

**改动位置**：紧接 `self.registry.run_all(...)` 之后、`UserAnalysisResult(...)` 构造之前。

**改动伪代码**：
```python
all_results = self.registry.run_all(...)

standardized_labels = build_standardized_labels(
    app_profile=all_results.get("app_profile"),
    behavior_profile=all_results.get("behavior_profile"),
    credit_profile=all_results.get("credit_profile"),
    comprehensive_profile=all_results.get("comprehensive_profile"),
    product_advice=all_results.get("product_advice"),
    ops_advice=all_results.get("ops_advice"),
)

return UserAnalysisResult(
    uid=uid,
    app_profile=...,
    ...
    standardized_labels=standardized_labels,
)
```

**约束**：
- 不改 Skill 执行顺序；
- 不改 SkillRegistry；
- 不改任何 Skill 的输入/输出形状；
- 新增 import：`from app.services.label_builder import build_standardized_labels`。

预计净增代码量：~10 行。

---

## 7. Schema 变更

**唯一改动**：`app/schemas/final_response.py` 的 `UserAnalysisResult` 新增一个可选字段：

```python
class UserAnalysisResult(BaseModel):
    uid: str
    app_profile: AgentOutput
    behavior_profile: AgentOutput
    credit_profile: AgentOutput
    comprehensive_profile: AgentOutput
    product_advice: AgentOutput | None = None
    ops_advice: AgentOutput | None = None
    standardized_labels: dict[str, Any] | None = None   # ← 新增
```

**不引入** `StandardizedLabels` Pydantic 强类型模型。理由：
- 17 key 形状由 `label_builder` 构造层保证，下游消费方按 dict 读；
- 引入强类型会让"动态 fallback / 局部 unknown"的逻辑被 schema 强校验拒绝，得不偿失；
- Pydantic v2 `dict[str, Any]` 与 v1 兼容。

向后兼容：默认 `None`，既有响应消费方（前端 / 测试 / 报告渲染器）若不读该字段，不受影响。

---

## 8. 测试策略

### 8.1 测试文件
新建 `tests/test_standardized_labels.py`，使用 pytest，纯单测（mock AgentOutput dict，不依赖 repository / LLM）。

### 8.2 用例分组

**A. 正常路径（happy path）**
- A1：6 个 Skill 全 ok，构造一份典型 fixture → 验证 17 key 全部为预期非 unknown 值，且分组 key 齐全。

**B. 数据缺失降级**
- B1：credit 缺失（status="data_missing"）→ `credit_stability` / `debt_pressure` / `borrow_hunger` = `"unknown"`，`data_completeness` = `"缺征信"`。
- B2：仅 app ok，behavior + credit 缺失 → 行为/风险维度全 unknown，`data_completeness` = `"仅APP数据"`。
- B3：app 缺失 → `data_completeness` = `"不完整"`。

**C. fallback 链验证（3 组）**
- C1：`borrow_hunger`：metrics 没有 `borrowing_urgency_level`，但有 `borrowing_hunger_level` → 取 hunger 值。
- C2：`churn_risk`：behavior metrics 缺 `churn_risk_level`，ops_advice `churn_warning.level` 有值 → 取 ops_advice。
- C3：`outreach_preference`：ops_advice `outreach_channel.primary` 缺，product_advice `recommended_channel.primary` 缺，但 behavior `evidence.contact_preference.best_channel` 有值 → 取 behavior。

**D. not_available 永久 unknown**
- D1：无论输入如何，`age_band` / `occupation_type` / `geo_region` 始终为 `"unknown"`。

**E. 顶层异常兜底**
- E1：传入异常输入（如 `app_profile={"structured_result": "not_a_dict"}`）→ 返回完整 17 key 的兜底 dict，不抛异常。

**F. schema 兼容性**
- F1：把 build 出的 dict 塞进 `UserAnalysisResult(... standardized_labels=...)` 构造能通过 Pydantic 校验。
- F2：`UserAnalysisResult` 不传 `standardized_labels` 时仍能构造（默认 None）。

### 8.3 测试不做的事
- 不调用 real LLM；
- 不连接数据库；
- 不读 `data/` 真实数据；
- 不跑 orchestrator 端到端（端到端兼容性由 F1 + 既有 orchestrator 测试覆盖即可）。

---

## 9. 性能与失败模式

### 9.1 性能
- 纯内存 dict 字段读取，单次调用 O(1)（17 维度 + 几次 fallback 查找，常数次字典访问）；
- 无 I/O，无锁，无 LLM 调用；
- 单 uid 增量耗时预估 < 1 ms，对 orchestrator 整体耗时（当前 ~163s/uid 含 LLM）影响可忽略。

### 9.2 失败模式与降级矩阵

| 失败模式 | label_builder 行为 | 用户感知 |
| --- | --- | --- |
| 单字段路径不存在 / None / 空字符串 | 该叶子 → `"unknown"` | 该维度显示 unknown，其它 16 维正常 |
| 单 Skill `structured_result` 非 dict | 该 Skill 相关维度全 unknown | 局部降级 |
| 输入 None（某 Skill 未运行） | 该 Skill 相关维度全 unknown | 局部降级 |
| 顶层未捕获异常 | 返回 `_default_labels()` + `logger.warning` | 全部 unknown，但 17 key 形状仍完整 |
| `data_completeness` 派生失败 | 该 key → `"unknown"` | 元数据降级 |

### 9.3 不破坏既有契约
- 即便 `standardized_labels` 全 unknown，`UserAnalysisResult` 仍能完整序列化；
- 不影响其它 Skill 的输出；
- 不影响响应耗时可观测性。

---

## 10. 风险与未决项

| ID | 风险 / 未决项 | 影响 | 缓解 |
| --- | --- | --- | --- |
| R1 | `product_sensitivity_level` 与"提额意愿"是近似映射，不完全等价 | 业务侧解读偏差 | 在 Design Doc / 字段映射表注明；后续如需精确"提额意愿"，单独建模而非改本模块 |
| R2 | `comprehensive.persona` 是聚合字符串（如 `"S2 / high-activity / balanced-engagement / low-risk"`），与 §九 "城市白领 / 蓝领务工" 类自然语言生活方式不严格对齐 | `lifestyle` 标签可读性偏弱 | 本期直接透出原值；后续如需自然语言生活方式，由 explainer 增强而非本模块 |
| R3 | 17 维标签中 3 维当前 not_available（年龄层 / 职业类型 / 地理区域） | 基础属性缺 3 维，运行时均输出 unknown | 上游补全后只需新增映射行，不破坏接口 |
| R4 | 后续若 behavior_profile / credit_profile schema 补全（TASK.md "P1: 补全 Behavior/Credit Pydantic Schema"），关键级别可能升到 structured_result 顶层 | 当前路径需更新 | 仅改 `label_builder.py` 内的路径常量；不影响调用方 |
| R5 | 未引入强类型 `StandardizedLabels` 模型 | IDE 自动完成 / mypy 推断弱 | 本期 YAGNI；如形状稳定后再引入 |
| R6 | `data_completeness` 中文枚举值与前端 i18n 策略可能冲突 | 国际化时需额外映射 | 当前墨西哥单市场，YAGNI；多市场时引入 country pack |

---

## 11. 非目标（Non-goals）

明确不在本 Design Doc 范围内的事：

- ❌ 不补全 `behavior_profile` / `credit_profile` 的 Pydantic schema（见 TASK.md P1）；
- ❌ 不修改 6 个 Skill 任何文件（assembler / decision_engine / explainer / contracts / agent 入口 / schema）；
- ❌ 不做前端渲染 / UI 集成；
- ❌ 不做国家差异化（country pack）；
- ❌ 不调用 real LLM（label_builder 是纯规则模块）；
- ❌ 不读取 `data/` 下任何真实数据文件；
- ❌ 不写自动迁移脚本 / 不做版本兼容层（默认值 None 已保证向后兼容）；
- ❌ 不引入新依赖（仅用标准库 + 已有 logger）；
- ❌ 不修改 `data_acquisition_agent/` 下任何文件；
- ❌ 不做星级 ★1-5 转换（§九 还款意愿原为 ★1-5，本期保留 low/medium/high 原值）。
