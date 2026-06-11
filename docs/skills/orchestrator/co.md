# 哥伦比亚（co）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/co/*.csv`
- 行为事件：`data/behavior/co/*.csv`
- 征信数据：`data/credit/co/*.json`
- UID 文件：`data/id_files/co/*.txt`

## UID 规范
- UID 长度 4-32 字符
- 字符集：[a-zA-Z0-9_-]

## 关键时区
- America/Bogota (UTC-5)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：COP（哥伦比亚比索；金额数值大，注意 int64 溢出）

## 常见取数模板
- "高价值用户" → 单笔 GMV ≥ 100,000 COP（V1 占位阈值，业务方确认后更新）

## V1 query_data 状态
- **不支持**：da-agent V1 没有 colombia manifest 也没有枚举值。`query_data(country="co")` 在工具入口直接抛 `ValueError("V1 query_data does not support country='co'")`
- 解锁条件：业务方确认 colombia 接入需求 → da-agent 增加 colombia 枚举 + manifest（独立 Plan）

## 节假日
- 默认按工作日计算
