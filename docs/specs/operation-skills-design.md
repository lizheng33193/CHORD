# Operation Skills Design — ProductAdviceSkill + OpsAdviceSkill

- 作者：Claude Code（与 user 共同确认）
- 日期：2026-04-30
- 状态：Confirmed（user 已逐段确认）
- 关联：CLAUDE.md / PLANNING.md / TASK.md（P2 项 — Stage=2 经营层 Skill）

---

## 1. 目标

为现有四画像管线（app / behavior / credit / comprehensive）增加经营层 stage=2 的两个 Skill：

- **ProductAdviceSkill**（`product_advice`）— 产品策略：续贷 / 提额 / 利率方案 / 推荐渠道
- **OpsAdviceSkill**（`ops_advice`）— 运营策略：催收 / 流失预警 / 触达渠道 / 挽回方案

两者结构同构（同 stage、同上游、同六步管线），仅业务规则不同 — 因此共享一份 Design Doc，分两节并列描述。

## 2. 在系统中的位置

```
stage 0  (并行)   AppProfile / BehaviorProfile / CreditProfile
                          ↓
stage 1  (串行)   ComprehensiveProfile
                          ↓
stage 2  (并行)   ProductAdviceSkill  +  OpsAdviceSkill   ← 本次新增
```

- `stage = 2`
- `depends_on = ["comprehensive_profile"]`（只依赖综合画像，不再直读 app/behavior/credit，避免重复融合）
- 由 `SkillRegistry` 注入 `comprehensive_profile_result` kwarg

## 3. 上游契约（消费 comprehensive 的哪些字段）

来自 `comprehensive_profile_result["structured_result"]`（参考方案文档 §六 6.2 的 JSON 输出 + `app/schemas/comprehensive_profile.py`）：

| 字段路径 | 类型 | 用途 |
|---|---|---|
| `recommended_segment` | `S1`–`S6` | 核心驱动：决定策略矩阵 |
| `segment_name` | str | 报告展示 |
| `overall_risk` | 低/中低/中/中高/高 | 利率/额度/催收力度 |
| `overall_value` | 高/中高/中/低 | 是否提额/VIP |
| `behavior_tags.churn_risk` | 高/中/低 | OpsAdvice 流失预警等级提升 |
| `behavior_tags.best_contact_channel` | WhatsApp/Push/SMS | 触达渠道 |
| `behavior_tags.best_contact_time` | str | 触达时间 |
| `behavior_tags.product_activity` | str | 提额意愿 |
| `financial_tags.multi_head_risk` | 高/中/低 | ProductAdvice 控额 |
| `financial_tags.debt_pressure` | 高/中/低 | 催收 / 控额 |
| `financial_tags.borrowing_urgency` | 高/中/低 | 续贷急迫度 |
| `signal_conflicts[]` | list | 报告中风险提示 |
| `confidence` | 高/中/低 | 输出置信度透传 |
| `data_completeness.*` | dict | 数据缺失时降级 |

**降级规则**：若 `comprehensive_profile_result` 缺失 / `status != "ok"` / `recommended_segment` 不在 S1–S6 → `assembler.build_missing_output()` 给 "数据不足，建议人工复核" 文案，`structured_result.status = "data_missing"`。

## 4. 输出契约（与 AgentOutput 对齐）

两个 Skill 都返回 `AgentOutput` 四件套（summary / structured_result / charts / report_markdown）。schema 文件分开：

- 新增 `app/schemas/product_advice.py` → `ProductAdviceStructuredResult`
- 新增 `app/schemas/ops_advice.py` → `OpsAdviceStructuredResult`
- 都包含 `ModelTrace`（与 comprehensive 一致，便于 `used_llm` 可观测）

### 4.1 final_response.py 扩展（向后兼容）

```python
class UserAnalysisResult(BaseModel):
    uid: str
    app_profile: AgentOutput
    behavior_profile: AgentOutput
    credit_profile: AgentOutput
    comprehensive_profile: AgentOutput
    product_advice: AgentOutput | None = None   # 新增
    ops_advice: AgentOutput | None = None       # 新增
```

`Optional + 默认 None` → 旧 client 忽略未知字段不会 break。`orchestrator._analyze_single_user` 在 stage=2 完成后从 `registry_results` 取这两个值回填。

## 5. 决议：API 暴露方式

确认走方案 1（user 已选）：扩展 `UserAnalysisResult` 为 Optional 字段。`/api/analyze` 响应 JSON 中将多出 `product_advice` 与 `ops_advice` 两个 section（值可能为 null）。

## 6. 六步管线结构

两个 Skill 共享相同的目录结构：

