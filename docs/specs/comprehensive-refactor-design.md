# Comprehensive Profile 六步管线重构设计

**Plan 路径预留**：`docs/plans/comprehensive-refactor-plan.md`（本设计确认后再写）
**关联 TASK.md 条目**：P1 拆分 Comprehensive 为六步管线
**关联 PLANNING.md 章节**：六步管线参考结构（与 `app_profile/` 对齐）
**日期**：2026-04-28

## 1. 背景与动机

`app/runtime_skills/comprehensive_agent.py` 当前 512 行单文件，把上游消费、特征抽取、规则判断、LLM 调用、结果组装全塞在一个类中。同目录下 `app_profile/`、`behavior/`、`credit/` 已按六步管线（contracts → data_access → feature_builder → decision_engine → explainer → assembler）拆分；只有 comprehensive 形态不一致。

不一致带来三个具体问题：
- 新人接手不知道照哪个写
- 后续给它加 Pydantic schema、补 model_trace 的改动没有清晰落点
- TASK.md P2 的产品/运营策略 Agent（stage≥1）没有"上游消费型 Skill"的现成模板

本次重构目标是**把 comprehensive 对齐到六步管线，但不动外部 schema 和 BaseSkill.analyze 签名**。完成后，stage=1 的"上游消费型"Skill 就有了官方模板，P2 直接复用。

## 2. 范围

**In scope**
- 在 `app/runtime_skills/comprehensive/` 下新建六步管线文件（contracts / data_access / feature_builder / decision_engine / explainer / assembler）
- 重写 `app/runtime_skills/comprehensive_agent.py` 为薄入口（~50 行），仅编排六步
- 新增 `tests/test_comprehensive_phase1.py`，按 6 个 class 组织单测
- 不破坏 68 测试基线

**Out of scope**
- `ComprehensiveProfileStructuredResult` schema 字段重写（另一条 P1）
- behavior/credit 的对齐拆分（已经拆过，本次不动）
- prompt 模板大改（仅追加"哪个上游缺失"的提示句，且条件渲染）
- model_trace 在 behavior/credit 顶层的修复（属于 P0-2 验证发现的另一个独立任务）

## 3. 决策汇总（来自 5 轮澄清）

| # | 决策点 | 结论 |
|---|---|---|
| Q1 | data_access 是否保留 | **保留为薄壳**（`ComprehensiveUpstreamProvider`），与 app_profile 形态对齐，为 P2 stage≥1 Skill 打模板 |
| Q2 | 六个 TypedDict 字段切法 | **方案 A**：feature=数值抽取（含 score）；decision=if/elif 派生（含 segment/value/confidence/conflicts/persona_seed）；metrics 兼容现 schema 形状由 decision 拍平；upstream_summaries 由 feature_builder 抽取 |
| Q3 | LLM 与规则边界 | **保守边界**：segment / risk_level / value_signal_level / confidence_level / dimension_scores / conflict_count 规则强制；persona / summary 规则出 fallback、LLM 优先；conflict_explanations 按下标对齐润色（A1，条数顺序不变）；tags 规则出全集 + LLM 追加上限 N=3；reasoning 文本 LLM 唯一来源 |
| Q4 | 失败降级矩阵 | **三态保留**（ok / data_missing / model_unavailable）；data_missing 触发条件 `ok_count == 0`；部分上游失败仍调 LLM（prompt 中提示哪个上游缺失）；fallback_reason 自由字符串 + contracts.py 注释清单（C1） |
| Q5 | 文件骨架 | 与 app_profile 方法签名像素级对齐；`build_comprehensive_run_context` 放 contracts.py（C1）；测试 `tests/test_comprehensive_phase1.py` 按 6 class 组织（T1，含 UpstreamProvider）；Plan 拆 7 个 task（P1） |

## 4. 文件骨架

### 4.1 目录结构

```
app/runtime_skills/comprehensive/
├── __init__.py
├── contracts.py
├── data_access.py
├── feature_builder.py
├── decision_engine.py
├── explainer.py
└── assembler.py

app/runtime_skills/comprehensive_agent.py     # 重写为薄入口
tests/test_comprehensive_phase1.py             # 新建
```

