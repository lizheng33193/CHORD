# Golden Test Design — Behavior + Comprehensive Profile 回归基线

- 作者：Claude Code（与 user 共同确认）
- 日期：2026-05-01
- 状态：Draft（待 user 确认）
- 关联：CLAUDE.md / PLANNING.md / TASK.md（A1 — Golden Test 评估框架）
- 适用范围：`behavior_profile` + `comprehensive_profile` 两个 Skill 的输出回归
- 框架可扩展性：新增 Skill 仅需新增 Golden Case fixture + 注册条目，不需改评估框架本身

**本期范围限定（受数据约束）**：

- `behavior_profile`：4 个 Golden Case（G1–G4），覆盖今日 prompt 改动的 4 个触发维度，跑 L1+L2+L3 完整三层断言
- `comprehensive_profile`：仅 1 个 Golden Case（G1，唯一三方数据齐全的 UID），作为 **smoke test**（仅 L1+L2，不做 L3-d 跨 case 差异化），目的是确认 behavior 改动没有让 comprehensive 的 schema 坏掉
- 完整 comprehensive 覆盖推到下期（数据补齐 ≥ 3 个三方齐全 UID 后），加 fixture + 注册条目即可，不改框架

---

## 1. 目标

为今日 prompt 改动密集的 `behavior_profile`（churn_root_cause 指引、Quincena 发薪日分析、token 裁剪、流失归因）以及其下游 `comprehensive_profile`（stage 1 直接消费上游输出）建立一套**可复跑、可量化、可审 diff** 的回归基线，使得：

1. Prompt 改动后能立即定位是否引入回归（结构 / 字段 / 叙述模板化）
2. 回归报告能直接指向具体 prompt 段落（通过 case 的"为什么选它"标签）
3. 跑一次评估 ≤ 数秒（不打 real LLM），CI / 本地都可频繁跑
4. Prompt 真的有意改动时，开发者用显式 `--refresh-fixtures` 重录，PR diff 把 LLM 输出变化变成可 review 的 artifact

**非目标**（本期不做）：
- `app_profile` / `credit_profile` / `product_advice` / `ops_advice` 的 Golden Test（前两者今日未改 prompt；后两者刚落地 3 天，输出未稳定）
- 扩展层 loose 比对（schema-only + 数值范围）—— 留给未来 D 模式
- LLM-as-judge 语义等价比对 —— 引入 LLM 不确定性到评估本身，避免
- markdown 报告归档 —— pytest 结构化诊断 + fixture diff 已够用，留给扩展层

## 2. 在系统中的位置

```
现有 178 测试体系（pytest tests/）
    └── tests/test_golden_behavior_comprehensive.py   ← 本次新增
            └── tests/golden/runner.py                 ← 评估辅助（薄测试 + 厚 runner）
                    ├── 读 / 写 fixture
                    ├── 调 BehaviorProfileSkill / ComprehensiveProfileSkill
                    └── 执行三层断言
            └── tests/fixtures/golden/                 ← 录制的真实 LLM 输出（进 git）
                    ├── behavior_profile/{uid}.json
                    └── comprehensive_profile/{uid}.json
```

- 不进入 `app/runtime_skills/`，不参与运行时
- 不进入 `app/scripts/eval/`，因为 golden runner 本质是测试基础设施（CLAUDE.md "测试文件默认只在 tests/ 下创建"）
- 不修改任何 Skill 代码 —— Golden Test 是**只读消费者**，调 `skill.analyze(uid, **kwargs)` 拿输出后断言

## 3. Golden Case 选取标准（按"prompt 改动点能否触发"定义维度）

### 3.1 维度调整说明

Q2 原候选维度（高活跃 / 低活跃高强度 / 高 churn / Quincena）基于 **30 天用户画像假设**，但实际 `data/behavior/by_uid/` 的 9 个 UID 是**申请期单日 / 双日行为快照**（最高活跃天数仅 2 天，平均会话 < 2 分钟），原标准不匹配数据。

调整为按**今日 prompt 改动点能否触发**定义维度：

| 维度 | 触发条件（基于原始事件统计） | 评估目的 |
|---|---|---|
| A — 强 Quincena | quincena 占比 ≥ 70% | 验证 behavior prompt 注入了 Quincena 发薪日上下文 |
| B — 弱 Quincena（反例） | quincena 占比 ≤ 50% | 验证 prompt 不会强行编造发薪日叙述 |
| C — 高事件密度 | events > 500 | 验证 token 裁剪能否处理大事件量 |
| D — 低事件密度 | events < 300 | 验证 token 充足时叙述不退化 |

### 3.2 本期 4 个 Golden Case（behavior）

| ID | UID | events | 活跃天数 | quincena% | 跨度(天) | 维度 | 选取理由 |
|---|---|---|---|---|---|---|---|
| G1 | `824812551379353600` | 593 | 2 | 70.2% | 9.0 | A + C | 强 quincena + 高密度 + 多日跨度；**唯一三方齐全** → 同时作 comprehensive smoke |
| G2 | `824822394441957376` | 978 | 2 | 91.1% | 1.3 | A + C | 高密度强 quincena 极端 case |
| G3 | `824848564055179264` | 414 | 2 | 36.0% | 1.8 | B + C | quincena 反例 |
| G4 | `824928257039138816` | 234 | 1 | 100% | 0.0 | D | 低密度短促对照 |

