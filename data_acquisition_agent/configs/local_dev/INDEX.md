# Local Dev (MySQL 4-table) Knowledge Base — INDEX

> DA_LOCAL_DEV=1 时使用；面向 Docker MySQL 8 的本地 4 表沙盒，配合跨国共享 `system_prompt.md`

---

## system_prompt.md
- **path**: data_acquisition_agent/demo0/system_prompt.md
- **title**: 跨国共享 system prompt
- **keywords**: [system, prompt, role, task_orientation, json_format_rules]
- **usage_hint**: 必须始终注入
- **token_estimate**: 0
- **always_inject**: true

## scheme.md
- **path**: data_acquisition_agent/configs/local_dev/scheme.md
- **title**: 本地 mysql 4 表 schema（app / behavior / credit_raw / label）
- **keywords**: [schema, table, mysql, 字段, 表结构, credit_report_raw, app_label_dictionary]
- **usage_hint**: 涉及表名 / 字段问题
- **token_estimate**: 2100
- **always_inject**: true

## business_logic.md
- **path**: data_acquisition_agent/configs/local_dev/business_logic.md
- **title**: 本地业务规则（cohort discovery + bucket extraction）
- **keywords**: [活跃用户, 金融用户, 高风险, 业务规则, 定义]
- **usage_hint**: 业务定义问题
- **token_estimate**: 900
- **always_inject**: false

## few.md
- **path**: data_acquisition_agent/configs/local_dev/few.md
- **title**: 本地 few-shot SQL 模板（cohort + bucket extraction）
- **keywords**: [example, few-shot, sql 示例, bucket extraction, uid]
- **usage_hint**: 默认 few-shot，优先约束到本地 4 表
- **token_estimate**: 1700
- **always_inject**: true

## all_examples.md
- **path**: data_acquisition_agent/configs/local_dev/all_examples.md
- **title**: 本地完整示例库（聚合说明与不支持场景）
- **keywords**: [完整示例, 历史 case, local_dev]
- **usage_hint**: 复杂查询补充；遇到生产表名时回退到本地替代表
- **token_estimate**: 800
- **always_inject**: false
