# 智利（cl）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/cl/*.csv`
- 行为事件：`data/behavior/cl/*.csv`
- 征信数据：`data/credit/cl/*.json`
- UID 文件：`data/id_files/cl/*.txt`

## UID 规范
- UID 长度 4-32 字符
- 字符集：[a-zA-Z0-9_-]

## 关键时区
- America/Santiago (UTC-4 / 夏令时 UTC-3)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：CLP（智利比索；金额数值大，注意 int64 溢出）

## 常见取数模板
- "高价值用户" → 单笔 GMV ≥ 50,000 CLP（V1 占位阈值）

## V1 query_data 状态
- **不支持**：与 co 同
- 解锁条件：与 co 同

## 节假日
- 默认按工作日计算
