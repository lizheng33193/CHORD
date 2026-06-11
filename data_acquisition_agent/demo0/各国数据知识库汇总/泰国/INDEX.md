# Thailand Data Acquisition Knowledge Base — INDEX

> 本文件为 LLM 路由用，列出本目录下每个 md 文件的元数据。
> 路由优先级：always_inject > INDEX 关键词命中 > BM25 兜底 > 全量回退（env var）

---

## system_prompt.md
- **path**: data_acquisition_agent/demo0/system_prompt.md
- **title**: 跨国共享 system prompt（任务流程、JSON 输出契约、analyst_private_prefix 规则）
- **keywords**: [system, prompt, role, task_orientation, json_format_rules, analyst_private_prefix]
- **usage_hint**: 必须始终注入，承载任务流程与输出契约
- **token_estimate**: 4713
- **always_inject**: true

## 多国业务逻辑.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/多国业务逻辑.md
- **title**: 业务黑话词典（mob1 / eKYC 拦截 / 复借首贷 / 客群定义 / 时间窗口）
- **keywords**: [活跃用户, 沉默用户, 风控, 阈值, 分层, mob1, eKYC, 复借, 首贷, 黑话, 业务规则]
- **usage_hint**: 当用户问题涉及"什么算 X"、"X 的定义"、"X 的判断标准"
- **token_estimate**: 2505
- **always_inject**: false

## scheme.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/scheme.md
- **title**: StarRocks 物理 schema（主表 / 维度表 / 事件表 / UID 字段名）
- **keywords**: [schema, table, column, dwd_, ods_, dws_, fact_, dim_, 字段, 表结构, uid, user_uuid, individual_uuid]
- **usage_hint**: 任何涉及"查询哪张表"、"字段是什么类型"、"表之间怎么 JOIN"的问题
- **token_estimate**: 11342
- **always_inject**: true

## few.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/few.md
- **title**: 目标国原生验证代码（高频 SQL 模板 + 目标国本地化 quirks）
- **keywords**: [example, few-shot, 模板, sql 示例, 时区, 渠道, 风控标识]
- **usage_hint**: 默认作为基础 few-shot；本地化字段替换时优先级最高
- **token_estimate**: 5734
- **always_inject**: true

## all_examples .md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/all_examples .md
- **title**: 跨国全局 SQL 示例库（100+ 个 NL→SQL 历史成功 case，跨国宏观骨架）
- **keywords**: [完整示例, 历史 case, 高级查询, CTE, 漏斗, 跨国]
- **usage_hint**: 复杂查询场景下补充示例；提取纯逻辑骨架，禁止直接带入参考国字段
- **token_estimate**: 25014
- **always_inject**: false

## gem prompt.md
- **path**: data_acquisition_agent/demo0/各国数据知识库汇总/泰国/gem prompt.md
- **title**: Gemini 提示词补丁（gem 模型行为微调）
- **keywords**: [gemini, prompt patch, 模型微调]
- **usage_hint**: 仅 gem 模型路由命中时注入
- **token_estimate**: 4731
- **always_inject**: false
