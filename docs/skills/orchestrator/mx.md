# 墨西哥（mx）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/mx/*.csv`
- 行为事件：`data/behavior/mx/*.csv`
- 征信数据：`data/credit/mx/*.json`
- UID 文件：`data/id_files/mx/*.txt`

## UID 规范
- UID 长度 4-32 字符（与 Plan #03 Phase 2 `uid_whitelist._PATTERNS["mx"]` 同步）
- 字符集：[a-zA-Z0-9_-]
- 示例：`MX0001` / `mx_user_123`

## 关键时区
- America/Mexico_City (UTC-6 / 夏令时 UTC-5)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59（按本地时区）

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：MXN

## 常见取数模板
- "上周流失下单用户" → 参考 `data_acquisition_agent/demo0/` 的 mob1 数据集
- "高价值用户" → 单笔 GMV ≥ 1000 MXN

## V1 query_data 状态
- **可用**：da-agent V1 mexico manifest 已实装，163 测试基线已覆盖
- 调用：`query_data(request=..., country="mx")` 走 generate → ACK → execute 链

## 节假日
- 默认按工作日计算；具体节假日按需扩展
