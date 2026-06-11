# 本地开发 — All Examples（local MySQL `user_profile`）

参考 [few.md](./few.md) 的本地示例。本地开发模式只覆盖最基础的两类场景：

- `cohort discovery`：抽样 UID、三方齐全 UID、按 App 类别 / 行为时间窗 / 征信信号找 UID
- `bucket extraction`：在确认 UID 范围后，抽取 app / behavior / credit 原始字段写入 `by_uid`

不支持的场景（生产环境才有）：
- 多日数仓分区（`dt=...`）
- 用户画像产品中间层（`dwd_loan_user_*`）
- 关联资产/借贷/还款/催收宽表
- 生产 StarRocks / Hive catalog
- `CREATE TABLE AS SELECT` / `dm_model.*` 临时表
