# 本地开发 — 墨西哥数据库 Schema（Docker MySQL `user_profile`）

> **重要**：你正在为本地开发模式生成 SQL，目标是 Docker MySQL 8 数据库 `user_profile`。  
> **必须只使用以下 4 张表**，不要引用任何 `hive.*` / `dwd_*` / `dwb_*` / `dm_model.*` 生产数仓表。  
> SQL 方言：MySQL 8（兼容 MySQL 5.7 常见查询写法）。  
> **只读查询默认原则**：优先 `query_only`，禁用 `DELETE / DROP / TRUNCATE / UPDATE / INSERT`。

---

## 表 1：`app_install_list` — 用户安装 App 明细

行数级别：约 **112,559** 行，约 **1,000** 个 UID。

| 字段 | 类型 | 含义 |
|---|---|---|
| `uid` | varchar(32) | 用户 ID；app bucket 切片主键 |
| `app_name` | varchar(255) | App 显示名 |
| `app_package` | varchar(255) | Android 包名 |
| `first_install_time` | bigint | 首次安装时间（毫秒时间戳） |
| `last_update_time` | bigint | 最近更新时间（毫秒时间戳） |
| `gp_category` | varchar(255) | Google Play 一级分类 |
| `ai_category_level_1_CN` | varchar(255) | AI 一级中文分类 |
| `ai_category_level_2_CN` | varchar(255) | AI 二级中文分类 |
| `timestamp_` | bigint | 样本抽取时间戳 |
| `create_at` | datetime | 样本创建时间 |

**App bucket extraction 最低字段要求**：  
`uid, app_name, app_package, first_install_time, last_update_time, gp_category, ai_category_level_2_CN`

---

## 表 2：`behavior_events` — 用户埋点行为事件

行数级别：约 **448,296** 行，约 **1,000** 个 UID。

| 字段 | 类型 | 含义 |
|---|---|---|
| `uid` | varchar(32) | 用户 ID |
| `servertimestamp` | bigint | 服务端时间戳（毫秒） |
| `timestamp_` | bigint | 客户端时间戳（毫秒） |
| `scenetype` | varchar(255) | 场景类型 |
| `processtype` | varchar(255) | 进程类型 |
| `eventname` | varchar(255) | 事件名 |
| `extend` | longtext | JSON 字符串扩展字段 |
| `clientmodel` | varchar(255) | 机型 |
| `clientosversion` | varchar(255) | OS 版本 |
| `url` | longtext | 当前 URL |
| `refer` | longtext | 来源 URL |
| `ip` | varchar(255) | IP 地址 |

**Behavior bucket extraction 最低字段要求**：  
至少返回 `uid` + 一个时间字段（`servertimestamp` 或 `timestamp_`）+ 一个事件字段（如 `eventname`、`scenetype`、`processtype`）。

---

## 表 3：`credit_report_raw` — 原始征信/CDC 样本

行数级别：约 **1,000** 行，约 **1,000** 个 UID。

| 字段 | 类型 | 含义 |
|---|---|---|
| `uid` | varchar(32) | 用户 ID（由 `user_uuid` 映射得到） |
| `user_uuid` | varchar(32) | 原始用户 ID |
| `apply_risk_id` | varchar(32) | 风控申请单号 |
| `timestamp_` | varchar(30) | 征信数据时间戳 |
| `code` | varchar(64) | 返回码 |
| `folioconsulta` | varchar(128) | 查询流水号 |
| `nombrescore` | varchar(128) | 分数字段名 |
| `valor` | varchar(64) | 分数或关键值 |
| `razones` | text | 原因摘要 |
| `consultas_detail_json` | longtext | 查询详情 JSON |
| `creditos_detail_json` | longtext | 信贷详情 JSON |
| `dt` | varchar(16) | 原始日期字段 |
| `rn` | int | 原始排序号 |

**Credit bucket extraction 最低字段要求**：  
至少返回 `uid` + 一个强信用信号字段：`valor` / `nombrescore` / `razones` / `consultas_detail_json` / `creditos_detail_json`

---

## 表 4：`app_label_dictionary` — App 分类字典

行数级别：约 **3,670** 行。

| 字段 | 类型 | 含义 |
|---|---|---|
| `app_package` | varchar(255) | 包名，唯一键 |
| `app_name` | varchar(255) | App 名称 |
| `gp_category` | varchar(255) | Google Play 一级分类 |
| `ai_category_level_1_CN` | varchar(255) | AI 一级中文分类 |
| `ai_category_level_2_CN` | varchar(255) | AI 二级中文分类 |
| `rating` | varchar(64) | 评分 |
| `download_count` | varchar(64) | 下载量 |
| `is_delisted` | varchar(16) | 是否下架 |

此表用于构建/校验 `app_install_list`，**通常不是直接写 bucket 的目标表**。

---

## 输出约束（重要）

- **必须** 在 SELECT 列表中包含 `uid` 字段，agent pipeline 依赖它切分 `by_uid` 文件。
- 用户未指定时默认带 `LIMIT`，建议 `5 <= LIMIT <= 100`。
- **不要** 使用生产数仓分区字段（如 `dt='YYYYMMDD'`）限制这 4 张本地表，除非用户明确要求查询 `credit_report_raw.dt`。
- **不要** 生成 `CREATE TABLE` / `DROP TABLE` / `INSERT` / `UPDATE` / `DELETE` / `TRUNCATE`。
- App bucket 字段名必须精确使用 `ai_category_level_2_CN`，不能自行改写大小写或简写。
- 毫秒时间戳建议用 `FROM_UNIXTIME(col / 1000)` 做时间过滤。