### 4.2 六个 TypedDict（contracts.py）

```python
class ComprehensiveRunContext(TypedDict):
    uid: str
    country_code: str
    application_time: str
    trace_id: str
    enable_llm_explanation: bool
    language: str
    channel: str
    # 注：去掉 source_preference，因为不读源数据

class ComprehensiveUpstreamBundle(TypedDict):
    """data_access 产出：上游三个 Skill result 的健康解包"""
    uid: str
    country_code: str
    app_result: dict[str, Any]
    behavior_result: dict[str, Any]
    credit_result: dict[str, Any]
    app_status: str            # ok | missing | degraded
    behavior_status: str
    credit_status: str
    ok_count: int              # 0..3
    missing_modules: list[str] # 用于 prompt 提示
    data_status: str           # ok | data_missing（ok_count==0 → data_missing）
    errors: list[str]

class ComprehensiveFeatureBundle(TypedDict):
    """feature_builder 产出：纯数值/纯抽取，无判断"""
    uid: str
    country_code: str
    app_metrics: dict[str, Any]
    behavior_metrics: dict[str, Any]
    credit_metrics: dict[str, Any]
    app_score: int             # 1-5
    behavior_score: int
    credit_score: int
    upstream_summaries: dict[str, str]  # {app_profile, behavior_profile, credit_profile}
    feature_status: str        # "ok" | "error"
    errors: list[str]

class ComprehensiveDecisionResult(TypedDict):
    """decision_engine 产出：规则派生 + 给 explainer 的 seed"""
    uid: str
    country_code: str
    decision_status: str       # "ok" | "error"
    segment: str                          # S1..S6
    overall_risk_level: str
    value_signal_level: str
    confidence_level: str
    conflict_explanations: list[str]      # K 条 seed
    persona_seed: str
    tags_rule: list[str]                  # 规则全集
    metrics: dict[str, Any]               # 已拍平到现 schema 形状
    errors: list[str]

class ComprehensiveExplanationResult(TypedDict):
    """explainer 产出：LLM 文本可覆盖项"""
    uid: str
    country_code: str
    explanation_status: str               # ok | partial | skipped | model_unavailable
    used_llm: bool
    summary: str
    persona: str                          # 可空，空则用 persona_seed
    tags_addon: list[str]                 # LLM 追加的（上限 3，不与规则重复）
    conflict_explanations: list[str]      # 与 decision 同长度，逐条润色
    reasoning_texts: dict[str, str]
    model_trace: dict[str, Any]
    errors: list[str]

class ComprehensivePageResult(TypedDict):
    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str
```

`build_comprehensive_run_context()` 也放 contracts.py，签名与 `build_app_run_context` 对齐。

**fallback_reason 已知取值清单**（注释在 contracts.py，自由字符串不强枚举）：
```
""                                       # LLM 被采纳
"upstream_all_missing"                   # data_missing 路径
"model_mode_mock"
"empty_explanation_payload"
"schema_validation_failed: <exc>"
"<model_client status>"                  # 如 timeout / json_parse_error / http_<code>
```

### 4.3 类与方法签名