每个 case 在 runner 注册表（`GOLDEN_CASES`）中标注 `uid` / `selection_reason` / `dimensions` / `key_assertions`。

### 3.3 comprehensive smoke case

| ID | UID | 说明 |
|---|---|---|
| G1-comp | `824812551379353600` | 唯一三方齐全 UID，仅做 L1 + L2，不做 L3-d；目的是验证 behavior 改动没让 comprehensive schema 坏掉 |

## 4. 三层断言设计

### L1 — 结构层

| 项 | 断言 |
|---|---|
| behavior `structured_result` | `BehaviorStructuredResult.model_validate(...)` 不抛异常 |
| comprehensive `structured_result` | `ComprehensiveStructuredResult.model_validate(...)` 不抛异常 |
| AgentOutput 四件套 | `summary` / `structured_result` / `charts` / `report_markdown` 四个 key 都存在 |

L1 失败 = 代码坏了（schema 不兼容 / 字段缺失），必须 100% 通过。

### L2 — 字段层

| 字段路径（behavior） | 断言 |
|---|---|
| `structured_result.evidence.behavior_profile_narrative.behavior_summary` | str，`len > 50` |
| `summary` | str，`len > 20` |
| `report_markdown` | str，`len > 100` |
| `structured_result.churn_root_cause`（如果是 high churn case） | `list[str]`，非空，每个值 ∈ `{credit_limit_unmet, interest_perception_high, competitor_poaching, ux_friction, repayment_burden, no_clear_signal}` |

| 字段路径（comprehensive） | 断言 |
|---|---|
| `structured_result.recommended_segment` | `str`，∈ `{S1, S2, S3, S4, S5, S6}` |
| `summary` | str，`len > 20` |
| `report_markdown` | str，`len > 100` |

L2 失败 = 字段丢了 / 枚举越界。

> **注**：`churn_root_cause` 的具体路径需 Plan 阶段确认（在 `structured_result` 顶层 还是 `behavior_tags` 下），断言代码用 helper 函数访问，避免路径硬编码。

### L3 — 内容层（regex 反向断言）

只做"不能匹配"，不做"必须出现"。理由：LLM 措辞有正常变化，正向断言会频繁误报；反向断言锁的是 prompt 里**明确禁止**的模板句，是确定性的"不能出现"。

| # | 断言对象 | 反向 regex | 锁的是什么 |
|---|---|---|---|
| L3-a | `behavior_summary` 开头 | 不匹配 `r"^该用户近\s*\d+\s*天活跃天数"` | 防止退化为模板首句 |
| L3-b | `behavior_summary` 开头 | 不匹配 `r"^标准化旅程共识别"` | 防止退化为占位首句 |
| L3-c | `business_advice` 每条开头（如有该字段） | 不匹配 `r"^建议(优化\|突出\|触发\|在关键流失窗口前)"` | 防止建议泛化模板 |
| L3-d | 强 quincena case (G1, 70%) vs 弱 quincena case (G3, 36%) 的 `behavior_summary` quincena 段叙述 | 必须显著不同（具体 regex 见 Plan 阶段） | 锁死跨 case 的 quincena 叙述差异化（这条是跨 case 断言，仅在 behavior 上做，不在 comprehensive 上做——comprehensive 本期只有 G1 一个 case） |

L3 失败 = 叙述模板化，prompt 改动可能引入了不期望的退化。

## 5. LLM 调用模式 — Real LLM + 录制回放

```
首次（或 --refresh-fixtures）：
  pytest tests/test_golden_behavior_comprehensive.py --refresh-fixtures
    │
    ├── 设 ModelClient.mode = "vertex"
    ├── 跑每个 (uid, skill) 组合一次 → 拿 AgentOutput
    ├── 写到 tests/fixtures/golden/{skill}/{uid}.json
    └── 不执行断言（refresh 模式只录不评）

日常 / CI：
  pytest tests/test_golden_behavior_comprehensive.py
    │
    ├── 不调 ModelClient
    ├── 直接读 tests/fixtures/golden/{skill}/{uid}.json
    └── 跑 L1/L2/L3 三层断言
```

**为什么不直接 mock 模式**：mock 模式走 deterministic fallback，绕开 prompt 渲染，无法验证 prompt 改动效果。

**fixture 文件内容**：完整 `AgentOutput`（`summary` + `structured_result` + `charts` + `report_markdown`），保证 L1/L2/L3 三层断言都能从 fixture 跑出来。

**fixture 进 git**：PR diff 可见，prompt 改动后 refresh 出来的 fixture 变化会作为 review artifact。

## 6. 评估结果输出 — pytest + 结构化诊断

不另建 markdown 报告。失败时 `AssertionError` 信息自包含：

