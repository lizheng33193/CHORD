# 泰国（th）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/th/*.csv`
- 行为事件：`data/behavior/th/*.csv`
- 征信数据：`data/credit/th/*.json`
- UID 文件：`data/id_files/th/*.txt`

## UID 规范
- UID 长度 8-32 字符（与 Plan #03 Phase 2 `uid_whitelist._PATTERNS["th"]` 同步）
- 字符集：[a-zA-Z0-9_-]
- 示例：`TH000123` / `th_user_456`

## 关键时区
- Asia/Bangkok (UTC+7)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59 (UTC+7)

## 流失定义（默认）
- 30 天无下单 = 流失
- "上周流失" = 上周内最后一次活跃距今 ≥ 30 天

## 货币
- 单位：THB
- Behavior Profile `value_estimation` 输入按 THB 处理；汇报时不做汇率换算

## 常见取数模板（query_data 触发示例）
- "上周流失下单用户" → 限定时区 UTC+7，过滤上周内有下单记录且最近 30 天无活跃
- "高价值用户" → 单笔 GMV ≥ 1000 THB
- "新增注册" → 按 created_at 过滤，注意时区转换

## V1 query_data 状态
- **stub**：da-agent V1 未启用 thailand manifest，`query_data(country="th")` 抛 `ManifestNotImplemented`
- 解锁条件：Plan #2.5 da-agent 多国扩展 + thailand manifest 实装

## 节假日
- 默认按工作日计算；具体节假日 → `docs/skills/orchestrator/holidays/th.md`（按需扩展）