```
app/runtime_skills/
├── product_advice_agent.py        (新增) 薄入口，≤80 行
├── product_advice/
│   ├── __init__.py                (已存在，空)
│   ├── contracts.py               (已存在，需扩展 FeatureBundle / DecisionResult / ExplanationResult)
│   ├── data_access.py             (新增) 从 comprehensive_profile_result 抽取上游字段
│   ├── feature_builder.py         (新增) normalize + 派生字段
│   ├── decision_engine.py         (新增) 规则引擎：S1–S6 → 策略矩阵查表
│   ├── explainer.py               (新增) LLM 增强（mock 降级）
│   └── assembler.py               (新增) 拼 AgentOutput
├── ops_advice_agent.py            (新增)
└── ops_advice/                    (同构)
```

## 7. ProductAdviceSkill 策略矩阵

来自方案文档 §八 客群分层矩阵第 5 列「核心经营策略」。`decision_engine` 由规则查表给出 100% 确定性的决策：

| segment | renewal_strategy | credit_line_action | rate_plan | recommended_channel | priority |
|---|---|---|---|---|---|
| S1 优质成长客 | 主动续贷（提前 7 天触达） | 主动提额 +30~50% | VIP 专属低利率 | WhatsApp + Push | P0 |
| S2 稳健经营客 | 续贷优惠（满期 3 天前触达） | 适度提额 +10~20% | 标准利率 + 优惠券 | WhatsApp | P1 |
| S3 价格敏感客 | 限时利率优惠续贷 | 维持额度 | 比竞品低（如 Kueski 锚点） | Push + 邮件 | P1 |
| S4 潜在流失客 | 挽回式续贷（重激活） | 维持额度 | 挽回券（首期免息） | WhatsApp 专属关怀 | P0 |
| S5 多头高风客 | 不主动续贷 / 缩短账期 | 控额，不提额 | 不发券 | 仅风控通知（SMS） | — |
| S6 沉默观望客 | 场景化续贷（Buen Fin 唤醒） | 维持额度 | 标准利率 | Push（轻触达） | P2 |

`structured_result` 形状（草案）：

```json
{
  "uid": "...",
  "agent_name": "product_advice_agent",
  "status": "ok",
  "segment": "S2",
  "renewal_strategy": {"action": "续贷优惠", "trigger_offset_days": -3, "reason": "..."},
  "credit_line_action": {"action": "适度提额", "delta_pct_range": [10, 20], "reason": "..."},
  "rate_plan": {"plan": "标准利率 + 优惠券", "anchor_competitor": null},
  "recommended_channel": {"primary": "WhatsApp", "secondary": "Push", "best_time": "晚间19-21点"},
  "priority": "P1",
  "tags": ["S2", "续贷优惠", "适度提额", "WhatsApp"],
  "model_trace": {"...": "..."}
}
```

## 8. OpsAdviceSkill 策略矩阵

| segment | collection_strategy | churn_warning | outreach_channel | retention_offer |
|---|---|---|---|---|
| S1 + 无逾期 | 无需催收 | 无 | — | — |
| S2 + 无逾期 | T+1 软提醒（WhatsApp） | 无 | WhatsApp | — |
| S3 价格敏感 | T+1 软提醒 | 轻预警（比价中） | Push | 利率券（防流失） |
| S4 潜在流失客 | T+1 软提醒 | 强预警 | WhatsApp 专属关怀 | 挽回礼包 + 首期免息 |
| S5 多头高风客 | 提前提醒（D-3） + T+1 / T+7 加强 | 强预警 | SMS + 电话 | 不发券 |
| S6 沉默 | 场景化唤醒 | 中预警（沉默 30 天） | Push（轻触达） | 唤醒券 |

**等级提升规则**：`comprehensive.behavior_tags.churn_risk == "高"` 时 churn_warning 上调一档（无 → 轻 → 中 → 强），但不会跨越客群本身的 collection_strategy 强度。

`structured_result` 形状（草案）：

```json
{
  "uid": "...",
  "agent_name": "ops_advice_agent",
  "status": "ok",
  "segment": "S4",
  "collection_strategy": {"trigger": "T+1", "reminder_steps": ["WhatsApp soft", "WhatsApp + Push D+3"], "intensity": "soft"},
  "churn_warning": {"level": "high", "signals": ["竞品APP安装", "活跃度下降"]},
  "outreach_channel": {"primary": "WhatsApp", "best_time": "晚间19-21点"},
  "retention_offer": {"type": "首期免息+挽回礼包", "valid_days": 14},
  "tags": ["S4", "强流失预警", "WhatsApp", "挽回券"],
  "model_trace": {"...": "..."}
}
```

## 9. 决策表落地位置（Country Pack）