```python
# data_access.py
class ComprehensiveUpstreamProvider:
    def fetch(
        self, uid: str, context: ComprehensiveRunContext, *,
        app_result: dict[str, Any],
        behavior_result: dict[str, Any],
        credit_result: dict[str, Any],
    ) -> ComprehensiveUpstreamBundle: ...

# feature_builder.py
class ComprehensiveFeatureBuilder:
    def build(
        self, upstream: ComprehensiveUpstreamBundle,
        context: ComprehensiveRunContext,
    ) -> ComprehensiveFeatureBundle: ...
    # 私有：_build_app_score / _build_behavior_score / _build_credit_score
    #       _extract_metrics / _build_upstream_summaries

# decision_engine.py
class ComprehensiveDecisionEngine:
    def decide(
        self, feature_bundle: ComprehensiveFeatureBundle,
        upstream: ComprehensiveUpstreamBundle,
        context: ComprehensiveRunContext,
    ) -> ComprehensiveDecisionResult: ...

    def build_prompt_payload(
        self, feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
        upstream: ComprehensiveUpstreamBundle,
    ) -> dict[str, Any]: ...
    # 私有：_assign_segment / _build_conflict_explanations
    #       _derive_value_signal / _derive_confidence_level
    #       _build_persona_seed / _build_tags_seed / _flatten_metrics

# explainer.py
class ComprehensiveExplainer:
    def __init__(self, model_client: ModelClient, prompt_path: Path) -> None: ...
    def explain(
        self, uid: str,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
        upstream: ComprehensiveUpstreamBundle,
        prompt_payload: dict[str, Any],
        context: ComprehensiveRunContext,
    ) -> ComprehensiveExplanationResult: ...
    # 私有：_build_prompt / _load_prompt_template / _build_skipped_result
    #       _build_model_trace / _build_model_fallback_reason
    #       _has_meaningful_payload / _is_complete_payload
    #       _patch_conflict_explanations / _filter_tags_addon

# assembler.py
class ComprehensivePageAssembler:
    def __init__(self, model_client: ModelClient) -> None: ...
    # 仅读取 mode/model_name 用于 fallback 判断，不调用 generate_structured
    def build_missing_output(
        self, uid: str, context: ComprehensiveRunContext,
        upstream: ComprehensiveUpstreamBundle,
    ) -> ComprehensivePageResult: ...
    def build_fallback_structured(
        self, uid: str,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
    ) -> dict[str, Any]: ...
    def assemble(
        self, uid: str,
        fallback_structured: dict[str, Any],
        explanation_result: ComprehensiveExplanationResult,
    ) -> ComprehensivePageResult: ...
    # tags 合并：tags_rule + tags_addon（已由 explainer 去重截断），assembler 做最终 dedupe
```

### 4.4 入口（comprehensive_agent.py，重写后 ~50 行）

```python
class ComprehensiveProfileSkill(BaseSkill):
    name = "comprehensive_profile"
    stage = 1
    depends_on: list[str] = ["app_profile", "behavior_profile", "credit_profile"]

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client
        prompt_path = settings.resolve_path(f"{settings.prompt_dir}/comprehensive_prompt.md")
        self.upstream_provider = ComprehensiveUpstreamProvider()
        self.feature_builder = ComprehensiveFeatureBuilder()
        self.decision_engine = ComprehensiveDecisionEngine()
        self.explainer = ComprehensiveExplainer(model_client, prompt_path)
        self.assembler = ComprehensivePageAssembler(model_client)

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        context = build_comprehensive_run_context(uid, application_time=kwargs.get("application_time"))
        upstream = self.upstream_provider.fetch(
            uid, context,
            app_result=kwargs.get("app_profile_result", {}),
            behavior_result=kwargs.get("behavior_profile_result", {}),
            credit_result=kwargs.get("credit_profile_result", {}),
        )
        if upstream["data_status"] != "ok":
            return self.assembler.build_missing_output(uid, context, upstream)

        feature_bundle = self.feature_builder.build(upstream, context)
        decision_result = self.decision_engine.decide(feature_bundle, upstream, context)
        prompt_payload = self.decision_engine.build_prompt_payload(feature_bundle, decision_result, upstream)
        fallback_structured = self.assembler.build_fallback_structured(uid, feature_bundle, decision_result)
        explanation_result = self.explainer.explain(
            uid, feature_bundle, decision_result, upstream, prompt_payload, context,
        )
        return self.assembler.assemble(uid, fallback_structured, explanation_result)
```

## 5. 关键行为契约

### 5.1 LLM/规则边界

| 字段 | 产出方 | LLM 是否可覆盖 |
|---|---|---|
| `uid` / `status` / `model_trace` | 规则强制 | 否 |
| `metrics.segment` / `metrics.risk_level` / `metrics.value_signal_level` / `metrics.confidence_level` | decision_engine | 否 |
| `metrics.dimension_scores` / `metrics.conflict_count` | feature_builder + decision_engine | 否 |
| `metrics.conflict_explanations` | decision_engine 出 K 条 seed | 是（按下标对齐润色，K 不变、顺序不变） |
| `persona` | decision_engine 出 seed | 是（LLM 优先，空则用 seed） |
| `summary` | assembler 出 fallback | 是（LLM 优先） |
| `tags` | decision_engine 出全集 | 仅追加（上限 3，dedupe 后不与规则重复） |
| `upstream_summaries` | feature_builder 透传 | 否 |
| 各维度 `reasoning` | LLM 唯一来源 | 是（无 LLM 时为空） |

