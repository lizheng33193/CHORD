# 本地开发 — 业务逻辑（local MySQL `user_profile`）

> 简化版业务逻辑，仅用于本地开发联调，不代表真实业务规则。

## 用户身份

每个用户由 `uid`（VARCHAR(20)，雪花 ID）唯一标识。本地数据集仅含墨西哥地区少量样本用户。

## 数据来源

- **App 数据**：用户已安装的 App 清单；分类字段已在入库时和 `app_label_dictionary` 做过 join
- **行为数据**：用户在我司 App 内的埋点事件
- **征信数据**：墨西哥征信/CDC 的原始样本字段，保存在 `credit_report_raw`

## 用户分群（简化）

- **高风险**：`credit_report_raw` 中 `valor` 偏低，或 `razones` 非空
- **金融人群**：`app_install_list` 中 `gp_category = '金融'`，或 `ai_category_level_2_CN` 命中金融相关分类
- **活跃用户**：最近 7 天内 `behavior_events` 有事件

## 取数原则

1. 默认抽样 5 个 UID（用户未指定时）
2. SQL 必须 `SELECT uid`（pipeline 切分依赖此字段）
3. 必须带 `LIMIT`，避免全表扫描
4. cohort discovery 和 bucket extraction 要分开思考：
   - cohort discovery：找 UID
   - bucket extraction：返回写 bucket 所需字段
5. `app_label_dictionary` 主要用于 join 与校验，不是默认 bucket 目标表
6. 禁止引用任何生产数仓表名