抽成 Python dict 常量，与现有 country_packs 风格一致：

- `app/country_packs/mx/product_advice_rules.py` （新增）
- `app/country_packs/mx/ops_advice_rules.py` （新增）
- `app/country_packs/mx/segments.py` （新增，segment 枚举共享，避免漂移）

`decision_engine.py` 仅做查表 + churn_risk 等级提升的合并逻辑。未来扩展东南亚只需新增 country_pack。

## 10. LLM 增强（explainer 层）

两个 Skill 都遵循 "规则给 fallback；LLM 仅增强可读性" 双轨。

**Prompt 模板（新增 2 个）**：
- `app/prompts/product_advice_prompt.md` — 输入 segment + 规则查到的 raw action → LLM 输出 `recommendation_summary`（自然语言）+ `talking_points`（3-5 条具体话术）+ `risk_warnings`
- `app/prompts/ops_advice_prompt.md` — 输入 segment + churn_signals + collection_intensity → LLM 输出 `outreach_script`（WhatsApp / SMS 草稿，不含敏感金额）+ `retention_pitch`

**LLM 仅增强不决策**：`renewal_strategy / credit_line_action / collection_strategy / churn_warning` 等关键字段全部由规则引擎落定。LLM 只在 `summary / talking_points / outreach_script` 等说明性字段填内容。这样 LLM 不可用时直接用规则文案降级。

**Mock 降级**：
- `model_client.mode == "mock"` → 跳过 LLM，`explainer.status="model_mode_mock"`，summary 用模板（如 `"S2 客群建议续贷优惠 + 适度提额"`）
- `model_client.mode != "mock"` 但调用失败 / JSON 解析失败 → `explainer.status="model_unavailable"`，仍用规则文案
- `model_trace.used_llm` 透传

**Prompt 输入大小**：上游只取 comprehensive 的核心字段（约 15 个 tag），prompt < 5KB，无需 token 预算管控。

## 11. assembler 输出形状

```python
{
    "summary": "<1-2 句话的策略概要>",
    "structured_result": {... 见第 7/8 节 ...},
    "charts": [],          # 本期 YAGNI：经营建议主要是文字 + 表格
    "report_markdown": "<结构化 markdown>",
}
```

`charts` 留空是本期 YAGNI 决定。前端没有图表诉求；未来若要画 "S1-S6 占比饼图" 也是聚合层的事。

## 12. 测试设计（TDD）

新增测试文件：
- `tests/test_product_advice_phase1.py`
- `tests/test_ops_advice_phase1.py`

每个文件覆盖：
1. **正常路径**（mock LLM）：S1/S2/S3/S4/S5/S6 各跑一次，断言 `structured_result.segment` 与策略字段
2. **边界**：上游 `status != "ok"` / segment 不在 S1-S6 / `data_completeness` 缺一维
3. **降级**：`model_client.mode == "mock"` 不报错，`status="model_mode_mock"` 透传到 model_trace
4. **schema 校验**：`AgentOutput.model_validate(result)` 通过
5. **集成**：扩展 `tests/test_orchestrator_*.py` 或新增一个，验证 `_analyze_single_user` 输出的 `UserAnalysisResult.product_advice` / `.ops_advice` 非 None

## 13. 风险与边界

| 风险 | 缓解 |
|---|---|
| comprehensive 输出 schema 字段名 / 嵌套与 §六示例略有偏差 | data_access 层做 `dict.get(..., default)`，缺字段时打 warning 不挂 |
| segment 字段大小写 / 前后空格 | feature_builder normalize（upper + strip） |
| 旧 client 反序列化新 schema 报 unknown field | Optional + 默认 None，Pydantic v2 默认 ignore extra |
| LLM 输出话术包含金额 / 利率数字幻觉 | prompt 里禁止 LLM 写具体数字，金额从 structured_result 取 |
| 矩阵表被复制成两份难维护 | segment 枚举共享 `app/country_packs/mx/segments.py` |

## 14. Out of Scope（本期不做）

- LangGraph 迁移
- Charts 渲染（饼图、桑基图）
- 多国家（仅墨西哥；其他国家走 country_pack 占位）
- Prompt 模板的 A/B
- 实时回流（运营策略命中率监控）

## 15. 后续步骤

- Step 3：检查 stub 现状 → 建六步管线骨架 → 更新 PLANNING.md
- Step 4：写 Plan 到 `docs/plans/operation-skills-plan.md`，每个 Task 2-5 分钟，含完整代码 + 验证命令
- Step 5：TDD 实现，每完成一个 Phase 停下汇报
- Step 6：Spec 合规性检查 + 代码质量检查
- Step 7：交付（不 push）