### 5.2 失败降级矩阵

| 触发条件 | structured.status | model_trace.fallback_reason | 调 LLM？ |
|---|---|---|---|
| ok_count == 0 | `data_missing` | `upstream_all_missing` | 否 |
| ok_count ≥ 1 + mode=mock | `ok` | `model_mode_mock` | 否 |
| ok_count ≥ 1 + LLM ok + payload 有效 | `ok` | `""` | 是 |
| ok_count ≥ 1 + LLM ok + payload 空 | `model_unavailable` | `empty_explanation_payload` | 是 |
| ok_count ≥ 1 + LLM 调用失败 | `model_unavailable` | `<model_client status>` | 是 |
| ok_count ≥ 1 + schema 校验失败 | `model_unavailable` | `schema_validation_failed: <exc>` | 是 |

**部分上游失败（ok_count=1 或 2）的处理**：
- status 仍为 `ok`，由 `metrics.confidence_level` 自然降为 medium/low 表达"信号完整度"
- prompt 中通过 `missing_modules` 字段明确告诉 LLM 哪个上游缺失（仅追加一句提示，不大改 prompt）
- 缺失上游的 metrics 视为空 dict，score 自动归 0

### 5.3 prompt 改动（最小化）

`app/prompts/comprehensive_prompt.md` 在 `## Input` 段尾追加一行（条件渲染：`missing_modules` 为空 list 时该行不输出）：

```
- missing_modules: <list of upstream module names that are missing or degraded; treat their metrics as absent rather than as low values>
```

无其他改动。

渲染方式由 Plan task 5 确定，本设计只约束语义：missing_modules 为空时该行不出现在最终 prompt 中。

## 6. 测试结构（tests/test_comprehensive_phase1.py）

按 **6 个 class** 组织：

```python
class TestComprehensiveUpstreamProvider:
    # 用 dict fixture 直接驱动，不需要 ModelClient
    # 覆盖：三上游全 ok / 部分失败（1-2 个 ok）/ 全失败 →data_missing /
    #       structured_result 不是 dict（异常输入容错）

class TestComprehensiveFeatureBuilder:
    # 用 ComprehensiveUpstreamBundle fixture 直接驱动，不 mock ModelClient
    # 覆盖：三上游全 ok / 部分缺失 / score 边界值

class TestComprehensiveDecisionEngine:
    # 用 ComprehensiveFeatureBundle fixture 驱动
    # 覆盖：S1-S6 六个 segment 分支 / conflict 触发条件 / metrics 拍平形状

class TestComprehensiveExplainer:
    # 用 mock ModelClient
    # 覆盖：mock 模式跳过 / LLM ok / payload 空 / schema 失败 /
    #       conflict 按下标对齐润色 / tags 追加上限 3 /
    #       missing_modules 空与非空两种 prompt 渲染分支

class TestComprehensivePageAssembler:
    # 不需要 ModelClient（只用 model_client.mode/model_name）
    # 覆盖：build_missing_output / build_fallback_structured /
    #       assemble 合并 LLM 文本 / status 收敛规则 /
    #       tags_rule + tags_addon 最终 dedupe

class TestComprehensiveAgentE2E:
    # 端到端：构造三个上游 result dict，跑完 analyze()
    # 覆盖：data_missing / 部分上游 + mock 模式 / 全 ok + mock 模式
```

**回归保证**：跑完 `python -m pytest tests/ -v`，68 测试全过。

## 7. Plan 拆分（7 个 task，每个 2-5 分钟）

