# Orchestrator Golden Test Rubric

按 Design Doc § 8.2 4 维 Rubric（每维 1-5 分，单条总分 4-20）。

## 4 维度

1. **工具选择准确性**（tool_selection）：选对工具 = 5；选错主工具 = 1
2. **工具顺序合理性**（tool_order）：query_data 先于 run_profile = 5；颠倒 = 1
3. **参数提取准确性**（param_extract）：country / app_time / uid 提取正确 = 5；缺失 = 2
4. **无幻觉**（no_hallucination）：不调不存在的工具 / 不编造 UID = 5；调不存在工具 = 1

## 通过线

- 单条 ≥ 16/20（每维 ≥ 4 分） → pass
- 12-15 → review
- ≤ 11 → fail

## Judge 选型

- Judge 模型：Claude Opus 4.7（10x tier，独立 Provider 实例）
- Judge prompt 模板：`tests/golden/judge_prompt.md`
- 5-10 次手工对齐校准（Design Doc § 8.5）：偏差 > 1 分 → 调措辞，重跑；偏差 < 1 分才信任 LLM Judge 自动跑
- **Phase 4 V1 用 mock Judge 跑通 runner，5-10 次手工对齐校准放在 Plan #03 [complete] 后单独迭代**
