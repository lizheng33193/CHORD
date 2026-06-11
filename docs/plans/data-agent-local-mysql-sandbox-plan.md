# Data Agent 墨西哥 Docker MySQL 本地沙盒计划

## 目标

打通 `generate -> execute -> write by_uid -> profile read` 的本地真实执行闭环，不追求生产 StarRocks / Hive 还原，不覆盖 mob1 / eKYC / DDL 执行。

## 实施范围

- `DA_LOCAL_DEV=1` 下，知识库路由与 BM25 必须真正切到 `local_dev`
- 本地 schema 升级为 4 表：
  - `app_install_list`
  - `behavior_events`
  - `credit_report_raw`
  - `app_label_dictionary`
- 新增 Docker MySQL 8 compose 与初始化 SQL
- 新增可重跑、分块导入的 Mexico CSV -> MySQL 脚本
- `behavior` / `credit` 继续走 raw CSV 输出，不引入 prepared JSON 兼容改造

## 关键约束

- `/generate` 只允许使用本地 4 表，不得回到生产 `hive.*` / `dwd_*` / `dwb_*` / `dm_model.*`
- `/execute` 仅验证 `query_only`
- App bucket SQL 必须返回精确 7 字段，尤其 `ai_category_level_2_CN`
- 真实导入数据仍位于 `/Users/zhengli/Desktop/docker-data`

## 验收要点

- `metadata.knowledge_files_loaded` 指向 `data_acquisition_agent/configs/local_dev/*.md`
- MySQL 容器可在 `127.0.0.1:3307` 访问
- 4 张表可导入并具备预期数量级
- `app` / `behavior` / `credit` 三类 bucket 都能写入 `by_uid`
- 单 UID `/api/analyze-stream` 能消费新写入的本地数据