| # | Task | 文件 | 验证命令 |
|---|---|---|---|
| 1 | 建 `comprehensive/` 目录骨架 + contracts.py 完整 TypedDict + `build_comprehensive_run_context` + `__init__.py` | contracts.py, __init__.py | `python -c "from app.runtime_skills.comprehensive import *"` |
| 2 | 实现 data_access.py：`ComprehensiveUpstreamProvider.fetch` + 单元测试 | data_access.py, test_comprehensive_phase1.py 部分 | `pytest tests/test_comprehensive_phase1.py::TestComprehensiveUpstreamProvider -v` |
| 3 | 实现 feature_builder.py：搬 `_build_*_score`、抽 metrics、抽 summaries + 单元测试 | feature_builder.py, test 补充 | `pytest tests/test_comprehensive_phase1.py::TestComprehensiveFeatureBuilder -v` |
| 4 | 实现 decision_engine.py：搬 `_assign_segment / _build_conflict_explanations / _derive_*` + persona_seed + tags_rule + flatten_metrics + build_prompt_payload + 单元测试 | decision_engine.py, test 补充 | `pytest tests/test_comprehensive_phase1.py::TestComprehensiveDecisionEngine -v` |
| 5 | 实现 explainer.py：拼 prompt（含 missing_modules 条件渲染 + 追加 comprehensive_prompt.md 一行）+ ModelClient 调用 + conflict 按下标对齐润色 + tags 追加上限 3 + model_trace + 单元测试 | explainer.py, comprehensive_prompt.md, test 补充 | `pytest tests/test_comprehensive_phase1.py::TestComprehensiveExplainer -v` |
| 6 | 实现 assembler.py：build_missing_output + build_fallback_structured + assemble（schema 校验 + charts + report + tags 最终 dedupe）+ 单元测试 | assembler.py, test 补充 | `pytest tests/test_comprehensive_phase1.py::TestComprehensivePageAssembler -v` |
| 7 | 重写 comprehensive_agent.py 为薄入口 + E2E 测试 + 更新 PLANNING.md + 更新 TASK.md + 跑全量测试基线 | comprehensive_agent.py, test E2E, PLANNING.md, TASK.md | `pytest tests/ -v`（68 全过）+ `python -c "import pathlib; assert sum(1 for _ in pathlib.Path('app/runtime_skills/comprehensive_agent.py').open(encoding='utf-8')) <= 80"` |

**Baseline commit**：执行 task 1 前打 `[baseline] comprehensive-refactor`；task 7 后打 `[complete] comprehensive-refactor`。

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| metrics 拍平形状漂移导致前端/charts 解析失败 | task 4 单测断言 metrics 字段集与现 schema 完全一致；task 7 E2E 对比一份冻结的 fixture 输出 |
| LLM conflict 润色破坏下标对齐 | explainer `_patch_conflict_explanations` 严格按 index 对齐：LLM 返回数组短于 K 时缺位用 seed 顶上；长于 K 时截断 |
| tags 追加上限 3 但 LLM 返回更多 | explainer `_filter_tags_addon` 先 dedupe 再截前 3；assembler 做最终 dedupe 兜底 |
| 部分上游失败时 prompt 误导 LLM | prompt 加 missing_modules 条件渲染显式提示；feature_builder 缺失上游的 metrics 直接置空，score=0 |
| 重构期间 68 测试基线被破坏 | 每个 task 完成立即跑对应单测；task 7 收尾跑全量 |
| API 响应 JSON 形状漂移导致前端解析失败 | task 7 E2E 断言 `POST /api/analyze` 响应 JSON 顶层键集合与重构前一致 |

## 9. 验收标准

1. `app/runtime_skills/comprehensive/` 下六个文件齐全，每个文件单一职责
2. `comprehensive_agent.py` 行数 ≤ 80
3. `tests/test_comprehensive_phase1.py` 至少覆盖 6 个 class、每个 class ≥ 3 个测试用例
4. `pytest tests/ -v` 通过（基线 68 测试 + 新增 comprehensive_phase1 测试 ≥ 18 个 → 共 ≥ 86 测试全过）
5. `ComprehensiveProfileStructuredResult` schema 未改
6. `BaseSkill.analyze(uid, **kwargs)` 签名未改
7. `app/prompts/comprehensive_prompt.md` 仅追加一行 `missing_modules`（条件渲染）
8. mock 模式下端到端可跑通（`MODEL_MODE=mock`）
9. `POST /api/analyze` 的响应 JSON 形状未改（顶层键集合与重构前一致）