```
AssertionError: [behavior][uid=824812551379353600] L3-a violation:
  behavior_summary 命中禁用模板 r"^该用户近\s*\d+\s*天活跃天数"
  实际开头='该用户近 30 天活跃天数 18 天，会话深度...'
  fixture: tests/fixtures/golden/behavior_profile/824812551379353600.json
  selection_reason: 高活跃用户（验证差异化叙述）
```

成功时 pytest 默认沉默，符合现有 178 测试体系的输出风格。

## 7. 模块职责划分

### `tests/test_golden_behavior_comprehensive.py`（薄）

- pytest 入口
- 使用 pytest custom flag `--refresh-fixtures`（在 `conftest.py` 注册）
- 每个 (uid, skill) 组合一个 test case（用 pytest parametrize）
- 跨 case 的 L3-d 断言用单独的测试函数

### `tests/golden/runner.py`（厚）

职责：
- `load_fixture(skill, uid) -> AgentOutput dict`
- `record_fixture(skill, uid, output) -> None`
- `run_skill_real_llm(skill_name, uid) -> AgentOutput dict`（仅 refresh 模式调用）
- `assert_l1_structure(skill_name, fixture) -> None`
- `assert_l2_fields(skill_name, fixture, case_metadata) -> None`
- `assert_l3_content(skill_name, fixture, case_metadata) -> None`
- `assert_l3d_cross_case_diff(high_active_fixture, low_active_fixture) -> None`
- `GOLDEN_CASES: list[CaseMetadata]` 注册表（含 uid + selection_reason + 触发哪些断言）

### `tests/conftest.py`（如已存在则改造，否则新建）

- 注册 `--refresh-fixtures` flag
- 提供 fixture mode 判断函数

### `tests/fixtures/golden/`

- 进 git
- 由 refresh 模式生成
- 任何手工修改视为非法（PR review 时拒绝）

## 8. Plan 阶段必须包含的 Task

下游 Plan 文档要包含至少这些 Task（顺序）：

1. Q6 候选 UID 确认 → 选定 3-5 个具体 UID
2. 新建 `tests/conftest.py` 注册 `--refresh-fixtures` flag
3. 新建 `tests/golden/__init__.py` + `tests/golden/runner.py`（先写 stub + 接口）
4. 新建 `tests/test_golden_behavior_comprehensive.py`（先写失败测试 — RED）
5. 实现 runner 的 fixture 读写 + L1 结构断言（GREEN）
6. 实现 L2 字段断言（GREEN）
7. 实现 L3 内容反向断言 + L3-d 跨 case 断言（GREEN）
8. **首次 baseline 录制**：`pytest tests/test_golden_behavior_comprehensive.py --refresh-fixtures`，跑 real LLM 录制初始 fixture，肉眼审核所有 fixture 内容是否合理后 commit
9. 不带 flag 重跑一次确认全绿
10. 全量 `pytest tests/ -v` 确认零回归

## 9. 风险与降级

| 风险 | 影响 | 应对 |
|---|---|---|
| Real LLM refresh 时 vertex 配额不足 / 鉴权失败 | 无法录制 baseline | refresh 模式失败要明确报错，让 user 检查 `MODEL_MODE` / `key.json` |
| LLM 输出非确定性，refresh 出来的 fixture 跨次不一致 | L3 断言可能因为措辞变化失败 | L3 用反向断言而非正向比对，且 fixture 进 git 后只在显式 refresh 时变化 |
| `data/sample_ids.txt` 中 UID 在 `data/behavior/` 缺失 | 无法跑该 case | Q6 阶段就要扫数据确认 UID 数据完整 |
| `churn_root_cause` 字段路径在 schema 里和 prompt 输出不一致 | L2 断言路径错误 | runner 用 helper 访问，路径在一处定义 |
| Schema 校验失败因 LLM 输出新字段 | L1 全部失败 | Pydantic 默认 ignore extra，不会因新字段失败 |

## 10. 验收标准

Plan 全部 Task 完成后：

- [ ] `pytest tests/test_golden_behavior_comprehensive.py -v` 全绿（不带 flag，从 fixture 跑）
- [ ] `pytest tests/ -v` 全量零回归（基线 178+ tests 全过）
- [ ] `tests/fixtures/golden/behavior_profile/` 和 `tests/fixtures/golden/comprehensive_profile/` 各 3-5 个 fixture，已 commit
- [ ] PLANNING.md / TASK.md 更新（A1 打勾）
- [ ] 故意改坏一个 prompt（如把 churn_root_cause 指引删掉），re-refresh 后 L2 断言能捕捉到 → 反向证明框架有效（这一步可由 user 抽查）

## 11. 更新记录

- [2026-05-01] 初始 Draft，Q1-Q5 确认后产出
- [2026-05-01] Q6 数据扫描后调整：§1 范围加"behavior 4 case + comprehensive 1 case smoke"；§3 维度从 Q2 原标准换为"prompt 改动点触发"四维度，写入具体 4 个 UID（G1-G4）；§4 L3-d 跨 case 断言从"高活跃 vs 低活跃"换为"强 quincena vs 弱 quincena"
